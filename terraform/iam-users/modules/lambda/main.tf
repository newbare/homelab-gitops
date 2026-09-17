# ============================================
# Lambda Function
# ============================================
# NOTA: O ZIP é gerado pelo build.sh (que instala deps).
# Rodar ./src/build.sh ANTES do terraform apply.

resource "aws_lambda_function" "this" {
  function_name = "${var.project_name}-${var.environment}-process-users"
  role          = var.lambda_role_arn
  handler       = var.lambda_handler
  runtime       = var.lambda_runtime
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size

  filename         = "${path.module}/src/lambda.zip"
  source_code_hash = filebase64sha256("${path.module}/src/lambda.zip")

  environment {
    variables = {
      IDENTITY_STORE_ID = var.identity_store_id
      SSO_INSTANCE_ARN  = var.sso_instance_arn
      BUCKET_NAME       = var.bucket_name
      ENVIRONMENT       = var.environment
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    Module      = "lambda"
  }
}

# ============================================
# Permissão para S3 invocar a Lambda
# ============================================
resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = var.bucket_arn
}

# ============================================
# S3 Event Notification
# ============================================
resource "aws_s3_bucket_notification" "lambda_trigger" {
  bucket = var.bucket_name

  lambda_function {
    lambda_function_arn = aws_lambda_function.this.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".xlsx"
  }

  depends_on = [aws_lambda_permission.allow_s3]
}
