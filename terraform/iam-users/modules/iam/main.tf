# ============================================
# IAM Role para a Lambda
# ============================================
resource "aws_iam_role" "lambda" {
  name = "${var.project_name}-${var.environment}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    Module      = "iam"
  }
}

# ============================================
# IAM Policy da Lambda
# ============================================
resource "aws_iam_role_policy" "lambda" {
  name = "${var.project_name}-${var.environment}-lambda-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3ReadUsersXlsx"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          var.bucket_arn,
          "${var.bucket_arn}/*"
        ]
      },
      {
        Sid    = "S3WriteCatalog"
        Effect = "Allow"
        Action = [
          "s3:PutObject"
        ]
        Resource = "${var.bucket_arn}/*"
      },
      {
        Sid    = "IAMCreateUsersAndGroups"
        Effect = "Allow"
        Action = [
          "iam:CreateUser",
          "iam:GetUser",
          "iam:CreateGroup",
          "iam:GetGroup",
          "iam:AddUserToGroup",
          "iam:ListUsers",
          "iam:ListGroups",
          "iam:TagUser",
          "iam:TagGroup"
        ]
        Resource = "*"
      },
      {
        Sid    = "IdentityStoreCreateUsersAndGroups"
        Effect = "Allow"
        Action = [
          "identitystore:CreateUser",
          "identitystore:CreateGroup",
          "identitystore:CreateGroupMembership",
          "identitystore:ListUsers",
          "identitystore:ListGroups",
          "identitystore:DescribeUser",
          "identitystore:DescribeGroup"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      }
    ]
  })
}
