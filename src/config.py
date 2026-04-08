from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class AIConfig(BaseModel):
    model: str
    max_tokens: int
    temperature: float


class ScrapingConfig(BaseModel):
    headless: bool
    request_delay_ms: int
    max_listings_per_site: int
    max_retries: int
    proxies: list[str] = Field(default_factory=list)


class CookieConfig(BaseModel):
    name: str
    value: str
    domain: str


class SiteConfig(BaseModel):
    name: str
    enabled: bool
    base_url: str
    url_builder: str
    strategy: str
    cookies: list[CookieConfig] = Field(default_factory=list)


class SearchConfig(BaseModel):
    city: str = ""
    neighborhood: str = ""
    anchor_address: str = ""
    anchor_lat: float | None = None   # geocoded at startup from anchor_address
    anchor_lng: float | None = None   # geocoded at startup from anchor_address
    max_distance_km: float | None = None
    move_in_date: str = ""
    lease_duration_months: int | None = None
    min_bedrooms: int | None = None
    max_bedrooms: int | None = None
    min_bathrooms: int | None = None
    unit_types: list[str] = Field(default_factory=list)
    max_monthly_rent: float | None = None
    min_monthly_rent: float | None = None
    min_sqft: int | None = None


class RequirementsConfig(BaseModel):
    max_monthly_rent: float | None = None
    min_bedrooms: int | None = None
    max_distance_km: float | None = None
    must_be_furnished: bool | None = None
    must_allow_pets: bool | None = None
    must_have_laundry: bool | None = None
    must_have_parking: bool | None = None
    short_term_ok: bool = True
    allowed_neighborhoods: list[str] = Field(default_factory=list)


class PreferenceConfig(BaseModel):
    name: str
    enabled: bool
    weight: float
    description: str
    type: str
    field: str | None = None
    values: list[str] = Field(default_factory=list)  # used by neighborhood_match type


class OutputConfig(BaseModel):
    directory: str
    formats: list[str]
    open_html_on_complete: bool


class AppConfig(BaseModel):
    ai: AIConfig
    scraping: ScrapingConfig
    websites: list[SiteConfig]
    search: SearchConfig
    requirements: RequirementsConfig
    preferences: list[PreferenceConfig]
    output: OutputConfig
    gemini_api_key: str


def load_config(config_path: str = "config.yaml") -> AppConfig:
    load_dotenv()

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env or environment")

    return AppConfig(
        ai=AIConfig(**raw["ai"]),
        scraping=ScrapingConfig(**raw["scraping"]),
        websites=[SiteConfig(**w) for w in raw["websites"]],
        search=SearchConfig(**raw["search"]),
        requirements=RequirementsConfig(**raw["requirements"]),
        preferences=[PreferenceConfig(**p) for p in raw["preferences"]],
        output=OutputConfig(**raw["output"]),
        gemini_api_key=api_key,
    )
