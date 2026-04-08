#!/usr/bin/env bash
set -euo pipefail

echo "=== a2a Setup ==="

# Remove stale venv (may have hardcoded paths from a previous directory)
if [ -d ".venv" ]; then
    echo "Removing existing .venv..."
    rm -rf .venv
fi

# Install dependencies
echo "Installing dependencies..."
uv sync
uv pip install -e ".[dev]"

# Install Playwright browsers
echo "Installing Playwright browsers..."
uv run playwright install chromium firefox

# Create .env from example if it doesn't exist
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from .env.example — fill in your GEMINI_API_KEY."
else
    echo ".env already exists, skipping."
fi

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Add your Gemini API key to .env"
echo "  2. Edit config.yaml with your search parameters"
echo "  3. Run: uv run python -m src.main"
