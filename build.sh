#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -o errexit

# 1. Install dependencies
pip install -r requirements.txt

# 2. Collect Static Files
python manage.py collectstatic --no-input

# 3. Apply Database Migrations (THE FIX!)
python manage.py migrate