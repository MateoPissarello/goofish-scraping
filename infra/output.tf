output "sqs_queue_url" {
  value = aws_sqs_queue.main.url
}

output "sqs_queue_arn" {
  value = aws_sqs_queue.main.arn
}

output "dlq_url" {
  value = aws_sqs_queue.dlq.url
}

output "dynamodb_table_name" {
  value = aws_dynamodb_table.scraped_urls.name
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "ecs_service_name" {
  value = aws_ecs_service.worker.name
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.worker.name
}
output "datasets_bucket_name" {
  value = aws_s3_bucket.datasets.bucket
}
