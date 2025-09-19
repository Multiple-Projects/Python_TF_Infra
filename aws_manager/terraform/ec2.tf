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

# Create EC2 instance
resource "aws_instance" "ec2_instance" {
  ami                    = "ami-08982f1c5bf93d976" # Latest Amazon Linux 2023 AMI
  instance_type          = "t2.micro"
  subnet_id              = data.aws_subnets.default_subnets.ids[0]
  vpc_security_group_ids = [data.aws_security_group.default_sg.id]
  tags = {
    Name = "__NAME__"
  }
}
