#!/usr/bin/env python
"""
This script cleans up the Terraform temporary directories and ensures 
that the proper structure is maintained for the repository.
"""

import os
import shutil
import sys

# Get the script's directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TERRAFORM_DIR = os.path.join(SCRIPT_DIR, 'aws_manager', 'terraform')

# Resources we're working with
RESOURCES = ['ec2', 's3', 'loadbalancer', 'vpc']

def ensure_temp_dirs():
    """
    Ensure that all temp directories exist and contain only a .gitkeep file
    """
    print("Ensuring temporary directories are properly set up...")
    
    for resource in RESOURCES:
        temp_dir = os.path.join(TERRAFORM_DIR, f'temp_{resource}')
        
        # Create directory if it doesn't exist
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            print(f"Created directory: {temp_dir}")
        
        # Remove everything from the directory
        for item in os.listdir(temp_dir):
            item_path = os.path.join(temp_dir, item)
            if item != '.gitkeep':
                if os.path.isfile(item_path):
                    os.remove(item_path)
                    print(f"Removed file: {item_path}")
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    print(f"Removed directory: {item_path}")
        
        # Check for any .terraform directories in the parent directory
        terraform_dir = os.path.join(temp_dir, '.terraform')
        if os.path.exists(terraform_dir):
            shutil.rmtree(terraform_dir)
            print(f"Removed Terraform directory: {terraform_dir}")
        
        # Ensure .gitkeep exists
        gitkeep_path = os.path.join(temp_dir, '.gitkeep')
        if not os.path.exists(gitkeep_path):
            with open(gitkeep_path, 'w') as f:
                pass  # Create empty file
            print(f"Created .gitkeep file in {temp_dir}")

def clean_terraform_artifacts():
    """
    Clean up all Terraform artifacts from the repository
    """
    print("Cleaning Terraform artifacts from the repository...")
    
    # Walk through all directories in the repository
    for root, dirs, files in os.walk(SCRIPT_DIR):
        # Skip .git directory
        if '.git' in dirs:
            dirs.remove('.git')
        
        # Remove Terraform state files
        for file in files:
            if file.endswith('.tfstate') or file.endswith('.tfstate.backup') or file == '.terraform.lock.hcl':
                file_path = os.path.join(root, file)
                os.remove(file_path)
                print(f"Removed Terraform state file: {file_path}")
        
        # Remove .terraform directories
        if '.terraform' in dirs:
            terraform_dir = os.path.join(root, '.terraform')
            shutil.rmtree(terraform_dir)
            print(f"Removed Terraform directory: {terraform_dir}")

def main():
    """
    Main function to clean up the repository
    """
    print("Starting repository cleanup...")
    
    # Ensure the terraform directory exists
    if not os.path.exists(TERRAFORM_DIR):
        print(f"Error: Terraform directory {TERRAFORM_DIR} not found!")
        return 1
    
    # Setup the temporary directories
    ensure_temp_dirs()
    
    # Clean up Terraform artifacts
    clean_terraform_artifacts()
    
    print("Repository cleanup completed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
