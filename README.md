# Python Django Terraform Infrastructure Manager

A web application built with Django to manage AWS infrastructure using Terraform.

## Features

- Create and destroy AWS resources through a web interface
- Support for multiple resource types (EC2, S3, VPC, Load Balancer, ASG)
- Custom naming and resource count
- Real-time feedback on resource creation/destruction
- Formatted Terraform output display

## Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure AWS credentials: `aws configure`
4. Run the Django server: `python manage.py runserver`

## Project Structure

```
├── aws_manager/             # Django app for AWS resource management
│   ├── terraform/           # Contains Terraform configuration files
│   │   ├── ec2.tf           # EC2 instance configuration
│   │   ├── loadbalancer.tf  # Load balancer configuration
│   │   ├── s3.tf            # S3 bucket configuration
│   │   ├── vpc.tf           # VPC configuration
│   │   ├── temp_ec2/        # Temporary directory for EC2 resources
│   │   ├── temp_loadbalancer/ # Temporary directory for Load Balancer resources
│   │   ├── temp_s3/         # Temporary directory for S3 resources
│   │   └── temp_vpc/        # Temporary directory for VPC resources
│   ├── templates/           # HTML templates
│   └── views.py             # View functions
├── main_project/            # Django project settings
├── manage.py                # Django management script
├── cleanup_repo.py          # Script to clean up temporary files
└── README.md                # This file
```

## Development Notes

- Before pushing to GitHub, run the cleanup script to remove Terraform state files:
  ```
  python cleanup_repo.py
  ```
  
- The `.gitignore` file is configured to exclude Terraform state and provider files while maintaining directory structure

## Technologies Used

- Django 5.2.5
- Python 3.12.6
- Terraform
- AWS SDK
- JavaScript/CSS for frontend
