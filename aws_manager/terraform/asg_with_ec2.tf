terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

# Find default VPC
data "aws_vpc" "default_vpc" {
  default = true
}

# Find default subnet in the default VPC
data "aws_subnets" "default_subnets" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default_vpc.id]
  }
}

# Find default security group
data "aws_security_group" "default_sg" {
  vpc_id = data.aws_vpc.default_vpc.id
  name   = "default"
}

resource "aws_autoscaling_group" "asg_example" {
  name                      = "example-asg"
  max_size                  = 2
  min_size                  = 1
  desired_capacity          = 1
  vpc_zone_identifier       = [data.aws_subnets.default_subnets.ids[0]]
  launch_configuration      = aws_launch_configuration.example.id
  tag {
    key                 = "Name"
    value               = "ASGWithEC2"
    propagate_at_launch = true
  }
}

resource "aws_launch_configuration" "example" {
  name_prefix   = "example-lc-"
  image_id      = "ami-0e731c3a5739c7862" # Latest Amazon Linux 2023 AMI
  instance_type = "t2.micro"
  security_groups = [data.aws_security_group.default_sg.id]
  lifecycle {
    create_before_destroy = true
  }
}
