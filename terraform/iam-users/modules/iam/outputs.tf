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
