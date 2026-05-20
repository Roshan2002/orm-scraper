#!/bin/bash
# Runs the scraper locally using credentials from .env.json
cd "$(dirname "$0")"
python3 scraper.py >> ../scraper.log 2>&1
