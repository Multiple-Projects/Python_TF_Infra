import os
import subprocess
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

TERRAFORM_DIR = os.path.join(os.path.dirname(__file__), 'terraform')

RESOURCE_FILES = {
    'ec2': 'ec2.tf',
    's3': 's3.tf',
    'loadbalancer': 'loadbalancer.tf',
    'vpc': 'vpc.tf',
    'asg_with_ec2': 'asg_with_ec2.tf',
}

def check_resource_exists(resource):
    """Check if a resource exists by looking for the terraform.tfstate file"""
    temp_dir = os.path.join(TERRAFORM_DIR, 'temp_' + resource)
    tfstate_path = os.path.join(temp_dir, 'terraform.tfstate')
    
    # If the directory and state file exist, check if the resource exists
    if os.path.exists(tfstate_path):
        try:
            # Run terraform state list to check if resources exist
            result = subprocess.run(['terraform', 'state', 'list'], 
                                   cwd=temp_dir, capture_output=True, text=True)
            # If there are resources in the state, return True
            return result.returncode == 0 and result.stdout.strip() != ''
        except Exception:
            pass
    return False

def index(request):
    # Check which resources exist
    resources_state = {
        resource: check_resource_exists(resource)
        for resource in RESOURCE_FILES.keys()
    }
    
    return render(request, 'aws_manager/index.html', {'resources_state': resources_state})

@csrf_exempt
def get_resource_display_name(resource):
    """Helper function to get the display name for a resource"""
    return {
        'ec2': 'EC2 Instance',
        's3': 'S3 Bucket',
        'loadbalancer': 'Load Balancer',
        'vpc': 'VPC',
        'asg_with_ec2': 'ASG with EC2',
    }.get(resource, resource)

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
        return JsonResponse({'success': False, 'message': 'Invalid resource'})
    
    tf_path = os.path.join(TERRAFORM_DIR, tf_file)
    temp_dir = os.path.join(TERRAFORM_DIR, 'temp_' + resource)
    
    # Create a temporary directory for this specific resource
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        print(f"Created temporary directory: {temp_dir}")
    
    resource_display_name = get_resource_display_name(resource)
    
    try:
        # Read the source Terraform file
        with open(tf_path, 'r') as src:
            tf_content = src.read()
        
        # Modify the Terraform file based on resource type and parameters
        if resource == 's3':
            # For S3, replace the bucket name with user-provided name and set count
            tf_content = tf_content.replace(
                'count  = 1  # Default to 1',
                f'count  = {resource_count}  # Set by user'
            )
            tf_content = tf_content.replace(
                'bucket = "django-s3-bucket-${count.index}-${random_id.bucket_id.hex}"',
                f'bucket = "{resource_name.lower()}-${{count.index + 1}}-${{random_id.bucket_id.hex}}"'
            )
            # Also update the ownership controls count
            tf_content = tf_content.replace(
                'count  = 1  # Match the count from the bucket',
                f'count  = {resource_count}  # Match the bucket count'
            )
        elif resource == 'ec2':
            # For EC2, add count and name tag
            tf_content = tf_content.replace(
                'resource "aws_instance" "ec2_instance" {',
                f'resource "aws_instance" "ec2_instance" {{\n  count = {resource_count}'
            )
            tf_content = tf_content.replace(
                'tags = {',
                f'tags = {{\n    Name = "{resource_name}-${{count.index + 1}}"'
            )
        elif resource == 'vpc':
            # For VPC, replace the name tag
            tf_content = tf_content.replace(
                'Name = "DjangoVPC"',
                f'Name = "{resource_name}"'
            )
        elif resource == 'loadbalancer':
            # For Load Balancer, replace the name
            tf_content = tf_content.replace(
                'name = "django-lb"',
                f'name = "{resource_name}"'
            )
        elif resource == 'asg_with_ec2':
            # For ASG, replace the name
            tf_content = tf_content.replace(
                'name = "example-asg"',
                f'name = "{resource_name}"'
            )
            tf_content = tf_content.replace(
                'value = "ASGWithEC2"',
                f'value = "{resource_name}"'
            )
        
        # Write the modified content to the temporary directory
        with open(os.path.join(temp_dir, 'main.tf'), 'w') as dst:
            dst.write(tf_content)
        
        # Inform user that creation is in progress
        creation_message = f"{resource_display_name} is getting created..."
        
        # Run terraform init and apply in the temp directory
        init_result = subprocess.run(['terraform', 'init'], cwd=temp_dir, capture_output=True, text=True)
        
        # Add the init output to our combined output
        combined_output = f"Initializing Terraform...\n{init_result.stdout}\n\n"
        
        # First run terraform plan to show what will be created
        plan_result = subprocess.run(['terraform', 'plan'], 
                                   cwd=temp_dir, capture_output=True, text=True)
        combined_output += f"Planning resource creation...\n{plan_result.stdout}\n\n"
        
        # Then run terraform apply to create the resources
        result = subprocess.run(['terraform', 'apply', '-auto-approve'], 
                                cwd=temp_dir, capture_output=True, text=True)
        
        combined_output += f"Applying Terraform configuration...\n{result.stdout}"
        
        if result.returncode == 0:
            return JsonResponse({
                'success': True, 
                'message': f'{resource_display_name} successfully created!', 
                'output': combined_output,
                'resource_name': resource_display_name, 
                'status': f"{resource_display_name} successfully created!"
            })
        else:
            error_output = combined_output + f"\n\nERROR:\n{result.stderr}"
            return JsonResponse({
                'success': False, 
                'message': 'Error creating resource', 
                'output': error_output,
                'resource_name': resource_display_name, 
                'status': 'Error during creation'
            })
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'message': str(e), 
            'resource_name': resource_display_name, 
            'status': 'Error during creation'
        })

@csrf_exempt
def destroy_resource(request):
    resource = request.POST.get('resource')
    tf_file = RESOURCE_FILES.get(resource)
    if not tf_file:
        return JsonResponse({'success': False, 'message': 'Invalid resource'})
    
    temp_dir = os.path.join(TERRAFORM_DIR, 'temp_' + resource)
    
    # Check if the temporary directory exists
    if not os.path.exists(temp_dir):
        return JsonResponse({
            'success': False,
            'message': f'Resource directory not found. The {resource} may not have been created yet.',
            'resource_name': get_resource_display_name(resource),
            'status': 'Error during destruction'
        })
    
    resource_display_name = get_resource_display_name(resource)
    
    try:
        # Inform user that destruction is in progress
        destruction_message = f"{resource_display_name} is being destroyed..."
        
        # First run terraform plan to show what will be destroyed
        plan_result = subprocess.run(['terraform', 'plan', '-destroy'], 
                                   cwd=temp_dir, capture_output=True, text=True)
        combined_output = f"Planning resource destruction...\n{plan_result.stdout}\n\n"
        
        # Run terraform destroy in the temp directory
        result = subprocess.run(['terraform', 'destroy', '-auto-approve'], 
                               cwd=temp_dir, capture_output=True, text=True)
        
        combined_output += f"Destroying resources...\n{result.stdout}"
        
        if result.returncode == 0:
            return JsonResponse({
                'success': True, 
                'message': f'{resource_display_name} successfully destroyed!', 
                'output': combined_output,
                'resource_name': resource_display_name, 
                'status': f"{resource_display_name} successfully destroyed!"
            })
        else:
            error_output = combined_output + f"\n\nERROR:\n{result.stderr}"
            return JsonResponse({
                'success': False, 
                'message': 'Error destroying resource', 
                'output': error_output,
                'resource_name': resource_display_name, 
                'status': 'Error during destruction'
            })
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'message': str(e), 
            'resource_name': resource_display_name, 
            'status': 'Error during destruction'
        })
