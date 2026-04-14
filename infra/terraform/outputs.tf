output "api_gateway_url" {
  description = "Public HTTPS endpoint for the RouteRadar TiTiler backend."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "ecr_repository_url" {
  description = "ECR repository URL. Tag and push your Docker image here before deploying."
  value       = aws_ecr_repository.backend.repository_url
}

output "lambda_function_name" {
  description = "Lambda function name (useful for aws lambda invoke or log tailing)."
  value       = aws_lambda_function.backend.function_name
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group name for Lambda logs."
  value       = aws_cloudwatch_log_group.backend.name
}
