provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "example" {
  count  = 1  # Default to 1, will be overridden by the views.py file
  bucket = "django-s3-bucket-${count.index}-${random_id.bucket_id.hex}"
}

# Enable ACL for the bucket
resource "aws_s3_bucket_ownership_controls" "example_ownership" {
  count  = 1  # Match the count from the bucket resource
  bucket = aws_s3_bucket.example[count.index].id
  
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

# Enable public access block for security
resource "aws_s3_bucket_public_access_block" "example_public_access" {
  count  = 1  # Match the count from the bucket resource
  bucket = aws_s3_bucket.example[count.index].id
  
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "random_id" "bucket_id" {
  byte_length = 4
}
