variable "project" {
  description = "Short project name used as a prefix for all resource names."
  type        = string
  default     = "route-radar"
}

variable "environment" {
  description = "Deployment environment tag (e.g. prod, staging)."
  type        = string
  default     = "prod"
}

variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "ca-central-1"
}

# ---------------------------------------------------------------------------
# ECR
# ---------------------------------------------------------------------------

variable "image_tag" {
  description = "ECR image tag to deploy. Set to 'latest' during development; use a git SHA in CI."
  type        = string
  default     = "latest"
}

variable "ecr_image_retention_count" {
  description = "Number of ECR images to retain. Older images are expired automatically."
  type        = number
  default     = 5
}

# ---------------------------------------------------------------------------
# Lambda
# ---------------------------------------------------------------------------

variable "lambda_memory_mb" {
  description = "Lambda memory in MB. Also controls vCPU allocation (1792 MB = 1 vCPU, 3008 MB ≈ 2 vCPUs)."
  type        = number
  default     = 3008
}

variable "lambda_timeout_s" {
  description = "Lambda timeout in seconds. Must be ≤ 29 s when behind API Gateway; Function URL allows up to 900 s."
  type        = number
  default     = 60
}

variable "log_retention_days" {
  description = "CloudWatch log retention period in days."
  type        = number
  default     = 14
}

# ---------------------------------------------------------------------------
# Cloudflare R2
# ---------------------------------------------------------------------------

variable "r2_access_key_id" {
  description = "Cloudflare R2 access key ID."
  type        = string
  sensitive   = true
}

variable "r2_secret_access_key" {
  description = "Cloudflare R2 secret access key."
  type        = string
  sensitive   = true
}

variable "r2_s3_endpoint" {
  description = "Cloudflare R2 S3-compatible endpoint URL (e.g. https://<account>.r2.cloudflarestorage.com)."
  type        = string
}

variable "r2_bucket" {
  description = "Cloudflare R2 bucket name containing the COGs and MosaicJSON."
  type        = string
}

variable "mosaic_key" {
  description = "R2 object key for the pre-built MosaicJSON file."
  type        = string
  default     = "mosaic/relief.json"
}

# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------

variable "budget_limit_usd" {
  description = "Monthly cost budget in USD. You will be alerted at 80% (forecasted) and 100% (actual)."
  type        = string
  default     = "10"
}

variable "budget_alert_emails" {
  description = "List of email addresses to notify when the budget threshold is crossed."
  type        = list(string)
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

variable "cors_allow_origins" {
  description = "List of origins allowed by the Lambda Function URL CORS policy. Use [\"*\"] to allow all."
  type        = list(string)
  default     = ["*"]
}
