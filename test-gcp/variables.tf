variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "The GCP zone"
  type        = string
  default     = "us-central1-a"
}

variable "bucket_name" {
  description = "The name of the GCS bucket"
  type        = string
}

variable "storage_class" {
  description = "The storage class of the bucket"
  type        = string
  default     = "STANDARD"
  validation {
    condition = contains([
      "STANDARD",
      "NEARLINE",
      "COLDLINE",
      "ARCHIVE"
    ], var.storage_class)
    error_message = "Storage class must be STANDARD, NEARLINE, COLDLINE, or ARCHIVE."
  }
}

variable "location" {
  description = "The location of the bucket"
  type        = string
  default     = "US-CENTRAL1"
}

variable "force_destroy" {
  description = "When deleting a bucket, this boolean option will delete all contained objects"
  type        = bool
  default     = false
}

variable "uniform_bucket_level_access" {
  description = "Enables uniform bucket-level access"
  type        = bool
  default     = true
}

variable "public_access_prevention" {
  description = "Prevents public access to a bucket"
  type        = string
  default     = "enforced"
  validation {
    condition = contains([
      "enforced",
      "inherited"
    ], var.public_access_prevention)
    error_message = "Public access prevention must be 'enforced' or 'inherited'."
  }
}

variable "versioning_enabled" {
  description = "Enable versioning for the bucket"
  type        = bool
  default     = true
}

variable "lifecycle_rules" {
  description = <<-EOT
    List of lifecycle rules for the bucket. Each rule defines actions and conditions for object lifecycle management.
    
    Available actions:
    - Delete: Delete objects
    - SetStorageClass: Change storage class (STANDARD, NEARLINE, COLDLINE, ARCHIVE)
    
    Available conditions:
    - age: Age of object in days
    - created_before: Date in RFC 3339 format (e.g., "2023-01-01")
    - with_state: Object state (LIVE, ARCHIVED, ANY)
    - matches_storage_class: List of storage classes to match
    - num_newer_versions: Number of newer versions (for versioned objects)
    - custom_time_before: Custom time before date
    - days_since_custom_time: Days since custom time
    - days_since_noncurrent_time: Days since object became noncurrent
    - noncurrent_time_before: Noncurrent time before date
  EOT
  type = list(object({
    action = object({
      type          = string
      storage_class = optional(string)
    })
    condition = object({
      age                        = optional(number)
      created_before             = optional(string)
      with_state                 = optional(string)
      matches_storage_class      = optional(list(string))
      num_newer_versions         = optional(number)
      custom_time_before         = optional(string)
      days_since_custom_time     = optional(number)
      days_since_noncurrent_time = optional(number)
      noncurrent_time_before     = optional(string)
    })
  }))
  default = [
    # Transition STANDARD objects to NEARLINE after 30 days for cost optimization
    {
      action = {
        type          = "SetStorageClass"
        storage_class = "NEARLINE"
      }
      condition = {
        age                   = 30
        matches_storage_class = ["STANDARD"]
      }
    },
    # Transition NEARLINE objects to COLDLINE after 90 days for further cost savings
    {
      action = {
        type          = "SetStorageClass"
        storage_class = "COLDLINE"
      }
      condition = {
        age                   = 90
        matches_storage_class = ["NEARLINE"]
      }
    },
    # Transition COLDLINE objects to ARCHIVE after 180 days for maximum cost efficiency
    {
      action = {
        type          = "SetStorageClass"
        storage_class = "ARCHIVE"
      }
      condition = {
        age                   = 180
        matches_storage_class = ["COLDLINE"]
      }
    },
    # Delete objects after 2 years (730 days) to comply with retention policies
    {
      action = {
        type = "Delete"
      }
      condition = {
        age = 730
      }
    },
    # Clean up old versions: delete noncurrent versions after 30 days
    {
      action = {
        type = "Delete"
      }
      condition = {
        with_state                 = "ARCHIVED"
        days_since_noncurrent_time = 30
      }
    },
    # Limit number of versions: keep only 10 most recent versions
    {
      action = {
        type = "Delete"
      }
      condition = {
        num_newer_versions = 10
        with_state         = "ARCHIVED"
      }
    }
  ]
}

variable "logs_lifecycle_rules" {
  description = "Lifecycle rules for the access logs bucket"
  type = list(object({
    action = object({
      type          = string
      storage_class = optional(string)
    })
    condition = object({
      age                        = optional(number)
      created_before             = optional(string)
      with_state                 = optional(string)
      matches_storage_class      = optional(list(string))
      num_newer_versions         = optional(number)
      custom_time_before         = optional(string)
      days_since_custom_time     = optional(number)
      days_since_noncurrent_time = optional(number)
      noncurrent_time_before     = optional(string)
    })
  }))
  default = [
    # Transition logs to ARCHIVE after 30 days for cost optimization
    {
      action = {
        type          = "SetStorageClass"
        storage_class = "ARCHIVE"
      }
      condition = {
        age                   = 30
        matches_storage_class = ["COLDLINE"]
      }
    },
    # Delete access logs after 90 days (compliance requirement)
    {
      action = {
        type = "Delete"
      }
      condition = {
        age = 90
      }
    }
  ]
}

variable "enable_lifecycle_rules" {
  description = "Enable lifecycle rules for the bucket. Set to false to disable all lifecycle management"
  type        = bool
  default     = true
}

variable "labels" {
  description = "A set of key/value label pairs to assign to the bucket"
  type        = map(string)
  default = {
    environment = "production"
    managed_by  = "terraform"
  }
}

variable "bucket_admins" {
  description = "List of IAM members who should have admin access to the bucket"
  type        = list(string)
  default     = []
}

variable "bucket_viewers" {
  description = "List of IAM members who should have viewer access to the bucket"
  type        = list(string)
  default     = []
}