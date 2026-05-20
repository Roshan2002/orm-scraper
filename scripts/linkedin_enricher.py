import os
import time
import random
import requests
from bs4 import BeautifulSoup
from linkedin_api import Linkedin

LINKEDIN_EMAIL = os.environ.get("LINKEDIN_EMAIL")
LINKEDIN_PASSWORD = os.environ.get("LINKEDIN_PASSWORD")

DECISION_MAKER_TITLES = [
    "CEO", "Founder", "Co-Founder", "Owner", "Managing Director",
    "CMO", "Head of Marketing", "VP Marketing", "Director of Marketing",
    "Head of Growth", "VP Growth",
]

_linkedin_client = None


def _get_client():
    global _linkedin_client
    if _linkedin_client is None:
        if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
            raise EnvironmentError("LINKEDIN_EMAIL and LINKEDIN_PASSWORD secrets not set.")
        _linkedin_client = Linkedin(LINKEDIN_EMAIL, LINKEDIN_PASSWORD)
    return _linkedin_client


def _google_search_linkedin(company_name, title):
    """Search Google for a LinkedIn profile matching company + title."""
    query = f'site:linkedin.com/in "{title}" "{company_name}"'
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(
            "https://www.google.com/search",
            params={"q": query, "num": 5},
            headers=headers,
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "linkedin.com/in/" in href:
                # Extract clean URL from Google redirect
                if href.startswith("/url?q="):
                    href = href.split("/url?q=")[1].split("&")[0]
                if "linkedin.com/in/" in href:
                    return href.split("?")[0].rstrip("/")
    except Exception:
        pass
    return None


def _extract_public_id(linkedin_url):
    """Get the public profile ID from a LinkedIn URL."""
    try:
        return linkedin_url.rstrip("/").split("/in/")[1].split("/")[0]
    except Exception:
        return None


def find_decision_maker(company_name):
    """
    Returns dict with keys: name, linkedin_url
    Tries each decision-maker title until one is found.
    """
    result = {"name": "", "linkedin_url": ""}

    for title in DECISION_MAKER_TITLES:
        url = _google_search_linkedin(company_name, title)
        # Respect Google rate limits
        time.sleep(random.uniform(3, 6))

        if not url:
            continue

        public_id = _extract_public_id(url)
        if not public_id:
            continue

        # Try to get the full name from LinkedIn API
        try:
            client = _get_client()
            profile = client.get_profile(public_id)
            first = profile.get("firstName", "")
            last = profile.get("lastName", "")
            name = f"{first} {last}".strip()
            if name:
                result["name"] = name
                result["linkedin_url"] = url
                # Slow down to avoid LinkedIn flagging the account
                time.sleep(random.uniform(4, 8))
                return result
        except Exception:
            # If API fails, still return the URL with name from Google snippet
            result["linkedin_url"] = url
            time.sleep(random.uniform(2, 4))
            continue

    return result


def enrich_prospects(prospects):
    """
    Takes a list of prospect dicts and fills in decision_maker_name
    and decision_maker_linkedin for each.
    """
    if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
        print("LinkedIn credentials not set — skipping enrichment.")
        return prospects

    print(f"Enriching {len(prospects)} prospects with LinkedIn data...")
    for i, p in enumerate(prospects):
        company = p.get("company", "")
        print(f"  [{i+1}/{len(prospects)}] Finding decision maker for: {company}")
        dm = find_decision_maker(company)
        p["decision_maker_name"] = dm["name"]
        p["decision_maker_linkedin"] = dm["linkedin_url"]
        if dm["name"] or dm["linkedin_url"]:
            print(f"    Found: {dm['name']} — {dm['linkedin_url']}")
        else:
            print(f"    Not found.")

    return prospects
