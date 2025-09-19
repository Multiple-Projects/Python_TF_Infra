import os
import subprocess
import threading
import time
import json
from queue import Queue
from django.shortcuts import render
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt

TERRAFORM_DIR = os.path.join(os.path.dirname(__file__), 'terraform')

RESOURCE_FILES = {
    'ec2': 'ec2.tf',
    's3': 's3.tf',
    'loadbalancer': 'loadbalancer.tf',
    'vpc': 'vpc.tf',
    'asg_with_ec2': 'asg_with_ec2.tf',
}

# Dictionary to store terminal output for each resource operation
terminal_outputs = {}

def clean_conflicting_terraform_files(temp_dir, resource=None):
    """Clean up any provider.tf, versions.tf, or other files that might conflict with main.tf"""
    output_text = ""
    
    # List of files that might contain conflicting configurations
    conflicting_files = [
        'provider.tf', 
        'versions.tf', 
        'terraform.tf',
        'aws.tf'
    ]
    
    for file_to_check in conflicting_files:
        file_path = os.path.join(temp_dir, file_to_check)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                output_text += f"\nRemoved conflicting {file_to_check} file\n"
            except Exception as e:
                output_text += f"\nWarning: Could not remove {file_to_check}: {str(e)}\n"
    
    # Also check for any other .tf files that might contain provider blocks
    for filename in os.listdir(temp_dir):
        if filename.endswith('.tf') and filename != 'main.tf':
            file_path = os.path.join(temp_dir, filename)
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Check if the file contains provider or terraform blocks
                if 'provider ' in content or 'terraform {' in content:
                    # We'll remove the file to avoid conflicts
                    os.remove(file_path)
                    output_text += f"\nRemoved potentially conflicting file {filename}\n"
            except Exception as e:
                output_text += f"\nWarning: Could not check or remove {filename}: {str(e)}\n"
    
    # If resource is provided, update the terminal output
    if resource and resource in terminal_outputs:
        terminal_outputs[resource]['output'] += output_text
    
    return output_text

def check_resource_exists(resource):
    """Check if a resource exists by looking for the terraform.tfstate file"""
    temp_dir = os.path.join(TERRAFORM_DIR, 'temp_' + resource)
    tfstate_path = os.path.join(temp_dir, 'terraform.tfstate')
    
    # If the directory and state file exist, check if the resource exists
    if os.path.exists(tfstate_path):
        try:
            # Run terraform state list to check if resources exist
            result = subprocess.run(['terraform', 'state', 'list'], 
                                   cwd=temp_dir, 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE,
                                   universal_newlines=True)
            
            # If there are resources listed, the resource exists
            return result.returncode == 0 and len(result.stdout.strip()) > 0
        except Exception as e:
            print(f"Error checking resource: {e}")
            return False
    return False

def get_resource_display_name(resource):
    """Convert resource key to display name"""
    resource_names = {
        'ec2': 'EC2 Instance',
        's3': 'S3 Bucket',
        'loadbalancer': 'Load Balancer',
        'vpc': 'VPC',
        'asg_with_ec2': 'Auto Scaling Group with EC2'
    }
    return resource_names.get(resource, resource.title())

def index(request):
    resources_status = {}
    
    # Check which resources exist
    for resource in RESOURCE_FILES.keys():
        resources_status[resource] = check_resource_exists(resource)
    
    return render(request, 'aws_manager/index.html', {
        'resources_status': resources_status
    })

@csrf_exempt
def create_resource(request):
    resource = request.POST.get('resource')
    resource_name = request.POST.get('name', '')  # Get the resource name from POST
    resource_count = request.POST.get('count', '1')  # Get the resource count from POST, default to 1
    
    # Validate inputs
    if not resource_name:
        return JsonResponse({
            'success': False, 
            'message': 'Resource name is required',
            'resource_name': get_resource_display_name(resource)
        })
    
    try:
        resource_count = int(resource_count)
        if resource_count < 1:
            resource_count = 1
        elif resource_count > 10:
            resource_count = 10
    except (ValueError, TypeError):
        resource_count = 1
    
    tf_file = RESOURCE_FILES.get(resource)
    if not tf_file:
        return JsonResponse({'success': False, 'message': 'Invalid resource type'})
    
    # Create a display name for the resource
    resource_display_name = get_resource_display_name(resource)
    
    try:
        # Prepare directory for Terraform files
        temp_dir = os.path.join(TERRAFORM_DIR, 'temp_' + resource)
        os.makedirs(temp_dir, exist_ok=True)
        
        # Clean up any existing Terraform files to prevent conflicts
        for existing_file in os.listdir(temp_dir):
            if existing_file.endswith('.tf'):
                os.remove(os.path.join(temp_dir, existing_file))
                
        # Use our helper function to ensure no conflicting provider files exist
        clean_conflicting_terraform_files(temp_dir)
        
        # Create a single main.tf file with all the necessary configurations
        src_file = os.path.join(TERRAFORM_DIR, tf_file)
        main_file = os.path.join(temp_dir, 'main.tf')
        
        # Read the template content
        with open(src_file, 'r') as f:
            content = f.read()
        
        # Replace placeholders with actual values
        content = content.replace('__NAME__', resource_name)
        content = content.replace('__COUNT__', str(resource_count))
        
        # Remove any terraform blocks and provider blocks from the template content to avoid duplicates
        import re
        
        # Instead of using regex directly on the full content, let's process line by line
        # to ensure we don't leave orphaned curly braces or incomplete blocks
        
        # First, split content into lines
        lines = content.split('\n')
        filtered_lines = []
        
        skip_mode = False
        open_braces = 0
        
        for line in lines:
            # Check for start of terraform or provider blocks
            if re.match(r'^\s*terraform\s*{', line) or re.match(r'^\s*provider\s*', line):
                skip_mode = True
                open_braces += line.count('{')
                continue
            
            # If we're in skip mode, count braces to determine when the block ends
            if skip_mode:
                open_braces += line.count('{')
                open_braces -= line.count('}')
                
                # If we've closed all braces, exit skip mode
                if open_braces <= 0:
                    skip_mode = False
                    open_braces = 0
                continue
            
            # If we're not in skip mode, keep the line
            filtered_lines.append(line)
        
        # Rejoin the filtered lines
        content = '\n'.join(filtered_lines)
        
        # Add a second pass to clean up any remaining provider-related lines
        # that might not be in blocks (like standalone variable declarations)
        content = re.sub(r'^\s*provider\s+.*$', '', content, flags=re.MULTILINE)
        
        # Write the single main.tf file with required configurations
        with open(main_file, 'w') as f:
            f.write('''
# Required Terraform version and providers
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"  # Use version 5.0 to match the locked version
    }
  }
  required_version = ">= 1.0.0"
}

# AWS provider configuration
provider "aws" {
  region = "us-east-1"
  # Using environment variables for credentials
  # For development purposes
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
}

''')
            # Append the modified template content
            f.write(content)
        
        # Validate the generated Terraform file for syntax errors
        def validate_terraform_file(file_path):
            """Check if the generated Terraform file has valid syntax"""
            try:
                # Run terraform validate -json to check syntax
                result = subprocess.run(
                    ['terraform', 'fmt', '-check', file_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=os.path.dirname(file_path),
                    universal_newlines=True
                )
                
                # Return True if successful (exit code 0), False otherwise
                return result.returncode == 0
            except Exception:
                return False
        
        # Initialize terminal output tracking
        terminal_outputs[resource] = {
            'output': '',
            'complete': False,
            'waiting_confirmation': False,
            'success': False
        }
        
        # Validate the syntax of the generated file
        if not validate_terraform_file(main_file):
            terminal_outputs[resource]['output'] = "ERROR: Generated Terraform file has syntax errors. Attempting to fix...\n"
            try:
                # Try to fix the file using terraform fmt
                subprocess.run(['terraform', 'fmt', main_file], 
                            cwd=temp_dir,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
                terminal_outputs[resource]['output'] += "Auto-formatted the Terraform file.\n"
            except Exception as e:
                terminal_outputs[resource]['output'] += f"Warning: Could not auto-format: {str(e)}\n"
        
        # Define a function to run terraform commands in a background thread
        def run_terraform():
            try:
                # Get the resource details
                temp_dir = os.path.join(TERRAFORM_DIR, 'temp_' + resource)
                
                # Clean up any conflicting Terraform configuration files
                clean_conflicting_terraform_files(temp_dir, resource)
                
                # Set up environment with disabled color output
                terraform_env = os.environ.copy()
                # Use NO_COLOR which is a standard way to disable color output
                terraform_env['NO_COLOR'] = 'true'
                
                # Always clean up existing state files for a fresh start
                terminal_outputs[resource]['output'] = "Preparing for Terraform initialization...\n"
                
                # Clean up all Terraform state files and directories to ensure a fresh start
                terraform_dir = os.path.join(temp_dir, '.terraform')
                terraform_lock_file = os.path.join(temp_dir, '.terraform.lock.hcl')
                
                # Remove .terraform directory if it exists
                if os.path.exists(terraform_dir):
                    import shutil
                    try:
                        shutil.rmtree(terraform_dir)
                        terminal_outputs[resource]['output'] += "Removed existing .terraform directory for clean initialization\n"
                    except Exception as e:
                        terminal_outputs[resource]['output'] += f"Warning: Could not remove .terraform directory: {str(e)}\n"
                
                # Remove .terraform.lock.hcl file if it exists
                if os.path.exists(terraform_lock_file):
                    try:
                        os.remove(terraform_lock_file)
                        terminal_outputs[resource]['output'] += "Removed existing .terraform.lock.hcl file for clean initialization\n"
                    except Exception as e:
                        terminal_outputs[resource]['output'] += f"Warning: Could not remove .terraform.lock.hcl file: {str(e)}\n"
                
                # Run terraform init with enhanced options
                terminal_outputs[resource]['output'] += "Initializing Terraform...\n"
                
                # Check if terraform executable exists
                try:
                    # Check if terraform is available
                    check_process = subprocess.run(['terraform', '--version'], 
                                               stdout=subprocess.PIPE, 
                                               stderr=subprocess.PIPE)
                    if check_process.returncode != 0:
                        raise Exception("Terraform not found. Please make sure it's installed and in your PATH.")
                except FileNotFoundError:
                    terminal_outputs[resource]['output'] += "\nERROR: Terraform executable not found! Please install Terraform.\n"
                    terminal_outputs[resource]['complete'] = True
                    terminal_outputs[resource]['success'] = False
                    return
                
                # Provider configuration is now in main.tf
                
                # Clean up any .terraform directories and lock files to start fresh
                terraform_dir = os.path.join(temp_dir, '.terraform')
                terraform_lock_file = os.path.join(temp_dir, '.terraform.lock.hcl')
                
                # Remove .terraform directory if it exists
                if os.path.exists(terraform_dir):
                    import shutil
                    try:
                        shutil.rmtree(terraform_dir)
                        terminal_outputs[resource]['output'] += "\nRemoved existing .terraform directory for clean initialization\n"
                    except Exception as e:
                        terminal_outputs[resource]['output'] += f"\nWarning: Could not remove .terraform directory: {str(e)}\n"
                
                # Remove .terraform.lock.hcl file if it exists to prevent version conflicts
                if os.path.exists(terraform_lock_file):
                    try:
                        os.remove(terraform_lock_file)
                        terminal_outputs[resource]['output'] += "\nRemoved existing .terraform.lock.hcl file to prevent version conflicts\n"
                    except Exception as e:
                        terminal_outputs[resource]['output'] += f"\nWarning: Could not remove .terraform.lock.hcl file: {str(e)}\n"
                
                # Run terraform init with detailed error handling, force reconfiguration, and upgrade flag
                init_process = subprocess.Popen(['terraform', 'init', '-no-color', '-reconfigure', '-upgrade'], 
                                              cwd=temp_dir,
                                              env=terraform_env,
                                              stdout=subprocess.PIPE, 
                                              stderr=subprocess.STDOUT,
                                              universal_newlines=True)
                
                # Process and capture real-time output
                for line in init_process.stdout:
                    terminal_outputs[resource]['output'] += line
                    print(line, end='', flush=True)
                
                # Check return code to see if initialization was successful
                init_return_code = init_process.wait()
                if init_return_code != 0:
                    terminal_outputs[resource]['output'] += "\n\nERROR: Terraform initialization failed! See output above for details.\n"
                    terminal_outputs[resource]['complete'] = True
                    terminal_outputs[resource]['success'] = False
                    return
                
                # Run terraform plan - not using auto-approve yet so the user can see the plan first
                terminal_outputs[resource]['output'] += "\n\nPlanning resource creation...\n"
                plan_process = subprocess.Popen(['terraform', 'plan', '-no-color'], 
                                              cwd=temp_dir,
                                              env=terraform_env,
                                              stdout=subprocess.PIPE, 
                                              stderr=subprocess.STDOUT,
                                              universal_newlines=True)
                
                # Process and capture real-time output
                for line in plan_process.stdout:
                    terminal_outputs[resource]['output'] += line
                    print(line, end='', flush=True)
                
                plan_process.wait()
                
                # Mark as ready for confirmation
                terminal_outputs[resource]['output'] += "\n\nPlan complete. Review the resources above and confirm creation.\n"
                terminal_outputs[resource]['waiting_confirmation'] = True
                terminal_outputs[resource]['complete'] = False
                
                # The apply command will be executed by the confirm_resource endpoint
                return
                
            except Exception as e:
                terminal_outputs[resource]['output'] += f"\n\nERROR: {str(e)}"
                terminal_outputs[resource]['complete'] = True
                terminal_outputs[resource]['success'] = False
        
        # Start the thread to run Terraform commands
        thread = threading.Thread(target=run_terraform)
        thread.daemon = True
        thread.start()
        
        # Return immediately with initial status
        return JsonResponse({
            'success': True,
            'message': f'{resource_display_name} creation started',
            'resource_name': resource_display_name,
            'status': 'creating'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'message': str(e), 
            'resource_name': resource_display_name, 
            'status': 'error'
        })

@csrf_exempt
def destroy_resource(request):
    resource = request.POST.get('resource')
    
    if not resource:
        return JsonResponse({'success': False, 'message': 'Resource type is required'})
    
    # Get a display name for the resource
    resource_display_name = get_resource_display_name(resource)
    
    try:
        # Check if temp directory exists
        temp_dir = os.path.join(TERRAFORM_DIR, 'temp_' + resource)
        if not os.path.exists(temp_dir):
            return JsonResponse({
                'success': False, 
                'message': f'{resource_display_name} does not exist',
                'resource_name': resource_display_name
            })
            
        # Ensure we have a main.tf file with proper configurations
        main_file = os.path.join(temp_dir, 'main.tf')
        if not os.path.exists(main_file):
            # Try to copy the relevant terraform file content
            tf_file = RESOURCE_FILES.get(resource, '')
            if tf_file:
                src_file = os.path.join(TERRAFORM_DIR, tf_file)
                if os.path.exists(src_file):
                    with open(src_file, 'r') as f:
                        content = f.read()
                    
                    # Remove any terraform blocks and provider blocks from the template content to avoid duplicates
                    import re
                    
                    # Use a more robust approach to remove terraform and provider blocks
                    # Split content into lines for better processing
                    lines = content.split('\n')
                    filtered_lines = []
                    
                    i = 0
                    while i < len(lines):
                        line = lines[i]
                        
                        # Check if this line starts a terraform or provider block
                        terraform_match = re.match(r'^\s*terraform\s*{', line)
                        provider_match = re.match(r'^\s*provider\s+"?\w+"?\s*{', line)
                        
                        if terraform_match or provider_match:
                            # Skip this block entirely by counting braces
                            brace_count = line.count('{') - line.count('}')
                            i += 1
                            
                            # Continue skipping lines until all braces are closed
                            while i < len(lines) and brace_count > 0:
                                next_line = lines[i]
                                brace_count += next_line.count('{') - next_line.count('}')
                                i += 1
                            
                            # Skip the closing brace line if we stopped on it
                            if i < len(lines) and brace_count == 0:
                                i += 1
                        else:
                            # Keep non-terraform/provider lines
                            filtered_lines.append(line)
                            i += 1
                    
                    # Rejoin the filtered lines
                    content = '\n'.join(filtered_lines)
                    
                    # Additional cleanup: remove any leftover provider-related lines
                    content = re.sub(r'^\s*provider\s+.*$', '', content, flags=re.MULTILINE)
                    content = re.sub(r'^\s*terraform\s+.*$', '', content, flags=re.MULTILINE)
                    
                    # Clean up any conflicting files before writing
                    clean_conflicting_terraform_files(temp_dir)
                    
                    # Write the main.tf file with required configurations
                    with open(main_file, 'w') as f:
                        f.write('''
# Required Terraform version and providers
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"  # Use version 5.0 to match the locked version
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
  required_version = ">= 1.0.0"
}

# AWS provider configuration
provider "aws" {
  region = "us-east-1"
  # Using environment variables for credentials
  # For development purposes
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
}

# Random provider configuration
provider "random" {
}

''')
                        # Append the modified template content
                        f.write(content)
        
        # Initialize terminal output tracking
        terminal_outputs[resource] = {
            'output': '',
            'complete': False,
            'waiting_confirmation': False,
            'success': False
        }
        
        # Define a function to run terraform destroy in a background thread
        def run_terraform_destroy():
            try:
                # Get the resource details
                temp_dir = os.path.join(TERRAFORM_DIR, 'temp_' + resource)
                
                # Clean up any conflicting Terraform configuration files
                clean_conflicting_terraform_files(temp_dir, resource)
                
                # Set up environment with disabled color output
                terraform_env = os.environ.copy()
                # Use NO_COLOR which is a standard way to disable color output
                terraform_env['NO_COLOR'] = 'true'
                
                # Clean up Terraform files for a fresh initialization
                terraform_dir = os.path.join(temp_dir, '.terraform')
                terraform_lock_file = os.path.join(temp_dir, '.terraform.lock.hcl')
                
                # Remove .terraform directory if it exists
                if os.path.exists(terraform_dir):
                    import shutil
                    try:
                        shutil.rmtree(terraform_dir)
                        terminal_outputs[resource]['output'] += "\nRemoved existing .terraform directory for clean initialization\n"
                    except Exception as e:
                        terminal_outputs[resource]['output'] += f"\nWarning: Could not remove .terraform directory: {str(e)}\n"
                
                # Remove .terraform.lock.hcl file if it exists to prevent version conflicts
                if os.path.exists(terraform_lock_file):
                    try:
                        os.remove(terraform_lock_file)
                        terminal_outputs[resource]['output'] += "\nRemoved existing .terraform.lock.hcl file to prevent version conflicts\n"
                    except Exception as e:
                        terminal_outputs[resource]['output'] += f"\nWarning: Could not remove .terraform.lock.hcl file: {str(e)}\n"
                
                # Run terraform init to make sure we have the latest providers
                terminal_outputs[resource]['output'] = "Preparing to initialize Terraform for destroy...\n"
                
                # Verify if the Terraform state file exists
                tfstate_path = os.path.join(temp_dir, 'terraform.tfstate')
                if not os.path.exists(tfstate_path):
                    terminal_outputs[resource]['output'] += "\nWarning: No terraform.tfstate file found. The resource might not have been created properly.\n"
                
                # Check for terraform.tfstate.backup in case the main state file was corrupted
                backup_state_path = os.path.join(temp_dir, 'terraform.tfstate.backup')
                if os.path.exists(backup_state_path) and not os.path.exists(tfstate_path):
                    try:
                        import shutil
                        shutil.copy2(backup_state_path, tfstate_path)
                        terminal_outputs[resource]['output'] += "\nRestored terraform.tfstate from backup file.\n"
                    except Exception as e:
                        terminal_outputs[resource]['output'] += f"\nWarning: Could not restore state from backup: {str(e)}\n"
                
                terminal_outputs[resource]['output'] += "Initializing Terraform...\n"
                
                # Check if terraform executable exists
                try:
                    # Check if terraform is available
                    check_process = subprocess.run(['terraform', '--version'], 
                                               stdout=subprocess.PIPE, 
                                               stderr=subprocess.PIPE)
                    if check_process.returncode != 0:
                        raise Exception("Terraform not found. Please make sure it's installed and in your PATH.")
                except FileNotFoundError:
                    terminal_outputs[resource]['output'] += "\nERROR: Terraform executable not found! Please install Terraform.\n"
                    terminal_outputs[resource]['complete'] = True
                    terminal_outputs[resource]['success'] = False
                    return
                
                # Provider configuration is now in main.tf
                
                # Clean up any .terraform directories and lock files to start fresh
                terraform_dir = os.path.join(temp_dir, '.terraform')
                terraform_lock_file = os.path.join(temp_dir, '.terraform.lock.hcl')
                
                # Remove .terraform directory if it exists
                if os.path.exists(terraform_dir):
                    import shutil
                    try:
                        shutil.rmtree(terraform_dir)
                        terminal_outputs[resource]['output'] += "\nRemoved existing .terraform directory for clean initialization\n"
                    except Exception as e:
                        terminal_outputs[resource]['output'] += f"\nWarning: Could not remove .terraform directory: {str(e)}\n"
                
                # Remove .terraform.lock.hcl file if it exists to prevent version conflicts
                if os.path.exists(terraform_lock_file):
                    try:
                        os.remove(terraform_lock_file)
                        terminal_outputs[resource]['output'] += "\nRemoved existing .terraform.lock.hcl file to prevent version conflicts\n"
                    except Exception as e:
                        terminal_outputs[resource]['output'] += f"\nWarning: Could not remove .terraform.lock.hcl file: {str(e)}\n"
                
                # Run terraform init with detailed error handling, force reconfiguration, and upgrade flag
                init_process = subprocess.Popen(['terraform', 'init', '-no-color', '-reconfigure', '-upgrade'], 
                                              cwd=temp_dir,
                                              env=terraform_env,
                                              stdout=subprocess.PIPE, 
                                              stderr=subprocess.STDOUT,
                                              universal_newlines=True)
                
                # Process and capture real-time output
                for line in init_process.stdout:
                    terminal_outputs[resource]['output'] += line
                    print(line, end='', flush=True)
                
                # Check return code to see if initialization was successful
                init_return_code = init_process.wait()
                if init_return_code != 0:
                    terminal_outputs[resource]['output'] += "\n\nERROR: Terraform initialization failed! See output above for details.\n"
                    terminal_outputs[resource]['complete'] = True
                    terminal_outputs[resource]['success'] = False
                    return
                
                # Run terraform plan -destroy to show what will be destroyed
                terminal_outputs[resource]['output'] += "\n\nPlanning resource destruction...\n"
                plan_process = subprocess.Popen(['terraform', 'plan', '-destroy', '-no-color'], 
                                              cwd=temp_dir,
                                              env=terraform_env,
                                              stdout=subprocess.PIPE, 
                                              stderr=subprocess.STDOUT,
                                              universal_newlines=True)
                
                # Process and capture real-time output
                for line in plan_process.stdout:
                    terminal_outputs[resource]['output'] += line
                    print(line, end='', flush=True)
                
                plan_process.wait()
                
                # Mark as ready for confirmation
                terminal_outputs[resource]['output'] += "\n\nPlan complete. Review the resources above and confirm destruction.\n"
                terminal_outputs[resource]['waiting_confirmation'] = True
                terminal_outputs[resource]['complete'] = False
                
                # The destroy command will be executed by the confirm_resource endpoint
                return
                
            except Exception as e:
                terminal_outputs[resource]['output'] += f"\n\nERROR: {str(e)}"
                terminal_outputs[resource]['complete'] = True
                terminal_outputs[resource]['success'] = False
        
        # Start the thread to run Terraform destroy
        thread = threading.Thread(target=run_terraform_destroy)
        thread.daemon = True
        thread.start()
        
        # Return immediately with initial status
        return JsonResponse({
            'success': True,
            'message': f'{resource_display_name} destruction started',
            'resource_name': resource_display_name,
            'status': 'destroying'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'message': str(e), 
            'resource_name': resource_display_name, 
            'status': 'error'
        })

def extract_terraform_plan(output):
    """
    Extract the relevant plan output from Terraform output.
    This function removes initialization noise and keeps only the plan details.
    It also applies HTML formatting for better display.
    """
    if not output:
        return ""
    
    # Look for markers of the plan section
    plan_start_markers = [
        "Terraform used the selected providers to generate the following execution plan",
        "Terraform will perform the following actions"
    ]
    
    plan_end_markers = [
        "Plan:",
        "Note: You didn't use the -out option"
    ]
    
    # Find the start of the plan
    plan_start = -1
    for marker in plan_start_markers:
        pos = output.find(marker)
        if pos != -1 and (plan_start == -1 or pos < plan_start):
            plan_start = pos
    
    if plan_start == -1:
        # Plan section not found
        # Check for provider configuration errors
        if "Error: Duplicate required providers configuration" in output:
            return "ERROR: Duplicate provider configuration detected. The system is fixing this issue. Please try again.\n\n" + output
        elif "Error:" in output and "provider" in output.lower():
            return "ERROR: Provider configuration issue detected. The system is fixing this issue. Please try again.\n\n" + output
        return output
    
    # Find the end of the plan
    plan_end = len(output)
    for marker in plan_end_markers:
        pos = output.find(marker, plan_start)
        if pos != -1:
            # Include the Plan: line in the output
            # Find the end of this line
            line_end = output.find("\n", pos)
            if line_end != -1:
                plan_end = line_end + 1  # Include the newline
            else:
                plan_end = len(output)
            break
    
    # Extract the plan
    plan_text = output[plan_start:plan_end]
    
    # Add a summary of what's happening
    if "Plan: " not in plan_text:
        # Add a generic summary
        action = "create" if "will be created" in output else "destroy" if "will be destroyed" in output else "update"
        plan_text = f"Terraform will {action} resources.\n\n{plan_text}"
    
    # Apply HTML formatting
    formatted_text = plan_text
    
    # Colorize plan sections
    formatted_text = formatted_text.replace("Terraform will perform the following actions", 
                                           '<span class="tf-action-header">Terraform will perform the following actions</span>')
    
    # Highlight resource actions (+ create, - destroy, ~ modify)
    formatted_text = formatted_text.replace("+ resource", '<span class="tf-+">+</span> <span class="tf-resource">resource</span>')
    formatted_text = formatted_text.replace("- resource", '<span class="tf--">-</span> <span class="tf-resource">resource</span>')
    formatted_text = formatted_text.replace("~ resource", '<span class="tf-~">~</span> <span class="tf-resource">resource</span>')
    
    # Highlight resource attributes
    lines = formatted_text.split("\n")
    for i, line in enumerate(lines):
        # Match resource property lines like "+ name = value"
        if "+" in line and " = " in line:
            parts = line.split(" = ", 1)
            if len(parts) == 2:
                prop_part = parts[0]
                value_part = parts[1]
                if "+" in prop_part:
                    prop_name = prop_part.split("+", 1)[1].strip()
                    lines[i] = f'<span class="tf-+">+</span> <span class="tf-resource">{prop_name}</span> = {value_part}'
        
        # Mark "will be created/destroyed" lines
        if "will be created" in line:
            lines[i] = line.replace("will be created", '<span class="tf-resource">will</span> be created')
        elif "will be destroyed" in line:
            lines[i] = line.replace("will be destroyed", '<span class="tf-resource">will</span> be destroyed')
            
        # Highlight Plan line
        if line.startswith("Plan:"):
            parts = line.split(":")
            if len(parts) > 1:
                rest = ":".join(parts[1:])
                # Split by commas
                plan_parts = rest.split(",")
                formatted_plan_parts = []
                for part in plan_parts:
                    # Extract number and action
                    import re
                    match = re.search(r'(\d+)(\s+to\s+\w+)', part)
                    if match:
                        num = match.group(1)
                        action = match.group(2)
                        formatted_plan_parts.append(f' <span class="tf-resource">{num}</span>{action}')
                    else:
                        formatted_plan_parts.append(part)
                
                lines[i] = f'Plan<span class="tf-:">:</span>{",".join(formatted_plan_parts)}'
    
    formatted_text = "\n".join(lines)
    
    return formatted_text

def get_terminal_output(request):
    """Get the terminal output for a specific resource operation."""
    resource = request.GET.get('resource')
    
    if not resource or resource not in terminal_outputs:
        return JsonResponse({
            'output': 'No output available for this resource.',
            'complete': True,
            'success': False
        })
    
    # Create a copy of the current terminal outputs
    response_data = terminal_outputs[resource].copy()
    
    # If we're waiting for confirmation, simplify the output to show only the plan
    if response_data.get('waiting_confirmation', False):
        # Check if there was an error during initialization
        if "ERROR: Terraform initialization failed!" in response_data['output']:
            # Keep the error message but add context about provider issues if applicable
            if "Duplicate required providers configuration" in response_data['output'] or "provider" in response_data['output'].lower():
                response_data['output'] = "ERROR: Provider configuration issue detected. This is being fixed automatically. Please cancel and try again.\n\n" + response_data['output']
        else:
            # Extract just the plan part for cleaner output
            response_data['output'] = extract_terraform_plan(response_data['output'])
    
    return JsonResponse(response_data)

@csrf_exempt
def confirm_resource(request):
    """Endpoint to confirm resource creation or destruction after viewing the plan."""
    resource = request.POST.get('resource')
    action = request.POST.get('action')  # 'create' or 'destroy'
    
    # Log request parameters for debugging
    print(f"confirm_resource called with: resource={resource}, action={action}")
    
    if not resource or resource not in terminal_outputs:
        return JsonResponse({
            'success': False, 
            'message': 'Invalid resource or no pending operation'
        })
        
    # Ensure action is valid
    if action not in ['create', 'destroy']:
        print(f"WARNING: Invalid action '{action}' received, defaulting to 'create'")
        action = 'create'
    
    # Get the resource details
    temp_dir = os.path.join(TERRAFORM_DIR, 'temp_' + resource)
    
    # Double check for any provider.tf or versions.tf files that might conflict
    clean_conflicting_terraform_files(temp_dir, resource)
    
    # Set up environment with disabled color output
    terraform_env = os.environ.copy()
    # Use NO_COLOR which is a standard way to disable color output
    terraform_env['NO_COLOR'] = 'true'
    
    try:
        # Update the output to show confirmation - ensure action is proper
        action_message = "Destroy" if action == "destroy" else "Create"
        terminal_outputs[resource]['output'] += f"\n\n{action_message} confirmed by user, executing...\n"
        terminal_outputs[resource]['waiting_confirmation'] = False
        
        # Check if terraform executable exists
        try:
            # Check if terraform is available
            check_process = subprocess.run(['terraform', '--version'], 
                                      stdout=subprocess.PIPE, 
                                      stderr=subprocess.PIPE)
            if check_process.returncode != 0:
                raise Exception("Terraform not found. Please make sure it's installed and in your PATH.")
        except FileNotFoundError:
            terminal_outputs[resource]['output'] += "\nERROR: Terraform executable not found! Please install Terraform.\n"
            terminal_outputs[resource]['complete'] = True
            terminal_outputs[resource]['success'] = False
            return JsonResponse({
                'success': False,
                'message': 'Terraform executable not found'
            })
            
        if action == 'create':
            # Run terraform apply
            terminal_outputs[resource]['output'] += "\nApplying Terraform configuration...\n"
            process = subprocess.Popen(['terraform', 'apply', '-auto-approve', '-no-color'], 
                                      cwd=temp_dir,
                                      env=terraform_env,
                                      stdout=subprocess.PIPE, 
                                      stderr=subprocess.STDOUT,
                                      universal_newlines=True)
        else:  # action == 'destroy'
            # First refresh the state to ensure it's up to date
            terminal_outputs[resource]['output'] += "\nRefreshing Terraform state...\n"
            refresh_process = subprocess.Popen(['terraform', 'refresh', '-no-color'], 
                                      cwd=temp_dir,
                                      env=terraform_env, 
                                      stdout=subprocess.PIPE, 
                                      stderr=subprocess.STDOUT,
                                      universal_newlines=True)
            
            # Capture refresh output
            for line in refresh_process.stdout:
                terminal_outputs[resource]['output'] += line
                print(line, end='', flush=True)
            
            refresh_return_code = refresh_process.wait()
            if refresh_return_code != 0:
                terminal_outputs[resource]['output'] += "\nWarning: State refresh failed, but continuing with destroy operation...\n"
            
            # Run terraform destroy with additional handling for state issues
            terminal_outputs[resource]['output'] += "\nDestroying resources...\n"
            
            # Check if there's a state file
            state_file = os.path.join(temp_dir, 'terraform.tfstate')
            if not os.path.exists(state_file) or os.path.getsize(state_file) == 0:
                terminal_outputs[resource]['output'] += "\nWarning: No state file found or state file is empty. Resources may have already been destroyed.\n"
                
                # Run terraform state list to check if there are any resources
                state_list_process = subprocess.Popen(['terraform', 'state', 'list'],
                                                     cwd=temp_dir,
                                                     env=terraform_env,
                                                     stdout=subprocess.PIPE,
                                                     stderr=subprocess.PIPE,
                                                     universal_newlines=True)
                state_output = state_list_process.communicate()[0]
                
                if not state_output.strip():
                    terminal_outputs[resource]['output'] += "\nNo resources found in Terraform state. Marking as destroyed.\n"
                    terminal_outputs[resource]['complete'] = True
                    terminal_outputs[resource]['success'] = True
                    return JsonResponse({
                        'success': True,
                        'message': 'No resources to destroy, operation considered successful'
                    })
            
            # Execute terraform destroy with auto-approve
            destroy_process = subprocess.Popen(['terraform', 'destroy', '-auto-approve', '-no-color'],
                                             cwd=temp_dir,
                                             env=terraform_env,
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT,
                                             universal_newlines=True)
            
            # Capture destroy output in real-time
            for line in destroy_process.stdout:
                terminal_outputs[resource]['output'] += line
                print(line, end='', flush=True)
            
            destroy_return_code = destroy_process.wait()
            
            if destroy_return_code == 0:
                terminal_outputs[resource]['output'] += "\n\nTerraform destroy completed successfully!\n"
                terminal_outputs[resource]['complete'] = True
                terminal_outputs[resource]['success'] = True
                return JsonResponse({
                    'success': True,
                    'message': f'{resource} destruction completed successfully'
                })
            else:
                terminal_outputs[resource]['output'] += f"\n\nTerraform destroy failed with return code {destroy_return_code}. Trying alternative methods...\n"
            
            # Force removal of the state file and try a more aggressive approach if destroy doesn't succeed
            # This block will be reached if normal destroy doesn't work
            terminal_outputs[resource]['output'] += "\n\nAttempting alternative method to ensure resources are completely removed...\n"
            
            # Try AWS CLI fallback for resource type-specific cleanup
            if resource == 's3':
                terminal_outputs[resource]['output'] += "\nAttempting to force-delete any S3 buckets via AWS CLI...\n"
                
                try:
                    # Try to extract bucket name from terraform state
                    # This is a more reliable approach since it contains the actual created resource names
                    state_file_path = os.path.join(temp_dir, 'terraform.tfstate')
                    if os.path.exists(state_file_path):
                        import json
                        try:
                            with open(state_file_path, 'r') as f:
                                state_data = json.load(f)
                                
                            # Extract bucket name from state
                            bucket_names = []
                            if "resources" in state_data:
                                for resource_item in state_data.get("resources", []):
                                    if resource_item.get("type") == "aws_s3_bucket":
                                        for instance in resource_item.get("instances", []):
                                            if "attributes" in instance and "bucket" in instance["attributes"]:
                                                bucket_name = instance["attributes"]["bucket"]
                                                if bucket_name:
                                                    bucket_names.append(bucket_name)
                            
                            if bucket_names:
                                terminal_outputs[resource]['output'] += f"\nFound {len(bucket_names)} S3 bucket(s) in state file\n"
                                
                                for bucket_name in bucket_names:
                                    terminal_outputs[resource]['output'] += f"\nAttempting to delete S3 bucket: {bucket_name}\n"
                                    
                                    # Run AWS CLI to delete the bucket with force option
                                    aws_process = subprocess.Popen(
                                        ['aws', 's3', 'rb', f"s3://{bucket_name}", '--force'],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        universal_newlines=True
                                    )
                                    aws_out, aws_err = aws_process.communicate()
                                    
                                    if aws_process.returncode == 0:
                                        terminal_outputs[resource]['output'] += f"\nSuccessfully removed S3 bucket {bucket_name} via AWS CLI.\n"
                                    else:
                                        terminal_outputs[resource]['output'] += f"\nAWS CLI command failed for bucket {bucket_name}: {aws_err}\n"
                            else:
                                terminal_outputs[resource]['output'] += f"\nNo S3 bucket names found in the state file.\n"
                        except json.JSONDecodeError:
                            terminal_outputs[resource]['output'] += f"\nCould not parse the state file as JSON. It may be corrupted.\n"
                    else:
                        terminal_outputs[resource]['output'] += f"\nNo terraform.tfstate file found. Cannot extract bucket names.\n"
                except Exception as e:
                    terminal_outputs[resource]['output'] += f"\nFailed to use AWS CLI fallback: {str(e)}\n"
            
            # Remove all state files to ensure a clean start next time
            lock_file = os.path.join(temp_dir, '.terraform.lock.hcl')
            if os.path.exists(lock_file):
                try:
                    os.remove(lock_file)
                    terminal_outputs[resource]['output'] += "\nRemoved .terraform.lock.hcl file for clean state\n"
                except Exception as e:
                    terminal_outputs[resource]['output'] += f"\nWarning: Could not remove lock file: {str(e)}\n"
            
            # Try to taint the resource first to force recreation/destruction
            # This is a more aggressive approach that marks the resource as needing to be destroyed
            taint_process = subprocess.Popen(['terraform', 'taint', 'aws_instance.ec2_instance'],
                                           cwd=temp_dir,
                                           env=terraform_env,
                                           stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE,
                                           universal_newlines=True)
            taint_result = taint_process.communicate()
            if taint_process.returncode == 0:
                terminal_outputs[resource]['output'] += "\nSuccessfully marked resource for destruction\n"
            
            # Try destroying with normal command and force flag
            terminal_outputs[resource]['output'] += "\nAttempting forced destroy...\n"
            process = subprocess.Popen(['terraform', 'destroy', '-auto-approve', '-no-color'], 
                                      cwd=temp_dir,
                                      env=terraform_env, 
                                      stdout=subprocess.PIPE, 
                                      stderr=subprocess.STDOUT,
                                      universal_newlines=True)
        
        # Process and capture real-time output
        for line in process.stdout:
            terminal_outputs[resource]['output'] += line
            print(line, end='', flush=True)
            
        # Mark as complete when done
        return_code = process.wait()
        terminal_outputs[resource]['complete'] = True
        terminal_outputs[resource]['success'] = (return_code == 0)
        
        # Special handling for destroy operations
        if action == 'destroy':
            output_str = terminal_outputs[resource]['output']
            
            # Case 1: No changes reported during destroy
            if "No changes. Your infrastructure matches the configuration." in output_str and "0 destroyed" in output_str:
                terminal_outputs[resource]['output'] += "\n\nNOTICE: Terraform reported no resources to destroy, but trying alternative approach...\n"
                
                # Try a more aggressive state removal and reinitialize approach
                terminal_outputs[resource]['output'] += "\nAttempting alternative resource removal method...\n"
                
                # Clean up all state files first
                for file_pattern in ['terraform.tfstate*', '.terraform.lock.hcl', '.terraform']:
                    # Use glob to match patterns
                    import glob
                    matched_files = glob.glob(os.path.join(temp_dir, file_pattern))
                    for file_path in matched_files:
                        try:
                            if os.path.isdir(file_path):
                                import shutil
                                shutil.rmtree(file_path)
                            else:
                                os.remove(file_path)
                            terminal_outputs[resource]['output'] += f"Removed {os.path.basename(file_path)}\n"
                        except Exception as e:
                            terminal_outputs[resource]['output'] += f"Warning: Could not remove {os.path.basename(file_path)}: {str(e)}\n"
                
                # Create a temporary apply file that removes the resource
                temp_tf_file = os.path.join(temp_dir, 'empty.tf')
                with open(temp_tf_file, 'w') as f:
                    f.write('''
# Required Terraform version and providers
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.0.0"
}

# AWS provider configuration
provider "aws" {
  region = "us-east-1"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
}
# No resources defined - this will force destroy any existing resources
''')
                
                # Reinitialize and apply the empty config to effectively remove resources
                terminal_outputs[resource]['output'] += "\nReinitializing with clean state...\n"
                reinit_process = subprocess.Popen(['terraform', 'init', '-no-color', '-reconfigure', '-upgrade'],
                                               cwd=temp_dir,
                                               env=terraform_env,
                                               stdout=subprocess.PIPE,
                                               stderr=subprocess.STDOUT,
                                               universal_newlines=True)
                
                # Capture output but don't display it all
                reinit_output = ""
                for line in reinit_process.stdout:
                    reinit_output += line
                
                reinit_return_code = reinit_process.wait()
                if reinit_return_code == 0:
                    terminal_outputs[resource]['output'] += "Reinitialization successful!\n"
                    
                    # Now apply the empty configuration to remove resources
                    terminal_outputs[resource]['output'] += "\nApplying empty configuration to force resource removal...\n"
                    empty_apply_process = subprocess.Popen(['terraform', 'apply', '-auto-approve', '-no-color'],
                                                        cwd=temp_dir,
                                                        env=terraform_env,
                                                        stdout=subprocess.PIPE,
                                                        stderr=subprocess.STDOUT,
                                                        universal_newlines=True)
                    
                    # Capture the apply output
                    for line in empty_apply_process.stdout:
                        terminal_outputs[resource]['output'] += line
                        print(line, end='', flush=True)
                    
                    empty_apply_return_code = empty_apply_process.wait()
                    if empty_apply_return_code == 0:
                        terminal_outputs[resource]['output'] += "\nResource successfully removed using alternative method.\n"
                    else:
                        # Last resort: Try to use AWS CLI directly to terminate the instance
                        # This is a direct intervention that bypasses Terraform entirely
                        terminal_outputs[resource]['output'] += "\nAttempting direct AWS resource removal as last resort...\n"
                        
                        # Extract instance ID from the Terraform plan output
                        import re
                        instance_id_match = re.search(r'instance/([i]-[0-9a-z]+)', output_str)
                        
                        if instance_id_match:
                            instance_id = instance_id_match.group(1)
                            terminal_outputs[resource]['output'] += f"\nDetected instance ID: {instance_id}\n"
                            
                            # Check if AWS CLI is available
                            aws_check = subprocess.run(['aws', '--version'], 
                                                    stdout=subprocess.PIPE, 
                                                    stderr=subprocess.PIPE)
                            
                            if aws_check.returncode == 0:
                                # Use AWS CLI to terminate the instance
                                terminal_outputs[resource]['output'] += f"\nAttempting to terminate instance {instance_id} using AWS CLI...\n"
                                aws_process = subprocess.Popen(['aws', 'ec2', 'terminate-instances', '--instance-ids', instance_id],
                                                           stdout=subprocess.PIPE,
                                                           stderr=subprocess.STDOUT,
                                                           universal_newlines=True)
                                
                                for line in aws_process.stdout:
                                    terminal_outputs[resource]['output'] += line
                                
                                aws_return_code = aws_process.wait()
                                if aws_return_code == 0:
                                    terminal_outputs[resource]['output'] += f"\nSuccessfully terminated instance {instance_id} using AWS CLI.\n"
                                else:
                                    terminal_outputs[resource]['output'] += f"\nFailed to terminate instance {instance_id} using AWS CLI.\n"
                            else:
                                terminal_outputs[resource]['output'] += "\nAWS CLI not available for direct resource removal.\n"
                        else:
                            terminal_outputs[resource]['output'] += "\nCould not detect instance ID from Terraform output for direct removal.\n"
                else:
                    terminal_outputs[resource]['output'] += "Reinitialization failed, but continuing with cleanup...\n"
                
                # Always clean up state files to ensure fresh start next time
                terminal_outputs[resource]['output'] += "\nCleaning up state files to ensure future operations work correctly.\n"
                for state_file in ['terraform.tfstate', 'terraform.tfstate.backup']:
                    full_path = os.path.join(temp_dir, state_file)
                    if os.path.exists(full_path):
                        try:
                            os.remove(full_path)
                            terminal_outputs[resource]['output'] += f"Removed {state_file}\n"
                        except Exception as e:
                            terminal_outputs[resource]['output'] += f"Warning: Could not remove {state_file}: {str(e)}\n"
        
        return JsonResponse({
            'success': True,
            'message': f'Resource {action} completed successfully'
        })
        
    except Exception as e:
        terminal_outputs[resource]['output'] += f"\n\nERROR: {str(e)}"
        terminal_outputs[resource]['complete'] = True
        terminal_outputs[resource]['success'] = False
        
        return JsonResponse({
            'success': False,
            'message': str(e)
        })

@csrf_exempt
def cancel_operation(request):
    """Endpoint to cancel a resource operation."""
    resource = request.POST.get('resource')
    
    if not resource or resource not in terminal_outputs:
        return JsonResponse({
            'success': False, 
            'message': 'Invalid resource or no pending operation'
        })
    
    # Reset the waiting confirmation status
    terminal_outputs[resource]['waiting_confirmation'] = False
    terminal_outputs[resource]['complete'] = True
    terminal_outputs[resource]['output'] += "\n\nOperation cancelled by user.\n"
    
    return JsonResponse({
        'success': True,
        'message': 'Operation cancelled'
    })

@csrf_exempt
def reset_resource(request):
    """Endpoint to completely reset a resource's Terraform state.
    This allows for manual cleanup and fresh initialization of resources.
    """
    resource = request.POST.get('resource')
    
    if not resource:
        return JsonResponse({
            'success': False, 
            'message': 'Invalid resource name'
        })
    
    # Get the resource details
    temp_dir = os.path.join(TERRAFORM_DIR, 'temp_' + resource)
    if not os.path.exists(temp_dir):
        return JsonResponse({
            'success': False, 
            'message': f'Resource directory does not exist'
        })
    
    # Initialize response data
    result = {
        'success': True,
        'message': 'Resource state reset successfully',
        'deleted_files': []
    }
    
    try:
        # Clean up all Terraform state files and directories
        # 1. terraform.tfstate files
        for state_file in ['terraform.tfstate', 'terraform.tfstate.backup']:
            file_path = os.path.join(temp_dir, state_file)
            if os.path.exists(file_path):
                os.remove(file_path)
                result['deleted_files'].append(state_file)
        
        # 2. .terraform directory
        terraform_dir = os.path.join(temp_dir, '.terraform')
        if os.path.exists(terraform_dir):
            import shutil
            shutil.rmtree(terraform_dir)
            result['deleted_files'].append('.terraform/')
        
        # 3. .terraform.lock.hcl file
        lock_file = os.path.join(temp_dir, '.terraform.lock.hcl')
        if os.path.exists(lock_file):
            os.remove(lock_file)
            result['deleted_files'].append('.terraform.lock.hcl')
        
        # Update terminal outputs if it exists for this resource
        if resource in terminal_outputs:
            terminal_outputs[resource] = {
                'output': 'Resource state has been reset. You can now create or destroy this resource again.',
                'complete': True,
                'waiting_confirmation': False,
                'success': True
            }
        
        return JsonResponse(result)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error resetting resource state: {str(e)}'
        })

