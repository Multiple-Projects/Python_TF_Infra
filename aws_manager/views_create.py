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
        
        # Import the output stream module
        from .stream import output_streams, get_stream_id
        
        # Create a unique stream ID for this operation
        stream_id = get_stream_id(resource)
        
        # Set up the output queue for this stream
        output_queue = Queue()
        output_streams[stream_id] = {
            "queue": output_queue,
            "active": True,
            "resource": resource
        }
        
        # Function to run terraform commands and update the queue
        def run_terraform_commands():
            combined_output = "Initializing Terraform...\n"
            
            # Add message to the queue
            output_queue.put("Initializing Terraform...\n")
            
            # Run terraform init
            init_process = subprocess.Popen(['terraform', 'init'], 
                                           cwd=temp_dir, 
                                           stdout=subprocess.PIPE, 
                                           stderr=subprocess.STDOUT,
                                           universal_newlines=True)
            
            # Process and capture real-time output
            for line in init_process.stdout:
                combined_output += line
                print(line, end='', flush=True)
                output_queue.put(line)
                
            init_process.wait()
            
            # Run terraform plan
            output_queue.put("\nPlanning resource creation...\n")
            combined_output += "\n\nPlanning resource creation...\n"
            
            plan_process = subprocess.Popen(['terraform', 'plan'], 
                                           cwd=temp_dir, 
                                           stdout=subprocess.PIPE, 
                                           stderr=subprocess.STDOUT,
                                           universal_newlines=True)
            
            # Process and capture real-time output
            for line in plan_process.stdout:
                combined_output += line
                print(line, end='', flush=True)
                output_queue.put(line)
                
            plan_process.wait()
            
            # Run terraform apply
            output_queue.put("\nApplying Terraform configuration...\n")
            combined_output += "\n\nApplying Terraform configuration...\n"
            
            result_process = subprocess.Popen(['terraform', 'apply', '-auto-approve'], 
                                            cwd=temp_dir, 
                                            stdout=subprocess.PIPE, 
                                            stderr=subprocess.STDOUT,
                                            universal_newlines=True)
            
            # Process and capture real-time output
            for line in result_process.stdout:
                combined_output += line
                print(line, end='', flush=True)
                output_queue.put(line)
                
            # Store the return code for checking if the command was successful
            return_code = result_process.wait()
            
            # Mark the stream as inactive
            output_streams[stream_id]["active"] = False
            
            # Send the final status message
            if return_code == 0:
                output_queue.put(f"\n{resource_display_name} successfully created!")
                success_status = {
                    'success': True, 
                    'message': f'{resource_display_name} successfully created!', 
                    'output': combined_output,
                    'resource_name': resource_display_name, 
                    'status': f"{resource_display_name} successfully created!"
                }
                output_streams[stream_id]["result"] = success_status
            else:
                error_message = "\nERROR: Terraform command failed"
                output_queue.put(error_message)
                error_status = {
                    'success': False, 
                    'message': 'Error creating resource', 
                    'output': combined_output + error_message,
                    'resource_name': resource_display_name, 
                    'status': 'Error during creation'
                }
                output_streams[stream_id]["result"] = error_status
            
            # Signal end of stream
            output_queue.put(None)
        
        # Start the terraform commands in a separate thread
        terraform_thread = threading.Thread(target=run_terraform_commands)
        terraform_thread.daemon = True
        terraform_thread.start()
        
        # Return immediately with the stream ID
        return JsonResponse({
            'success': True,
            'message': creation_message,
            'stream_id': stream_id,
            'resource_name': resource_display_name,
            'status': 'in_progress'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'message': str(e), 
            'resource_name': resource_display_name, 
            'status': 'Error during creation'
        })
