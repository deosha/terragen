variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "terragen-lambda-api"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "lambda_function_name" {
  description = "Name of the Lambda function (leave empty for auto-generated name)"
  type        = string
  default     = ""
}

variable "lambda_runtime" {
  description = "Runtime for the Lambda function"
  type        = string
  default     = "python3.9"
  validation {
    condition = contains([
      "python3.8", "python3.9", "python3.10", "python3.11",
      "nodejs18.x", "nodejs20.x",
      "java8", "java11", "java17", "java21",
      "dotnet6", "dotnet8",
      "go1.x"
    ], var.lambda_runtime)
    error_message = "Lambda runtime must be a valid AWS Lambda runtime."
  }
}

variable "lambda_memory_size" {
  description = "Amount of memory in MB for Lambda function"
  type        = number
  default     = 256
  validation {
    condition     = var.lambda_memory_size >= 128 && var.lambda_memory_size <= 10240
    error_message = "Lambda memory size must be between 128 MB and 10,240 MB."
  }
}

variable "lambda_timeout" {
  description = "Timeout in seconds for Lambda function"
  type        = number
  default     = 30
  validation {
    condition     = var.lambda_timeout >= 1 && var.lambda_timeout <= 900
    error_message = "Lambda timeout must be between 1 and 900 seconds."
  }
}

variable "api_gateway_name" {
  description = "Name of the API Gateway (leave empty for auto-generated name)"
  type        = string
  default     = ""
}

variable "api_gateway_stage_name" {
  description = "Stage name for API Gateway deployment"
  type        = string
  default     = "dev"
}

variable "enable_logging" {
  description = "Enable CloudWatch logging for API Gateway and Lambda"
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "Number of days to retain CloudWatch logs"
  type        = number
  default     = 14
  validation {
    condition = contains([
      1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653
    ], var.log_retention_days)
    error_message = "Log retention days must be a valid CloudWatch logs retention period."
  }
}

variable "enable_cors" {
  description = "Enable CORS for API Gateway"
  type        = bool
  default     = true
}

variable "cors_origins" {
  description = "List of allowed CORS origins"
  type        = list(string)
  default     = ["*"]
}

variable "cors_methods" {
  description = "List of allowed CORS methods"
  type        = list(string)
  default     = ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"]
}

variable "cors_headers" {
  description = "List of allowed CORS headers"
  type        = list(string)
  default     = ["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"]
}

variable "tags" {
  description = "Additional tags to apply to resources"
  type        = map(string)
  default     = {}
}