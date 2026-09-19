output "lambda_role_arn" {
  description = "ARN da IAM Role da Lambda"
  value       = aws_iam_role.lambda.arn
}

output "lambda_role_name" {
  description = "Nome da IAM Role da Lambda"
  value       = aws_iam_role.lambda.name
}

output "lambda_policy_name" {
  description = "Nome da IAM Policy da Lambda"
  value       = aws_iam_role_policy.lambda.name
}

output "techdocs_publisher_role_arn" {
  description = "ARN da IAM Role do publisher do TechDocs (EKS Pod Identity)"
  value       = aws_iam_role.techdocs_publisher.arn
}

output "techdocs_publisher_policy_name" {
  description = "Nome da IAM Policy do publisher do TechDocs"
  value       = aws_iam_role_policy.techdocs_publisher.name
}
