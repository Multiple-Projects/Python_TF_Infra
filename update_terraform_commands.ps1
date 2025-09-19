$filePath = "d:\Study practice\ZZ_Project\Python_Django_TF_Infra\aws_manager\views.py"
$fileContent = Get-Content -Path $filePath -Raw

# First replacement: Update the create_resource function
$oldPattern1 = @'
                # Clean up any .terraform directories to start fresh
                terraform_dir = os.path.join(temp_dir, '.terraform')
                if os.path.exists(terraform_dir):
                    import shutil
                    try:
                        shutil.rmtree(terraform_dir)
                        terminal_outputs[resource]['output'] += "\nRemoved existing .terraform directory for clean initialization\n"
                    except Exception as e:
                        terminal_outputs[resource]['output'] += f"\nWarning: Could not remove .terraform directory: {str(e)}\n"
                
                # Run terraform init with detailed error handling and force reconfiguration
                init_process = subprocess.Popen(['terraform', 'init', '-no-color', '-reconfigure'], 
'@

$newPattern1 = @'
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
'@

# Replace the patterns
$fileContent = $fileContent -replace [regex]::Escape($oldPattern1), $newPattern1

# Second replacement: Update the destroy_resource function
$oldPattern2 = @'
                # Provider configuration is now in main.tf
                
                # Clean up any .terraform directories to start fresh
                terraform_dir = os.path.join(temp_dir, '.terraform')
                if os.path.exists(terraform_dir):
                    import shutil
                    try:
                        shutil.rmtree(terraform_dir)
                        terminal_outputs[resource]['output'] += "\nRemoved existing .terraform directory for clean initialization\n"
                    except Exception as e:
                        terminal_outputs[resource]['output'] += f"\nWarning: Could not remove .terraform directory: {str(e)}\n"
                
                # Run terraform init with detailed error handling and force reconfiguration
                init_process = subprocess.Popen(['terraform', 'init', '-no-color', '-reconfigure'], 
'@

$newPattern2 = @'
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
'@

# Replace the second pattern
$fileContent = $fileContent -replace [regex]::Escape($oldPattern2), $newPattern2

# Save the modified content back to the file
$fileContent | Set-Content -Path $filePath

Write-Host "File successfully updated"