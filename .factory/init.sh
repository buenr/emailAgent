#!/usr/bin/env bash
# Idempotent environment setup for mission workers.
set -euo pipefail

REPO_ROOT="/mnt/c/users/RNA/Documents/Python Scripts/Email_Tagging_UI"

# Install Node.js dependencies if not already present.
if [ ! -d "$REPO_ROOT/web/node_modules" ]; then
  echo "Installing web dependencies..."
  cd "$REPO_ROOT/web" && npm install
else
  echo "web/node_modules already exists, skipping npm install."
fi

# Create venv if not present, install Python dependencies.
if [ ! -d "$REPO_ROOT/.venv" ]; then
  echo "Creating Python virtual environment..."
  cd "$REPO_ROOT" && python3 -m venv .venv
fi
if ! "$REPO_ROOT/.venv/bin/python" -c "import fastapi" 2>/dev/null; then
  echo "Installing Python dependencies..."
  cd "$REPO_ROOT" && .venv/bin/pip install -r requirements.txt 2>/dev/null || echo "Warning: full pip install failed, trying core packages..." && .venv/bin/pip install fastapi uvicorn pydantic python-dotenv httpx passlib bcrypt msal itsdangerous beautifulsoup4 lxml 2>/dev/null || echo "Warning: pip install failed, dependencies may need manual setup."
else
  echo "Python dependencies already installed."
fi

# Initialize shadcn/ui if not already configured.
if [ ! -f "$REPO_ROOT/web/components.json" ]; then
  echo "Initializing shadcn/ui..."
  cd "$REPO_ROOT/web" && npx shadcn@latest init -d --defaults 2>/dev/null || echo "shadcn init already done or needs manual setup."
else
  echo "shadcn/ui already configured (components.json exists)."
fi

echo "Environment setup complete."
