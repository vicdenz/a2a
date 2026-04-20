from __future__ import annotations

import csv
import json
import os
import platform
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.config import OutputConfig, PreferenceConfig
from src.extractor.schema import Listing


def _serialize_listing(listing: Listing) -> dict:
    data = listing.model_dump()
    # Convert datetime to ISO string for JSON
    if isinstance(data.get("scraped_at"), datetime):
        data["scraped_at"] = data["scraped_at"].isoformat()
    return data


def generate_output(
    listings: list[Listing],
    output_config: OutputConfig,
    preferences: list[PreferenceConfig],
    total_scraped: int,
    sites_count: int,
) -> None:
    """Write output files: HTML report, JSON, and CSV."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_dir = Path(output_config.directory) / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Output directory: {out_dir}")

    # Compute max possible score for the score bar
    max_score = sum(p.weight for p in preferences if p.enabled) or 1

    if "json" in output_config.formats:
        json_path = out_dir / "listings.json"
        with open(json_path, "w") as f:
            json.dump([_serialize_listing(l) for l in listings], f, indent=2)
        print(f"  Wrote {json_path}")

    if "csv" in output_config.formats:
        csv_path = out_dir / "listings.csv"
        fieldnames = [
            "rank", "passed_filter", "filter_reason", "score", "source",
            "title", "monthly_rent", "bedrooms", "bathrooms", "furnished",
            "distance_km", "neighbourhood", "address", "lease_term", "url",
        ]
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for i, listing in enumerate(listings, 1):
                writer.writerow({
                    "rank": i,
                    "passed_filter": listing.passed_filter,
                    "filter_reason": listing.filter_reason,
                    "score": listing.score,
                    "source": listing.source,
                    "title": listing.title,
                    "monthly_rent": listing.monthly_rent,
                    "bedrooms": listing.bedrooms,
                    "bathrooms": listing.bathrooms,
                    "furnished": listing.furnished,
                    "distance_km": listing.distance_km,
                    "neighbourhood": listing.neighbourhood,
                    "address": listing.address,
                    "lease_term": listing.lease_term,
                    "url": listing.url,
                })
        print(f"  Wrote {csv_path}")

    if "html" in output_config.formats:
        html_path = out_dir / "report.html"
        template_dir = Path(__file__).parent / "templates"
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template("report.html.j2")

        # Build active filter descriptions
        active_filters: list[str] = []
        for p in preferences:
            if p.enabled:
                active_filters.append(f"{p.name} (w={p.weight})")

        passed_count = sum(1 for l in listings if l.passed_filter)
        rendered = template.render(
            listings=listings,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            total_scraped=total_scraped,
            total_filtered=passed_count,
            total_listings=len(listings),
            sites_count=sites_count,
            active_filters=active_filters,
            max_score=max_score,
        )
        with open(html_path, "w") as f:
            f.write(rendered)
        print(f"  Wrote {html_path}")

        if output_config.open_html_on_complete:
            abs_path = str(html_path.resolve())
            if platform.system() == "Darwin":
                subprocess.run(["open", abs_path])
            elif platform.system() == "Linux":
                subprocess.run(["xdg-open", abs_path])
            else:
                webbrowser.open(f"file://{abs_path}")
