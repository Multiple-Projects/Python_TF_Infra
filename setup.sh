#!/bin/bash
# setup.sh - Post-clone setup script for Python Django Terraform Infrastructure

echo "=== Python Django Terraform Infrastructure Manager Setup ==="
echo "Setting up your environment..."

# Detect OS
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="Linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="Mac"
elif [[ "$OSTYPE" == "msys"* || "$OSTYPE" == "cygwin"* || "$OSTYPE" == "win32"* ]]; then
    OS="Windows"
else
    OS="Unknown"
fi

echo "Detected OS: $OS"

# Run the cleanup script to ensure directory structure
echo "Setting up directory structure..."
if [[ "$OS" == "Windows" ]]; then
    python cleanup_repo.py
else
    python3 cleanup_repo.py
fi

# Check for Python dependencies
echo "Checking Python dependencies..."
if [[ "$OS" == "Windows" ]]; then
    pip install -r requirements.txt
else
    pip3 install -r requirements.txt
fi

# Check for Terraform
echo "Checking for Terraform installation..."
if ! command -v terraform &> /dev/null; then
    echo "Terraform not found. Please install Terraform:"
    if [[ "$OS" == "Linux" ]]; then
        echo "  sudo apt-get update && sudo apt-get install -y gnupg software-properties-common curl"
        echo "  curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo apt-key add -"
        echo "  sudo apt-add-repository \"deb [arch=amd64] https://apt.releases.hashicorp.com \$(lsb_release -cs) main\""
        echo "  sudo apt-get update && sudo apt-get install -y terraform"
    elif [[ "$OS" == "Mac" ]]; then
        echo "  brew install terraform"
    else
        echo "  Download from: https://developer.hashicorp.com/terraform/install"
    fi
else
    echo "Terraform found: $(terraform --version)"
fi

# Check for AWS CLI
echo "Checking for AWS CLI installation..."
if ! command -v aws &> /dev/null; then
    echo "AWS CLI not found. Please install AWS CLI:"
    if [[ "$OS" == "Linux" ]]; then
        echo "  curl \"https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip\" -o \"awscliv2.zip\""
        echo "  unzip awscliv2.zip"
        echo "  sudo ./aws/install"
    elif [[ "$OS" == "Mac" ]]; then
        echo "  brew install awscli"
    else
        echo "  Download from: https://aws.amazon.com/cli/"
    fi
else
    echo "AWS CLI found: $(aws --version)"
fi

echo ""
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Configure AWS credentials: aws configure"
echo "2. Run the Django server: python manage.py runserver"
echo "3. Access the application at http://localhost:8000/"
echo ""
