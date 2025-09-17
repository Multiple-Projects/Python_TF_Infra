@echo off
REM setup.bat - Post-clone setup script for Python Django Terraform Infrastructure on Windows

echo === Python Django Terraform Infrastructure Manager Setup ===
echo Setting up your environment...

REM Run the cleanup script to ensure directory structure
echo Setting up directory structure...
python cleanup_repo.py

REM Check for Python dependencies
echo Checking Python dependencies...
pip install -r requirements.txt

REM Check for Terraform
echo Checking for Terraform installation...
where terraform >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Terraform not found. Please install Terraform:
    echo Download from: https://developer.hashicorp.com/terraform/install
) else (
    terraform --version
)

REM Check for AWS CLI
echo Checking for AWS CLI installation...
where aws >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo AWS CLI not found. Please install AWS CLI:
    echo Download from: https://aws.amazon.com/cli/
) else (
    aws --version
)

echo.
echo Setup complete!
echo.
echo Next steps:
echo 1. Configure AWS credentials: aws configure
echo 2. Run the Django server: python manage.py runserver
echo 3. Access the application at http://localhost:8000/
echo.
