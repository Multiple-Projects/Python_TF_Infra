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
        
        # Copy the resource Terraform file
        src_file = os.path.join(TERRAFORM_DIR, tf_file)
        dest_file = os.path.join(temp_dir, tf_file)
        
        # Read the template content
        with open(src_file, 'r') as f:
            content = f.read()
        
        # Replace placeholders with actual values
        content = content.replace('__NAME__', resource_name)
        content = content.replace('__COUNT__', str(resource_count))
        
        # Write to the destination file
        with open(dest_file, 'w') as f:
            f.write(content)
        
        # Initialize terminal output tracking
        terminal_outputs[resource] = {
            'output': '',
            'complete': False,
            'waiting_confirmation': False,
            'success': False
        }
        
        # Define a function to run terraform commands in a background thread
        def run_terraform():
            try:
                # Set up environment with disabled color output
                terraform_env = os.environ.copy()
                # Use NO_COLOR which is a standard way to disable color output
                terraform_env['NO_COLOR'] = 'true'
                
                # Run terraform init
                terminal_outputs[resource]['output'] = "Initializing Terraform...\n"
                init_process = subprocess.Popen(['terraform', 'init'], 
                                              cwd=temp_dir,
                                              env=terraform_env,
                                              stdout=subprocess.PIPE, 
                                              stderr=subprocess.STDOUT,
                                              universal_newlines=True)
                
                # Process and capture real-time output
                for line in init_process.stdout:
                    terminal_outputs[resource]['output'] += line
                    print(line, end='', flush=True)
                
                init_process.wait()
                
                # Run terraform plan - not using auto-approve yet so the user can see the plan first
                terminal_outputs[resource]['output'] += "\n\nPlanning resource creation...\n"
                plan_process = subprocess.Popen(['terraform', 'plan'], 
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
                # Set up environment with disabled color output
                terraform_env = os.environ.copy()
                # Use NO_COLOR which is a standard way to disable color output
                terraform_env['NO_COLOR'] = 'true'
                
                # Run terraform init to make sure we have the latest providers
                terminal_outputs[resource]['output'] = "Initializing Terraform...\n"
                init_process = subprocess.Popen(['terraform', 'init'], 
                                              cwd=temp_dir,
                                              env=terraform_env,
                                              stdout=subprocess.PIPE, 
                                              stderr=subprocess.STDOUT,
                                              universal_newlines=True)
                
                # Process and capture real-time output
                for line in init_process.stdout:
                    terminal_outputs[resource]['output'] += line
                    print(line, end='', flush=True)
                
                init_process.wait()
                
                # Run terraform plan -destroy to show what will be destroyed
                terminal_outputs[resource]['output'] += "\n\nPlanning resource destruction...\n"
                plan_process = subprocess.Popen(['terraform', 'plan', '-destroy'], 
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

def get_terminal_output(request):
    """Get the terminal output for a specific resource operation."""
    resource = request.GET.get('resource')
    
    if not resource or resource not in terminal_outputs:
        return JsonResponse({
            'output': 'No output available for this resource.',
            'complete': True,
            'success': False
        })
    
    return JsonResponse(terminal_outputs[resource])

@csrf_exempt
def confirm_resource(request):
    """Endpoint to confirm resource creation or destruction after viewing the plan."""
    resource = request.POST.get('resource')
    action = request.POST.get('action')  # 'create' or 'destroy'
    
    if not resource or resource not in terminal_outputs:
        return JsonResponse({
            'success': False, 
            'message': 'Invalid resource or no pending operation'
        })
    
    # Get the resource details
    temp_dir = os.path.join(TERRAFORM_DIR, 'temp_' + resource)
    
    # Set up environment with disabled color output
    terraform_env = os.environ.copy()
    # Use NO_COLOR which is a standard way to disable color output
    terraform_env['NO_COLOR'] = 'true'
    
    try:
        # Update the output to show confirmation
        terminal_outputs[resource]['output'] += f"\n\n{action.title()} confirmed by user, executing...\n"
        terminal_outputs[resource]['waiting_confirmation'] = False
        
        if action == 'create':
            # Run terraform apply
            terminal_outputs[resource]['output'] += "\nApplying Terraform configuration...\n"
            process = subprocess.Popen(['terraform', 'apply', '-auto-approve'], 
                                      cwd=temp_dir,
                                      env=terraform_env,
                                      stdout=subprocess.PIPE, 
                                      stderr=subprocess.STDOUT,
                                      universal_newlines=True)
        else:  # action == 'destroy'
            # Run terraform destroy
            terminal_outputs[resource]['output'] += "\nDestroying resources...\n"
            process = subprocess.Popen(['terraform', 'destroy', '-auto-approve'], 
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
