output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.main.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.main.arn
}

output "lambda_function_invoke_arn" {
  description = "Invoke ARN of the Lambda function"
  value       = aws_lambda_function.main.invoke_arn
}

output "lambda_function_version" {
  description = "Latest published version of Lambda function"
  value       = aws_lambda_function.main.version
}

output "lambda_function_last_modified" {
  description = "Date Lambda function was last modified"
  value       = aws_lambda_function.main.last_modified
}

output "lambda_function_source_code_size" {
  description = "Size in bytes of the Lambda function .zip file"
  value       = aws_lambda_function.main.source_code_size
}

output "lambda_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = aws_iam_role.lambda_role.arn
}

output "lambda_role_name" {
  description = "Name of the Lambda execution role"
  value       = aws_iam_role.lambda_role.name
}

output "api_gateway_rest_api_id" {
  description = "ID of the REST API"
  value       = aws_api_gateway_rest_api.main.id
}

output "api_gateway_rest_api_arn" {
  description = "ARN of the REST API"
  value       = aws_api_gateway_rest_api.main.arn
}

output "api_gateway_rest_api_name" {
  description = "Name of the REST API"
  value       = aws_api_gateway_rest_api.main.name
}

output "api_gateway_execution_arn" {
  description = "Execution ARN of the REST API"
  value       = aws_api_gateway_rest_api.main.execution_arn
}

output "api_gateway_stage_name" {
  description = "Name of the API Gateway stage"
  value       = aws_api_gateway_stage.main.stage_name
}

output "api_gateway_stage_arn" {
  description = "ARN of the API Gateway stage"
  value       = aws_api_gateway_stage.main.arn
}

output "api_gateway_invoke_url" {
  description = "URL to invoke the API Gateway"
  value       = aws_api_gateway_stage.main.invoke_url
}

output "api_gateway_deployment_id" {
  description = "ID of the API Gateway deployment"
  value       = aws_api_gateway_deployment.main.id
}

output "lambda_logs_group_name" {
  description = "Name of the Lambda CloudWatch log group"
  value       = var.enable_logging ? aws_cloudwatch_log_group.lambda_logs[0].name : null
}

output "lambda_logs_group_arn" {
  description = "ARN of the Lambda CloudWatch log group"
  value       = var.enable_logging ? aws_cloudwatch_log_group.lambda_logs[0].arn : null
}

output "api_gateway_logs_group_name" {
  description = "Name of the API Gateway CloudWatch log group"
  value       = var.enable_logging ? aws_cloudwatch_log_group.api_gateway_logs[0].name : null
}

output "api_gateway_logs_group_arn" {
  description = "ARN of the API Gateway CloudWatch log group"
  value       = var.enable_logging ? aws_cloudwatch_log_group.api_gateway_logs[0].arn : null
}

output "cors_enabled" {
  description = "Whether CORS is enabled for the API Gateway"
  value       = var.enable_cors
}

output "logging_enabled" {
  description = "Whether logging is enabled for Lambda and API Gateway"
  value       = var.enable_logging
}

output "log_retention_days" {
  description = "Number of days CloudWatch logs are retained"
  value       = var.log_retention_days
}