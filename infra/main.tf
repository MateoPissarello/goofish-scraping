terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# -------------------------
# Networking (default VPC)
# -------------------------
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Security group for Fargate tasks (outbound only).
resource "aws_security_group" "ecs_tasks" {
  name        = "${var.project_name}-ecs-tasks-sg"
  description = "ECS tasks security group"
  vpc_id      = data.aws_vpc.default.id

  # No inbound needed.
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# -------------------------
# Secrets Manager
# -------------------------

resource "aws_secretsmanager_secret" "proxy" {
  name = "${var.project_name}/proxy"

  description = "Credenciales de proxy para scraping Goofish"

  tags = {
    Project = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "proxy" {
  secret_id = aws_secretsmanager_secret.proxy.id

  secret_string = jsonencode({
    PROXY_SERVER = var.proxy_server
    PROXY_USER   = var.proxy_user
    PROXY_PASS   = var.proxy_pass
  })
}


# -------------------------
# DynamoDB (idempotency)
# -------------------------
resource "aws_dynamodb_table" "scraped_urls" { # Table for caching scraped URLs
  name         = "${var.project_name}-scraped-urls"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "url_hash"

  attribute {
    name = "url_hash"
    type = "S"
  }

  tags = {
    Project = var.project_name
  }
}

resource "aws_dynamodb_table" "parsed_urls" { # Table for storing parsed items
  name         = "${var.project_name}-parsed-items"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "ITEM_ID"

  attribute {
    name = "ITEM_ID"
    type = "S"
  }

  tags = {
    Project = var.project_name
  }
}



# -------------------------
# SQS + DLQ
# -------------------------
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.project_name}-dlq"
  message_retention_seconds = 1209600 # 14 days
}

resource "aws_sqs_queue" "main" {
  name                       = "${var.project_name}-queue"
  visibility_timeout_seconds = var.sqs_visibility_timeout_seconds

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

# -------------------------
# CloudWatch Logs
# -------------------------
resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${var.project_name}-worker"
  retention_in_days = 14
}

# -------------------------
# IAM for ECS task
# -------------------------
data "aws_iam_policy_document" "task_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

# Execution role (pull image, write logs, etc.)
resource "aws_iam_role" "ecs_execution_role" {
  name               = "${var.project_name}-ecs-exec-role"
  assume_role_policy = data.aws_iam_policy_document.task_assume_role.json
}

resource "aws_iam_role_policy_attachment" "ecs_exec_attach" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Task role (SQS + DynamoDB)
resource "aws_iam_role" "ecs_task_role" {
  name               = "${var.project_name}-ecs-task-role"
  assume_role_policy = data.aws_iam_policy_document.task_assume_role.json
}

data "aws_iam_policy_document" "task_policy" {
  statement {
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ChangeMessageVisibility"
    ]
    resources = [aws_sqs_queue.main.arn]
  }

  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem"
    ]
    resources = [
      aws_dynamodb_table.scraped_urls.arn,
      aws_dynamodb_table.parsed_urls.arn
    ]
  }

}

data "aws_iam_policy_document" "ecs_exec_secrets_policy" {
  statement {
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue"
    ]
    resources = [
      aws_secretsmanager_secret.proxy.arn
    ]
  }
}

resource "aws_iam_policy" "ecs_exec_secrets_policy" {
  name   = "${var.project_name}-ecs-exec-secrets"
  policy = data.aws_iam_policy_document.ecs_exec_secrets_policy.json
}
resource "aws_iam_role_policy_attachment" "ecs_exec_secrets_attach" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = aws_iam_policy.ecs_exec_secrets_policy.arn
}


resource "aws_iam_policy" "ecs_task_policy" {
  name   = "${var.project_name}-ecs-task-policy"
  policy = data.aws_iam_policy_document.task_policy.json
}

resource "aws_iam_role_policy_attachment" "task_policy_attach" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.ecs_task_policy.arn
}

# ===============================================
# S3
# ==============================================
resource "aws_s3_bucket" "datasets" {
  bucket = "${var.project_name}-datasets"
}

resource "aws_s3_bucket_notification" "datasets_notify" {
  bucket = aws_s3_bucket.datasets.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.s3_to_sqs.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".csv"
  }

  depends_on = [aws_lambda_permission.allow_s3]
}


data "aws_iam_policy_document" "lambda_assume" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "lambda_role" {
  name               = "${var.project_name}-s3-to-sqs-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "lambda_policy" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject"
    ]
    resources = ["${aws_s3_bucket.datasets.arn}/*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "sqs:SendMessage"
    ]
    resources = [aws_sqs_queue.main.arn]
  }

  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "lambda_policy" {
  name   = "${var.project_name}-s3-to-sqs-policy"
  policy = data.aws_iam_policy_document.lambda_policy.json
}

resource "aws_iam_role_policy_attachment" "lambda_policy_attach" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}


resource "aws_lambda_function" "s3_to_sqs" {
  function_name = "${var.project_name}-s3-to-sqs"
  role          = aws_iam_role.lambda_role.arn
  handler       = "s3_to_sqs.handler"
  runtime       = "python3.11"
  timeout       = 60

  filename         = "${path.module}/../lambda/s3_to_sqs.zip"
  source_code_hash = filebase64sha256("${path.module}/../lambda/s3_to_sqs.zip")

  environment {
    variables = {
      SQS_QUEUE_URL = aws_sqs_queue.main.url
    }
  }
}

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.s3_to_sqs.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.datasets.arn
}




# -------------------------
# ECS Cluster + Task + Service (Fargate)
# -------------------------
resource "aws_ecs_cluster" "this" {
  name = "${var.project_name}-cluster"
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.project_name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.worker_cpu)
  memory                   = tostring(var.worker_memory)

  execution_role_arn = aws_iam_role.ecs_execution_role.arn
  task_role_arn      = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = "worker"
      image     = var.ecr_image_url
      essential = true

      environment = [
        { name = "SQS_QUEUE_URL", value = aws_sqs_queue.main.url },
        { name = "GOOFISH_SCRAPED_URLS_TABLE", value = aws_dynamodb_table.scraped_urls.name },
        { name = "GOOFISH_PARSED_URLS_TABLE", value = aws_dynamodb_table.parsed_urls.name },
        { name = "AWS_REGION", value = var.aws_region }
      ]

      secrets = [
        {
          name      = "PROXY_SERVER"
          valueFrom = "${aws_secretsmanager_secret.proxy.arn}:PROXY_SERVER::"
        },
        {
          name      = "PROXY_USER"
          valueFrom = "${aws_secretsmanager_secret.proxy.arn}:PROXY_USER::"
        },
        {
          name      = "PROXY_PASS"
          valueFrom = "${aws_secretsmanager_secret.proxy.arn}:PROXY_PASS::"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.worker.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "ecs"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "worker" {
  name            = "${var.project_name}-worker-svc"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true
  }

  # Evita re-deploys innecesarios por diferencias de desired_count cuando autoscaling actúa
  lifecycle {
    ignore_changes = [desired_count]
  }
}

# -------------------------
# Auto Scaling basado en SQS messages visible
# -------------------------

resource "aws_appautoscaling_target" "ecs" {
  max_capacity       = var.max_capacity
  min_capacity       = var.min_capacity
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.worker.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_cloudwatch_metric_alarm" "scale_out" {
  alarm_name          = "${var.project_name}-scale-out"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Average"
  threshold           = 10
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.main.name
  }

  alarm_actions = [aws_appautoscaling_policy.scale_out.arn]
}

resource "aws_appautoscaling_policy" "scale_out" {
  name               = "${var.project_name}-scale-out-policy"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.ecs.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs.service_namespace

  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    cooldown                = 60
    metric_aggregation_type = "Average"

    # (métrica - threshold) entra en estos rangos

    # 10-50 msgs => +1
    step_adjustment {
      metric_interval_lower_bound = 0
      metric_interval_upper_bound = 40
      scaling_adjustment          = 1
    }

    # 50-200 msgs => +5
    step_adjustment {
      metric_interval_lower_bound = 40
      metric_interval_upper_bound = 190
      scaling_adjustment          = 5
    }

    # 200+ msgs => +10
    step_adjustment {
      metric_interval_lower_bound = 190
      scaling_adjustment          = 10
    }


  }
}


resource "aws_cloudwatch_metric_alarm" "scale_in" {
  alarm_name          = "${var.project_name}-scale-in"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 3
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Average"
  threshold           = 5
  treat_missing_data  = "breaching"

  dimensions = {
    QueueName = aws_sqs_queue.main.name
  }

  alarm_actions = [aws_appautoscaling_policy.scale_in.arn]
}

resource "aws_appautoscaling_policy" "scale_in" {
  name               = "${var.project_name}-scale-in-policy"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.ecs.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs.service_namespace

  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    cooldown                = 120
    metric_aggregation_type = "Average"

    step_adjustment {
      metric_interval_upper_bound = 0
      scaling_adjustment          = -1
    }
  }
}



