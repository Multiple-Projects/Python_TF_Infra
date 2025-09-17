provider "aws" {
  region = "us-east-1"
}

resource "aws_lb" "example" {
  name               = "django-lb"
  internal           = false
  load_balancer_type = "application"
  subnets            = ["subnet-xxxxxx"] # Replace with your subnet IDs
}
