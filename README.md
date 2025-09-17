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

## Development Notes

- Before pushing to GitHub, run the cleanup script to remove Terraform state files:
  ```
  python clean_terraform.py
  ```
  
- The `.gitignore` file is configured to exclude Terraform state and provider files

## Technologies Used

- Django 5.2.5
- Python 3.12.6
- Terraform
- AWS SDK
- JavaScript/CSS for frontend
