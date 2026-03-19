"""Tests for TerraGen configuration."""

import os
import pytest
from terragen.config import (
    get_default_region,
    get_region_examples,
    PROVIDER_REGIONS,
    MODEL,
    DEFAULT_MODEL,
)


class TestProviderRegions:
    """Test provider-specific region configurations."""

    def test_aws_default_region(self):
        """AWS should default to us-east-1."""
        assert get_default_region("aws") == "us-east-1"

    def test_gcp_default_region(self):
        """GCP should default to us-central1."""
        assert get_default_region("gcp") == "us-central1"

    def test_azure_default_region(self):
        """Azure should default to eastus."""
        assert get_default_region("azure") == "eastus"

    def test_unknown_provider_falls_back_to_aws(self):
        """Unknown provider should fall back to AWS defaults."""
        assert get_default_region("unknown") == "us-east-1"

    def test_aws_region_examples(self):
        """AWS should have valid region examples."""
        examples = get_region_examples("aws")
        assert "us-east-1" in examples
        assert "us-west-2" in examples
        assert len(examples) >= 4

    def test_gcp_region_examples(self):
        """GCP should have valid region examples."""
        examples = get_region_examples("gcp")
        assert "us-central1" in examples
        assert "europe-west1" in examples
        assert len(examples) >= 4

    def test_azure_region_examples(self):
        """Azure should have valid region examples."""
        examples = get_region_examples("azure")
        assert "eastus" in examples
        assert "westeurope" in examples
        assert len(examples) >= 4

    def test_provider_regions_structure(self):
        """PROVIDER_REGIONS should have correct structure."""
        for provider in ["aws", "gcp", "azure"]:
            assert provider in PROVIDER_REGIONS
            assert "default" in PROVIDER_REGIONS[provider]
            assert "examples" in PROVIDER_REGIONS[provider]
            assert "help" in PROVIDER_REGIONS[provider]


class TestModelConfig:
    """Test model configuration."""

    def test_default_model(self):
        """Default model should be Sonnet."""
        assert "sonnet" in DEFAULT_MODEL.lower()

    def test_model_env_override(self):
        """MODEL can be overridden via environment."""
        # MODEL is set at import time, so we just verify the default
        assert MODEL == os.environ.get("TERRAGEN_MODEL", DEFAULT_MODEL)
