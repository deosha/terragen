output "bucket_name" {
  description = "The name of the GCS bucket"
  value       = google_storage_bucket.main.name
}

output "bucket_url" {
  description = "The base URL of the bucket, in the format gs://<bucket-name>"
  value       = google_storage_bucket.main.url
}

output "bucket_self_link" {
  description = "The URI of the created bucket"
  value       = google_storage_bucket.main.self_link
}

output "bucket_location" {
  description = "The location of the bucket"
  value       = google_storage_bucket.main.location
}

output "bucket_storage_class" {
  description = "The storage class of the bucket"
  value       = google_storage_bucket.main.storage_class
}

output "versioning_enabled" {
  description = "Whether versioning is enabled for the bucket"
  value       = google_storage_bucket.main.versioning[0].enabled
}

output "logs_bucket_name" {
  description = "The name of the logs bucket"
  value       = google_storage_bucket.logs.name
}

output "logs_bucket_url" {
  description = "The base URL of the logs bucket"
  value       = google_storage_bucket.logs.url
}

output "bucket_lifecycle_rules" {
  description = "The lifecycle rules configured for the bucket"
  value = [
    for rule in google_storage_bucket.main.lifecycle_rule : {
      action    = rule.action
      condition = rule.condition
    }
  ]
}