# Random suffix for bucket name uniqueness
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# Logging bucket (for access logs) - created first to avoid dependency issues
resource "google_storage_bucket" "logs" {
  name                        = "${var.bucket_name}-logs-${random_id.bucket_suffix.hex}"
  location                    = var.location
  storage_class               = "COLDLINE"
  force_destroy               = var.force_destroy
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  labels = merge(var.labels, {
    purpose = "access-logs"
  })

  versioning {
    enabled = false
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 90 # Delete logs after 90 days
    }
  }
}

# GCS Bucket with versioning
resource "google_storage_bucket" "main" {
  name                        = "${var.bucket_name}-${random_id.bucket_suffix.hex}"
  location                    = var.location
  storage_class               = var.storage_class
  force_destroy               = var.force_destroy
  uniform_bucket_level_access = var.uniform_bucket_level_access
  public_access_prevention    = var.public_access_prevention

  labels = var.labels

  # Enable versioning
  versioning {
    enabled = var.versioning_enabled
  }

  # Lifecycle management
  dynamic "lifecycle_rule" {
    for_each = var.lifecycle_rules
    content {
      action {
        type          = lifecycle_rule.value.action.type
        storage_class = lifecycle_rule.value.action.storage_class
      }
      condition {
        age                        = lifecycle_rule.value.condition.age
        created_before             = lifecycle_rule.value.condition.created_before
        with_state                 = lifecycle_rule.value.condition.with_state
        matches_storage_class      = lifecycle_rule.value.condition.matches_storage_class
        num_newer_versions         = lifecycle_rule.value.condition.num_newer_versions
        custom_time_before         = lifecycle_rule.value.condition.custom_time_before
        days_since_custom_time     = lifecycle_rule.value.condition.days_since_custom_time
        days_since_noncurrent_time = lifecycle_rule.value.condition.days_since_noncurrent_time
        noncurrent_time_before     = lifecycle_rule.value.condition.noncurrent_time_before
      }
    }
  }

  # CORS configuration (if needed for web applications)
  cors {
    origin          = ["*"]
    method          = ["GET", "HEAD", "PUT", "POST", "DELETE"]
    response_header = ["*"]
    max_age_seconds = 3600
  }

  # Website configuration (optional)
  website {
    main_page_suffix = "index.html"
    not_found_page   = "404.html"
  }

  # Logging configuration
  logging {
    log_bucket        = google_storage_bucket.logs.name
    log_object_prefix = "access-logs/"
  }
}

# IAM binding for bucket access (optional - adjust as needed)
resource "google_storage_bucket_iam_member" "bucket_admin" {
  count  = length(var.bucket_admins)
  bucket = google_storage_bucket.main.name
  role   = "roles/storage.admin"
  member = var.bucket_admins[count.index]
}

resource "google_storage_bucket_iam_member" "bucket_viewer" {
  count  = length(var.bucket_viewers)
  bucket = google_storage_bucket.main.name
  role   = "roles/storage.objectViewer"
  member = var.bucket_viewers[count.index]
}