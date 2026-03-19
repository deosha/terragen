# Project Configuration
project_name = "terragen-lambda-api"
environment  = "dev"
aws_region   = "us-east-1"

# Lambda Configuration
lambda_runtime     = "python3.9"
lambda_memory_size = 256
lambda_timeout     = 30

# API Gateway Configuration
api_gateway_stage_name = "dev"

# Logging Configuration
enable_logging     = true
log_retention_days = 14

# CORS Configuration
enable_cors  = true
cors_origins = ["*"]
cors_methods = ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"]
cors_headers = ["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"]

# Additional Tags
tags = {
  Owner       = "terraform"
  CostCenter  = "engineering"
  Application = "lambda-api-gateway"
}