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

# ============================================
# IAM Role + Policy — publisher do TechDocs
# ============================================
# O Backstage publica E lê o site gerado direto no S3. Em vez de dar isso com
# uma credencial onipotente, este papel tem SÓ as ações que a doc exige, e SÓ
# no bucket do TechDocs.
#
# Ações — mínimo documentado em
# https://backstage.io/docs/features/techdocs/using-cloud-storage
#   escrita: s3:ListBucket, s3:PutObject, s3:DeleteObject, s3:DeleteObjectVersion
#   leitura: s3:ListBucket, s3:GetObject
# `s3:DeleteObjectVersion` consta na doc por causa de re-publicação; aqui ele é
# ainda mais necessário porque o bucket tem VERSIONAMENTO ligado.
#
# Trust `pods.eks.amazonaws.com` = EKS Pod Identity: é assim que o Pod recebe
# credencial TEMPORÁRIA, sem access key de longa duração — o que a AWS recomenda
# no lugar de chave estática:
# https://docs.aws.amazon.com/general/latest/gr/aws-access-keys-best-practices.html
# ("use temporary security credentials (such as IAM roles) instead of creating
#  long-term credentials like access keys")
#
# ⚠️ FALTA UMA PEÇA, e ela depende de infra que não existe aqui: a ASSOCIAÇÃO
# (`aws_eks_pod_identity_association`) exige um cluster EKS real. Sem ela o papel
# existe mas ninguém o assume — por isso o Floci continua usando a chave do
# Secret `backstage-techdocs-s3`. Isto é preparação para a AWS real, não
# permissão em uso hoje. Não finjo que é.
resource "aws_iam_role" "techdocs_publisher" {
  name = "${var.project_name}-${var.environment}-techdocs-publisher"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "pods.eks.amazonaws.com"
        }
        Action = [
          "sts:AssumeRole",
          "sts:TagSession"
        ]
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

resource "aws_iam_role_policy" "techdocs_publisher" {
  name = "${var.project_name}-${var.environment}-techdocs-publisher-policy"
  role = aws_iam_role.techdocs_publisher.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "TechDocsListBucket"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = var.techdocs_bucket_arn
      },
      {
        Sid      = "TechDocsObjects"
        Effect   = "Allow"
        Action   = var.techdocs_publisher_object_actions
        Resource = "${var.techdocs_bucket_arn}/*"
      }
    ]
  })
}
