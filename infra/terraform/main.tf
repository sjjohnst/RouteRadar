terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ---------------------------------------------------------------------------
# ECR — container image registry
# ---------------------------------------------------------------------------

resource "aws_ecr_repository" "backend" {
  name                 = "${var.project}-backend"
  image_tag_mutability = "MUTABLE" # allows re-pushing "latest" during development

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.common_tags
}

# Keep only the N most recent images to avoid runaway storage costs.
resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Retain only the ${var.ecr_image_retention_count} most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = var.ecr_image_retention_count
      }
      action = { type = "expire" }
    }]
  })
}

# ---------------------------------------------------------------------------
# IAM — Lambda execution role
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${var.project}-lambda-exec"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

# Basic Lambda execution: write logs to CloudWatch.
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Allow Lambda to pull its container image from ECR.
resource "aws_iam_role_policy_attachment" "lambda_ecr_pull" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# ---------------------------------------------------------------------------
# CloudWatch — log group with a retention policy
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/aws/lambda/${var.project}-backend"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

# ---------------------------------------------------------------------------
# Lambda function
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "backend" {
  function_name = "${var.project}-backend"
  role          = aws_iam_role.lambda_exec.arn

  # Container image — push to ECR first, then run terraform apply.
  package_type = "Image"
  image_uri    = "${aws_ecr_repository.backend.repository_url}:${var.image_tag}"

  architectures = ["x86_64"] # matches --platform=linux/amd64 in the Dockerfile
  publish       = true        # required for provisioned concurrency (can't use $LATEST)

  # TiTiler reads entire COG headers and can be CPU-intensive for mosaic builds.
  # 3 GB memory also gives ~2 vCPUs. Adjust down once you have real metrics.
  memory_size = var.lambda_memory_mb
  timeout     = var.lambda_timeout_s

  environment {
    variables = {
      # Cloudflare R2 — credentials injected as R2_* so main.py can remap
      # them to AWS_* before GDAL initialises (see main.py R2 workaround).
      R2_ACCESS_KEY_ID     = var.r2_access_key_id
      R2_SECRET_ACCESS_KEY = var.r2_secret_access_key
      R2_S3_ENDPOINT       = var.r2_s3_endpoint
      R2_BUCKET            = var.r2_bucket

      # GDAL S3 driver — must point at R2, not real AWS.
      AWS_S3_ENDPOINT     = replace(var.r2_s3_endpoint, "https://", "")
      AWS_VIRTUAL_HOSTING = "NO"   # GDAL treats any non-empty string as true; use NO/0 not FALSE
      AWS_HTTPS           = "YES"

      # Pre-built MosaicJSON location in R2.
      MOSAIC_OUTPUT_KEY = var.mosaic_key

      # Packing metadata fallbacks (overridden at startup from COG tags).
      COG_SCALE_FACTOR = "0.01"
      COG_ADD_OFFSET   = "0.0"
    }
  }

  # Ensure the log group exists before Lambda tries to write to it.
  depends_on = [
    aws_cloudwatch_log_group.backend,
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy_attachment.lambda_ecr_pull,
  ]

  tags = local.common_tags
}

# ---------------------------------------------------------------------------
# Lambda alias + provisioned concurrency
#
# The alias ("live") always points to $LATEST. Provisioned concurrency keeps
# N containers permanently warm so concurrent tile requests on a cold map
# don't all race to cold-start simultaneously and trigger 503s.
# Set var.lambda_provisioned_concurrency = 0 to skip this resource.
# ---------------------------------------------------------------------------

resource "aws_lambda_alias" "live" {
  name             = "live"
  function_name    = aws_lambda_function.backend.function_name
  function_version = aws_lambda_function.backend.version
}

resource "aws_lambda_provisioned_concurrency_config" "live" {
  count = var.lambda_provisioned_concurrency > 0 ? 1 : 0

  function_name                  = aws_lambda_function.backend.function_name
  qualifier                      = aws_lambda_alias.live.name
  provisioned_concurrent_executions = var.lambda_provisioned_concurrency
}

# ---------------------------------------------------------------------------
# API Gateway HTTP API — public HTTPS endpoint in front of Lambda.
# This is the pattern recommended by the TiTiler Lambda deployment docs and
# avoids account-level Lambda public access restrictions that block Function URLs.
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_api" "backend" {
  name          = "${var.project}-backend"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = var.cors_allow_origins
    allow_methods = ["GET", "OPTIONS"]
    allow_headers = ["*"]
    max_age       = 86400
  }

  tags = local.common_tags
}

resource "aws_apigatewayv2_integration" "backend" {
  api_id                 = aws_apigatewayv2_api.backend.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_alias.live.invoke_arn
  payload_format_version = "2.0" # required for Mangum
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.backend.id
  route_key = "$default" # catch-all — FastAPI/Mangum handles routing internally
  target    = "integrations/${aws_apigatewayv2_integration.backend.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.backend.id
  name        = "$default"
  auto_deploy = true
  tags        = local.common_tags
}

# Allow API Gateway to invoke the Lambda alias (which carries provisioned concurrency).
resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.backend.function_name
  qualifier     = aws_lambda_alias.live.name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.backend.execution_arn}/*/*"
}

# ---------------------------------------------------------------------------
# AWS Budget — alert when monthly spend approaches the limit.
#
# NOTE: Budgets alert but do NOT automatically stop Lambda. If you want hard
# enforcement, the nuclear option is to set reserved_concurrent_executions = 0
# on the Lambda function manually (or via a second apply) after receiving an
# alert. There is no fully-automatic kill-switch in AWS without custom
# automation (e.g. a CloudWatch alarm → SNS → Lambda that disables concurrency).
# ---------------------------------------------------------------------------

resource "aws_budgets_budget" "monthly" {
  name         = "${var.project}-monthly"
  budget_type  = "COST"
  limit_amount = var.budget_limit_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Alert at 80% of forecasted spend — early warning before you hit the limit.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.budget_alert_emails
  }

  # Alert when actual spend exceeds 100% of the limit.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.budget_alert_emails
  }
}

# ---------------------------------------------------------------------------
# Locals
# ---------------------------------------------------------------------------

locals {
  common_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}
