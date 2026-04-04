import os
import tempfile

import pytest
import yaml

from src.config import load_config


def _write_config(path, overrides=None):
    base = {
        "ai": {"model": "claude-sonnet-4-6", "max_tokens": 4096, "temperature": 0},
        "scraping": {
            "headless": True,
            "request_delay_ms": 1000,
            "max_listings_per_site": 10,
            "max_retries": 2,
            "proxies": [],
        },
        "websites": [
            {
                "name": "TestSite",
                "enabled": True,
                "base_url": "https://example.com",
                "url_builder": "kijiji",
                "strategy": "crawlee",
            }
        ],
        "search": {
            "city": "Toronto",
            "neighborhood": "",
            "anchor_address": "",
            "max_distance_km": None,
            "move_in_date": "",
            "lease_duration_months": None,
            "min_bedrooms": None,
            "max_bedrooms": None,
            "min_bathrooms": None,
            "unit_types": [],
            "max_monthly_rent": None,
            "min_monthly_rent": None,
            "min_sqft": None,
        },
        "requirements": {
            "max_monthly_rent": None,
            "min_bedrooms": None,
            "max_distance_km": None,
            "must_be_furnished": None,
            "must_allow_pets": None,
            "must_have_laundry": None,
            "must_have_parking": None,
            "short_term_ok": True,
        },
        "preferences": [],
        "output": {
            "directory": "./output",
            "formats": ["json"],
            "open_html_on_complete": False,
        },
    }
    if overrides:
        base.update(overrides)
    with open(path, "w") as f:
        yaml.dump(base, f)


def test_load_config_basic():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        _write_config(f.name)
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        try:
            config = load_config(f.name)
            assert config.ai.model == "claude-sonnet-4-6"
            assert config.search.city == "Toronto"
            assert len(config.websites) == 1
            assert config.anthropic_api_key == "test-key"
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)
            os.unlink(f.name)


def test_load_config_missing_api_key():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        _write_config(f.name)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                load_config(f.name)
        finally:
            os.unlink(f.name)


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/config.yaml")
