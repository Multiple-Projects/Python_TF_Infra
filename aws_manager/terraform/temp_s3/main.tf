provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "example" {
  count  = 2  # Set by user, will be overridden by the views.py file
  bucket = "demo-django-${count.index + 1}-${random_id.bucket_id.hex}"
}

# Enable ACL for the bucket
resource "aws_s3_bucket_ownership_controls" "example_ownership" {
  count  = 2  # Match the bucket count resource
  bucket = aws_s3_bucket.example[count.index].id
  
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

# Enable public access block for security
resource "aws_s3_bucket_public_access_block" "example_public_access" {
  count  = 2  # Match the bucket count resource
  bucket = aws_s3_bucket.example[count.index].id
  
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "random_id" "bucket_id" {
  byte_length = 4
}
