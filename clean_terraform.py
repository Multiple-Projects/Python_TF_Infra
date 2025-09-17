import os
import shutil
import sys

# Base directory where we'll search for temp directories
base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aws_manager', 'terraform')

# Look for temp_* directories in the terraform directory
temp_dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d)) and d.startswith('temp_')]

if not temp_dirs:
    print("No temporary Terraform directories found.")
    sys.exit(0)

print(f"Found {len(temp_dirs)} temporary Terraform directories.")

for temp_dir in temp_dirs:
    if temp_dir == 'temp_dir':  # Skip our placeholder directory
        continue
        
    full_path = os.path.join(base_dir, temp_dir)
    
    # Check if .terraform directory exists and remove it
    terraform_dir = os.path.join(full_path, '.terraform')
    if os.path.exists(terraform_dir):
        print(f"Cleaning {terraform_dir}...")
        shutil.rmtree(terraform_dir)
    
    # Remove terraform state files
    for state_file in ['terraform.tfstate', 'terraform.tfstate.backup', '.terraform.lock.hcl']:
        file_path = os.path.join(full_path, state_file)
        if os.path.exists(file_path):
            print(f"Removing {file_path}...")
            os.remove(file_path)
    
    # Keep the main.tf file if it exists
    main_tf = os.path.join(full_path, 'main.tf')
    if not os.path.exists(main_tf):
        print(f"Removing directory {full_path}...")
        shutil.rmtree(full_path)

print("Cleanup complete!")
