output "bucket_names" {
  description = "Nomes físicos dos buckets, por finalidade"
  value       = { for k, b in aws_s3_bucket.this : k => b.bucket }
}

output "bucket_arns" {
  description = "ARNs dos buckets, por finalidade"
  value       = { for k, b in aws_s3_bucket.this : k => b.arn }
}

output "bucket_ids" {
  description = "IDs dos buckets, por finalidade"
  value       = { for k, b in aws_s3_bucket.this : k => b.id }
}
