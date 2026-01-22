variable "project_name" {
  type    = string
  default = "iceberg-scraper"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

# URL completa de imagen (ECR), ejemplo:
# 123456789012.dkr.ecr.us-east-1.amazonaws.com/iceberg-scraper-worker:latest
variable "ecr_image_url" {
  type = string
}

variable "desired_count" {
  type    = number
  default = 1
}

variable "min_capacity" {
  type    = number
  default = 1
}

variable "max_capacity" {
  type    = number
  default = 20
}

# Umbral “simple” para escalar: si hay más de X mensajes visibles, escala.
variable "scale_out_threshold" {
  type    = number
  default = 50
}

variable "scale_in_threshold" {
  type    = number
  default = 10
}

# Tiempo máximo esperado por URL (para visibilidad SQS). Ajusta según tu scraping real.
variable "sqs_visibility_timeout_seconds" {
  type    = number
  default = 120
}

variable "worker_cpu" {
  type    = number
  default = 512
}

variable "worker_memory" {
  type    = number
  default = 1024
}
