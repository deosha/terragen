# GCP Configuration
project_id = "your-gcp-project-id"
region     = "us-central1"
zone       = "us-central1-a"

# Bucket Configuration
bucket_name                 = "my-storage-bucket"
storage_class               = "STANDARD"
location                    = "US-CENTRAL1"
force_destroy               = false
uniform_bucket_level_access = true
public_access_prevention    = "enforced"
versioning_enabled          = true

# Labels
labels = {
  environment = "production"
  managed_by  = "terraform"
  team        = "platform"
  cost_center = "infrastructure"
}

# IAM Members (update with your actual users/service accounts)
bucket_admins = [
  # "user:admin@yourdomain.com",
  # "serviceAccount:bucket-admin@your-project.iam.gserviceaccount.com"
]

bucket_viewers = [
  # "user:viewer@yourdomain.com",
  # "serviceAccount:app-service@your-project.iam.gserviceaccount.com"
]

# Custom lifecycle rules (optional - uncomment and modify as needed)
# lifecycle_rules = [
#   {
#     action = {
#       type = "SetStorageClass"
#       storage_class = "NEARLINE"
#     }
#     condition = {
#       age = 30
#     }
#   },
#   {
#     action = {
#       type = "SetStorageClass"
#       storage_class = "COLDLINE"
#     }
#     condition = {
#       age = 90
#     }
#   },
#   {
#     action = {
#       type = "Delete"
#     }
#     condition = {
#       age = 365
#     }
#   },
#   {
#     action = {
#       type = "Delete"
#     }
#     condition = {
#       with_state = "ARCHIVED"
#       days_since_noncurrent_time = 30
#     }
#   }
# ]