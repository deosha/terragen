# Generate random suffix for resource names
resource "random_string" "resource_suffix" {
  length  = 8
  lower   = true
  upper   = false
  special = false
}

# Local values for resource naming
locals {
  lambda_function_name = var.lambda_function_name != "" ? var.lambda_function_name : "${var.project_name}-function-${random_string.resource_suffix.result}"
  api_gateway_name     = var.api_gateway_name != "" ? var.api_gateway_name : "${var.project_name}-api-${random_string.resource_suffix.result}"
}

# Create a sample Lambda function code
resource "local_file" "lambda_code" {
  content  = <<EOF
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Sample Lambda function for API Gateway integration
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Extract HTTP method and path
    http_method = event.get('httpMethod', 'UNKNOWN')
    resource_path = event.get('resource', '/')
    
    # Sample response based on method
    if http_method == 'GET':
        response_body = {
            'message': 'Hello from Lambda!',
            'method': http_method,
            'path': resource_path,
            'timestamp': context.aws_request_id
        }
    elif http_method == 'POST':
        body = json.loads(event.get('body', '{}'))
        response_body = {
            'message': 'Data received successfully!',
            'received_data': body,
            'method': http_method,
            'path': resource_path
        }
    else:
        response_body = {
            'message': f'Method {http_method} not specifically handled',
            'method': http_method,
            'path': resource_path
        }
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
        },
        'body': json.dumps(response_body, indent=2)
    }
EOF
  filename = "${path.module}/lambda_function.py"
}

# Create deployment package
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = local_file.lambda_code.filename
  output_path = "${path.module}/lambda_function.zip"
  depends_on  = [local_file.lambda_code]
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "lambda_logs" {
  count = var.enable_logging ? 1 : 0

  name              = "/aws/lambda/${local.lambda_function_name}"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Name = "${local.lambda_function_name}-logs"
  })
}

# IAM role for Lambda
resource "aws_iam_role" "lambda_role" {
  name = "${local.lambda_function_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(var.tags, {
    Name = "${local.lambda_function_name}-role"
  })
}

# IAM policy for Lambda basic execution
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Additional IAM policy for CloudWatch logs (if logging enabled)
resource "aws_iam_role_policy" "lambda_logs_policy" {
  count = var.enable_logging ? 1 : 0

  name = "${local.lambda_function_name}-logs-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:*:log-group:/aws/lambda/${local.lambda_function_name}:*"
      }
    ]
  })
}

# Lambda function
resource "aws_lambda_function" "main" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = local.lambda_function_name
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = var.lambda_runtime
  memory_size      = var.lambda_memory_size
  timeout          = var.lambda_timeout
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_cloudwatch_log_group.lambda_logs,
  ]

  tags = merge(var.tags, {
    Name = local.lambda_function_name
  })
}

# API Gateway REST API
resource "aws_api_gateway_rest_api" "main" {
  name        = local.api_gateway_name
  description = "API Gateway for ${var.project_name}"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = merge(var.tags, {
    Name = local.api_gateway_name
  })
}

# API Gateway Resource (proxy)
resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "{proxy+}"
}

# API Gateway Method (ANY for proxy)
resource "aws_api_gateway_method" "proxy_any" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "ANY"
  authorization = "NONE"
}

# API Gateway Method (ANY for root)
resource "aws_api_gateway_method" "root_any" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_rest_api.main.root_resource_id
  http_method   = "ANY"
  authorization = "NONE"
}

# API Gateway Integration (proxy)
resource "aws_api_gateway_integration" "proxy_integration" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.proxy.id
  http_method = aws_api_gateway_method.proxy_any.http_method

  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.main.invoke_arn
}

# API Gateway Integration (root)
resource "aws_api_gateway_integration" "root_integration" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_rest_api.main.root_resource_id
  http_method = aws_api_gateway_method.root_any.http_method

  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.main.invoke_arn
}

# CORS configuration (if enabled)
resource "aws_api_gateway_method" "proxy_options" {
  count = var.enable_cors ? 1 : 0

  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "proxy_options_integration" {
  count = var.enable_cors ? 1 : 0

  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.proxy.id
  http_method = aws_api_gateway_method.proxy_options[0].http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = jsonencode({
      statusCode = 200
    })
  }
}

resource "aws_api_gateway_method_response" "proxy_options_200" {
  count = var.enable_cors ? 1 : 0

  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.proxy.id
  http_method = aws_api_gateway_method.proxy_options[0].http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }

  response_models = {
    "application/json" = "Empty"
  }
}

resource "aws_api_gateway_integration_response" "proxy_options_integration_response" {
  count = var.enable_cors ? 1 : 0

  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.proxy.id
  http_method = aws_api_gateway_method.proxy_options[0].http_method
  status_code = aws_api_gateway_method_response.proxy_options_200[0].status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'${join(",", var.cors_headers)}'"
    "method.response.header.Access-Control-Allow-Methods" = "'${join(",", var.cors_methods)}'"
    "method.response.header.Access-Control-Allow-Origin"  = "'${join(",", var.cors_origins)}'"
  }
}

# Lambda permissions for API Gateway
resource "aws_lambda_permission" "api_gateway_invoke" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.main.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

# CloudWatch Log Group for API Gateway
resource "aws_cloudwatch_log_group" "api_gateway_logs" {
  count = var.enable_logging ? 1 : 0

  name              = "/aws/apigateway/${local.api_gateway_name}"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Name = "${local.api_gateway_name}-logs"
  })
}

# API Gateway Account (for CloudWatch logging)
resource "aws_api_gateway_account" "main" {
  count = var.enable_logging ? 1 : 0

  cloudwatch_role_arn = aws_iam_role.api_gateway_cloudwatch_role[0].arn
}

# IAM role for API Gateway CloudWatch logging
resource "aws_iam_role" "api_gateway_cloudwatch_role" {
  count = var.enable_logging ? 1 : 0

  name = "${local.api_gateway_name}-cloudwatch-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "apigateway.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(var.tags, {
    Name = "${local.api_gateway_name}-cloudwatch-role"
  })
}

# IAM policy attachment for API Gateway CloudWatch
resource "aws_iam_role_policy_attachment" "api_gateway_cloudwatch_logs" {
  count = var.enable_logging ? 1 : 0

  role       = aws_iam_role.api_gateway_cloudwatch_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs"
}

# API Gateway Stage
resource "aws_api_gateway_stage" "main" {
  deployment_id = aws_api_gateway_deployment.main.id
  rest_api_id   = aws_api_gateway_rest_api.main.id
  stage_name    = var.api_gateway_stage_name

  dynamic "access_log_settings" {
    for_each = var.enable_logging ? [1] : []
    content {
      destination_arn = aws_cloudwatch_log_group.api_gateway_logs[0].arn
      format = jsonencode({
        requestId      = "$context.requestId"
        requestTime    = "$context.requestTime"
        httpMethod     = "$context.httpMethod"
        resourcePath   = "$context.resourcePath"
        status         = "$context.status"
        responseLength = "$context.responseLength"
        responseTime   = "$context.responseTime"
      })
    }
  }

  depends_on = [aws_api_gateway_account.main]

  tags = merge(var.tags, {
    Name = "${local.api_gateway_name}-${var.api_gateway_stage_name}"
  })
}

# API Gateway Deployment
resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.proxy.id,
      aws_api_gateway_method.proxy_any.id,
      aws_api_gateway_method.root_any.id,
      aws_api_gateway_integration.proxy_integration.id,
      aws_api_gateway_integration.root_integration.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_method.proxy_any,
    aws_api_gateway_method.root_any,
    aws_api_gateway_integration.proxy_integration,
    aws_api_gateway_integration.root_integration,
  ]
}