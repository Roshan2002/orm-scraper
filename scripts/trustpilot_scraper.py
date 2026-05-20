import json
import time
import random
from bs4 import BeautifulSoup

try:
    import cloudscraper
    _session = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
except ImportError:
    import requests as _req_fallback
    _session = _req_fallback.Session()

MIN_RATING = 2.0
MAX_RATING = 3.9
MIN_REVIEWS = 50
MAX_REVIEWS = 2000
MAX_PROSPECTS = 30

# Trustpilot category slugs — no API key needed
CATEGORIES = [
    "ecommerce_shopping",
    "software_company",
    "health_medical",
    "travel_vacations",
    "business_services",
    "electronics_technology",
    "money_insurance",
    "beauty_wellbeing",
    "home_garden",
    "food_beverages",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _extract_next_data(html):
    """Pull the __NEXT_DATA__ JSON blob Trustpilot embeds in every page."""
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if not tag:
        return None
    try:
        return json.loads(tag.string)
    except Exception:
        return None


def _get_category_companies(category_slug, page=1):
    url = (
        f"https://www.trustpilot.com/categories/{category_slug}"
        f"?numberofreviews=0&status=all&page={page}"
    )
    try:
        resp = _session.get(url, headers=HEADERS, timeout=20)
        print(f"    HTTP {resp.status_code} for {category_slug} p{page}")
        if resp.status_code != 200:
            return []
        data = _extract_next_data(resp.text)
        if not data:
            print(f"    No __NEXT_DATA__ found for {category_slug}")
            return []
        # Try every known path Trustpilot has used
        props = data.get("props", {}).get("pageProps", {})
        businesses = (
            props.get("businessUnits")
            or props.get("businesses")
            or props.get("categoryBusinessList", {}).get("businessUnits", [])
            or props.get("categoryPage", {}).get("businessUnits", [])
            or []
        )
        print(f"    Raw businesses returned: {len(businesses)}")
        return businesses
    except Exception as e:
        print(f"    Error fetching {category_slug}: {e}")
        return []


def _parse_company(biz):
    try:
        name = (biz.get("displayName") or biz.get("name", "")).strip()
        score = biz.get("score") or biz.get("trustScore") or {}
        if isinstance(score, dict):
            rating = float(score.get("trustScore") or score.get("stars") or 0)
        else:
            rating = float(score)
        reviews = biz.get("numberOfReviews") or biz.get("reviewsCount") or {}
        if isinstance(reviews, dict):
            count = int(reviews.get("total") or reviews.get("usersCount") or 0)
        else:
            count = int(reviews)
        website = biz.get("websiteUrl") or biz.get("website") or ""
        return name, rating, count, website
    except Exception:
        return None, 0, 0, ""


def scrape_trustpilot(existing: set) -> list:
    prospects = []
    print(f"Trustpilot scraper started (no API key). Target: {MAX_PROSPECTS} prospects.")

    for category in CATEGORIES:
        if len(prospects) >= MAX_PROSPECTS:
            break
        for page in range(1, 4):  # up to 3 pages per category = ~300 companies
            if len(prospects) >= MAX_PROSPECTS:
                break
            print(f"  Category: {category} page {page}")
            businesses = _get_category_companies(category, page)
            if not businesses:
                break

            for biz in businesses:
                name, rating, count, website = _parse_company(biz)
                if not name or name in existing:
                    continue
                if not (MIN_RATING <= rating <= MAX_RATING):
                    continue
                if not (MIN_REVIEWS <= count <= MAX_REVIEWS):
                    continue

                prospects.append({
                    "company": name,
                    "website": website,
                    "rating": rating,
                    "platform": "Trustpilot",
                    "review_count": count,
                    "decision_maker_name": "",
                    "decision_maker_linkedin": "",
                    "email": "",
                    "pain_point": f"{rating}★ on Trustpilot ({count} reviews) — needs reputation help",
                    "status": "Not contacted",
                })
                existing.add(name)
                print(f"    + {name} ({rating}★, {count} reviews)")

                if len(prospects) >= MAX_PROSPECTS:
                    break

            time.sleep(random.uniform(1.5, 3.0))

    print(f"Trustpilot: found {len(prospects)} qualified prospects.")
    return prospects
