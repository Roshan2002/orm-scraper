"""
LinkedIn decision-maker enricher.

Strategy (in order, stops when a result is found):
1. Google  site:linkedin.com/in  search  →  get profile URL (no login needed)
2. linkedin-api (unofficial)             →  get full name from profile URL
3. Fallback: return URL only, name blank
"""

import os
import re
import time
import random
import requests
from bs4 import BeautifulSoup

try:
    from linkedin_api import Linkedin as LinkedinAPI
    _LI_API_AVAILABLE = True
except ImportError:
    _LI_API_AVAILABLE = False

LINKEDIN_EMAIL = os.environ.get("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD = os.environ.get("LINKEDIN_PASSWORD", "")

TITLES = [
    "CEO", "Founder", "Co-Founder", "Owner",
    "Managing Director", "CMO", "Head of Marketing",
    "VP Marketing", "Director of Marketing",
]

GOOGLE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

_li_client = None


def _get_li_client():
    global _li_client
    if _li_client is None and _LI_API_AVAILABLE and LINKEDIN_EMAIL and LINKEDIN_PASSWORD:
        try:
            _li_client = LinkedinAPI(LINKEDIN_EMAIL, LINKEDIN_PASSWORD)
        except Exception as e:
            print(f"  LinkedIn API login failed: {e}")
    return _li_client


def _google_find_linkedin(company, title):
    query = f'site:linkedin.com/in "{title}" "{company}"'
    try:
        resp = requests.get(
            "https://www.google.com/search",
            params={"q": query, "num": 5, "hl": "en"},
            headers=GOOGLE_HEADERS,
            timeout=12,
        )
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "linkedin.com/in/" in href:
                if href.startswith("/url?q="):
                    href = href.split("/url?q=")[1].split("&")[0]
                match = re.search(r"linkedin\.com/in/([\w\-]+)", href)
                if match:
                    return f"https://www.linkedin.com/in/{match.group(1)}"
    except Exception:
        pass
    return None


def _get_name_from_api(public_id):
    client = _get_li_client()
    if not client:
        return ""
    try:
        profile = client.get_profile(public_id)
        first = profile.get("firstName", "")
        last = profile.get("lastName", "")
        return f"{first} {last}".strip()
    except Exception:
        return ""


def find_decision_maker(company):
    result = {"name": "", "linkedin_url": ""}

    for title in TITLES:
        url = _google_find_linkedin(company, title)
        time.sleep(random.uniform(3, 6))  # respect Google rate limits

        if not url:
            continue

        result["linkedin_url"] = url

        # Try to get name via linkedin-api
        match = re.search(r"linkedin\.com/in/([\w\-]+)", url)
        if match:
            name = _get_name_from_api(match.group(1))
            if name:
                result["name"] = name
                time.sleep(random.uniform(3, 6))
                return result

        # URL found but no name — still useful, return it
        return result

    return result


def enrich_prospects(prospects):
    if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
        print("LinkedIn credentials not set — skipping enrichment.")
        return prospects

    print(f"Enriching {len(prospects)} prospects with LinkedIn data...")
    for i, p in enumerate(prospects):
        company = p.get("company", "")
        print(f"  [{i+1}/{len(prospects)}] {company}")
        dm = find_decision_maker(company)
        p["decision_maker_name"] = dm["name"]
        p["decision_maker_linkedin"] = dm["linkedin_url"]
        status = f"{dm['name']} — {dm['linkedin_url']}" if dm["name"] or dm["linkedin_url"] else "not found"
        print(f"    {status}")

    return prospects
