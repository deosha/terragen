# Lambda Function with API Gateway

This Terraform configuration creates a production-ready AWS Lambda function integrated with API Gateway, providing a complete serverless API solution.

## Architecture

```
Internet → API Gateway → Lambda Function → CloudWatch Logs
```

## Features

- ✅ **AWS Lambda Function**: Serverless compute with configurable runtime and memory
- ✅ **API Gateway REST API**: RESTful API with proxy integration
- ✅ **CORS Support**: Cross-Origin Resource Sharing with configurable origins and methods
- ✅ **CloudWatch Logging**: Comprehensive logging for both Lambda and API Gateway
- ✅ **IAM Security**: Least-privilege IAM roles and policies
- ✅ **Sample Code**: Ready-to-use Python Lambda function
- ✅ **CI/CD Pipeline**: GitHub Actions workflow for automated deployment
- ✅ **Security Scanning**: Trivy vulnerability scanning integrated
- ✅ **Auto-naming**: Automatic resource naming with random suffixes

## Quick Start

1. **Prerequisites**
   ```bash
   # Install Terraform >= 1.0
   terraform --version
   
   # Configure AWS credentials
   aws configure
   ```

2. **Deploy the Infrastructure**
   ```bash
   # Clone and navigate to the project
   cd /Users/deo/terragen/test-learn
   
   # Initialize Terraform
   terraform init
   
   # Review the plan
   terraform plan
   
   # Deploy the infrastructure
   terraform apply
   ```

3. **Test the API**
   ```bash
   # Get the API Gateway URL from Terraform output
   API_URL=$(terraform output -raw api_gateway_invoke_url)
   
   # Test GET request
   curl $API_URL
   
   # Test POST request
   curl -X POST $API_URL \
     -H "Content-Type: application/json" \
     -d '{"message": "Hello from API!"}'
   ```

## Configuration

### Basic Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `project_name` | Name of the project | `terragen-lambda-api` | No |
| `environment` | Environment name (dev, staging, prod) | `dev` | No |
| `aws_region` | AWS region for resources | `us-east-1` | No |

### Lambda Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `lambda_function_name` | Lambda function name (auto-generated if empty) | `""` | No |
| `lambda_runtime` | Runtime for Lambda function | `python3.9` | No |
| `lambda_memory_size` | Memory allocation in MB (128-10240) | `256` | No |
| `lambda_timeout` | Timeout in seconds (1-900) | `30` | No |

### API Gateway Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `api_gateway_name` | API Gateway name (auto-generated if empty) | `""` | No |
| `api_gateway_stage_name` | Stage name for deployment | `dev` | No |

### Logging Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `enable_logging` | Enable CloudWatch logging | `true` | No |
| `log_retention_days` | Log retention period in days | `14` | No |

### CORS Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `enable_cors` | Enable CORS support | `true` | No |
| `cors_origins` | Allowed CORS origins | `["*"]` | No |
| `cors_methods` | Allowed HTTP methods | `["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"]` | No |
| `cors_headers` | Allowed headers | `["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"]` | No |

## Outputs

| Output | Description |
|--------|-------------|
| `lambda_function_name` | Name of the Lambda function |
| `lambda_function_arn` | ARN of the Lambda function |
| `api_gateway_rest_api_id` | ID of the REST API |
| `api_gateway_invoke_url` | URL to invoke the API Gateway |
| `lambda_logs_group_name` | Name of the Lambda CloudWatch log group |
| `api_gateway_logs_group_name` | Name of the API Gateway CloudWatch log group |

## Example Usage

### Custom Configuration

Create a `terraform.tfvars` file:

```hcl
project_name = "my-serverless-api"
environment  = "production"

# Lambda settings
lambda_runtime     = "python3.11"
lambda_memory_size = 512
lambda_timeout     = 60

# API Gateway settings
api_gateway_stage_name = "prod"

# Logging settings
enable_logging     = true
log_retention_days = 30

# CORS settings
enable_cors  = true
cors_origins = ["https://mydomain.com", "https://www.mydomain.com"]

# Additional tags
tags = {
  Owner       = "platform-team"
  CostCenter  = "engineering"
  Application = "customer-api"
}
```

### Production Deployment

```bash
# Set production environment
export TF_VAR_environment=prod
export TF_VAR_log_retention_days=90

# Deploy with production settings
terraform apply -var-file="production.tfvars"
```

## Lambda Function

The included sample Lambda function (`lambda_function.py`) provides:

- HTTP method routing (GET, POST, etc.)
- JSON request/response handling
- CORS headers
- Comprehensive logging
- Error handling

### Customizing the Lambda Function

1. **Replace the function code**:
   ```bash
   # Edit the generated lambda_function.py
   nano lambda_function.py
   
   # Redeploy
   terraform apply
   ```

2. **Add dependencies**:
   ```bash
   # Create requirements.txt
   echo "requests==2.31.0" > requirements.txt
   
   # Package with dependencies
   pip install -r requirements.txt -t ./
   zip -r lambda_function.zip . -x "*.tf*" "*.md" ".git*"
   ```

## API Endpoints

The API Gateway provides the following endpoints:

- **GET /**: Returns a welcome message
- **POST /**: Accepts JSON data and returns confirmation
- **ANY /{proxy+}**: Handles all HTTP methods for any path

### Example Requests

```bash
# Health check
curl https://your-api-id.execute-api.us-east-1.amazonaws.com/dev

# Create resource
curl -X POST https://your-api-id.execute-api.us-east-1.amazonaws.com/dev/users \
  -H "Content-Type: application/json" \
  -d '{"name": "John Doe", "email": "john@example.com"}'

# Custom path
curl https://your-api-id.execute-api.us-east-1.amazonaws.com/dev/custom/path
```

## Monitoring and Logging

### CloudWatch Logs

- **Lambda Logs**: `/aws/lambda/{function-name}`
- **API Gateway Logs**: `/aws/apigateway/{api-name}`

### Monitoring Commands

```bash
# View recent Lambda logs
aws logs tail /aws/lambda/$(terraform output -raw lambda_function_name) --follow

# View API Gateway logs
aws logs tail /aws/apigateway/$(terraform output -raw api_gateway_rest_api_name) --follow

# Check Lambda metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=$(terraform output -raw lambda_function_name) \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum
```

## Security

### IAM Policies

The configuration implements least-privilege access:

- **Lambda Execution Role**: Basic execution + CloudWatch logs
- **API Gateway Role**: CloudWatch logs publishing
- **Lambda Permissions**: Allows API Gateway invocation only

### Security Best Practices

- ✅ No hardcoded secrets or credentials
- ✅ Encrypted CloudWatch logs
- ✅ Least-privilege IAM roles
- ✅ Regional API Gateway endpoint
- ✅ CORS properly configured
- ✅ Input validation in Lambda function

## CI/CD Pipeline

The included GitHub Actions workflow (`.github/workflows/terraform.yml`) provides:

- **Automated Testing**: Format, validate, and plan on PR
- **Automated Deployment**: Apply changes on main branch
- **Security Scanning**: Trivy vulnerability scanning
- **Multi-Environment**: Support for development and production

### Setting up CI/CD

1. **Add GitHub Secrets**:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`

2. **Configure Environments**:
   - Create `development` and `production` environments in GitHub
   - Add environment-specific protection rules

## Troubleshooting

### Common Issues

1. **Lambda timeout errors**:
   ```hcl
   lambda_timeout = 60  # Increase timeout
   ```

2. **Memory issues**:
   ```hcl
   lambda_memory_size = 512  # Increase memory
   ```

3. **CORS issues**:
   ```hcl
   cors_origins = ["https://yourdomain.com"]  # Specific origins
   ```

4. **Permission errors**:
   ```bash
   # Check IAM role permissions
   aws iam get-role-policy --role-name $(terraform output -raw lambda_role_name) --policy-name lambda-logs-policy
   ```

### Logs and Debugging

```bash
# Check Terraform logs
export TF_LOG=DEBUG
terraform apply

# Check AWS CLI configuration
aws sts get-caller-identity

# Validate API Gateway
aws apigateway test-invoke-method \
  --rest-api-id $(terraform output -raw api_gateway_rest_api_id) \
  --resource-id $(terraform output -raw api_gateway_resource_id) \
  --http-method GET
```

## Cost Optimization

- **Lambda**: Pay per request and execution time
- **API Gateway**: Pay per API call
- **CloudWatch**: Pay for log ingestion and storage

### Estimated Monthly Costs (us-east-1)

| Usage | Lambda | API Gateway | CloudWatch | Total |
|-------|---------|-------------|------------|-------|
| 1K requests/month | $0.00 | $0.01 | $0.01 | $0.02 |
| 100K requests/month | $0.02 | $0.35 | $0.10 | $0.47 |
| 1M requests/month | $0.20 | $3.50 | $1.00 | $4.70 |

## Cleanup

To destroy all resources:

```bash
terraform destroy
```

**Warning**: This will permanently delete all resources and data.

## Support

- **Documentation**: [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- **AWS Lambda**: [Developer Guide](https://docs.aws.amazon.com/lambda/latest/dg/)
- **API Gateway**: [Developer Guide](https://docs.aws.amazon.com/apigateway/latest/developerguide/)

---

Generated by TerraGen - Infrastructure as Code Generator