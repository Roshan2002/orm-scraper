import requests
import gspread
from google.oauth2.service_account import Credentials
import json
import os
import time
from datetime import datetime
from linkedin_enricher import enrich_prospects

SHEET_ID = "1gqiRjuyaxVuas6dKFseGhbp0wSkY_WLC8KPIEeB9-aY"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TP_API_KEY = os.environ.get("TRUSTPILOT_API_KEY")
TP_BASE = "https://api.trustpilot.com/v1"

MIN_RATING = 2.0
MAX_RATING = 3.9
MIN_REVIEWS = 50
MAX_REVIEWS = 2000

SEARCH_QUERIES = [
    "software",
    "ecommerce",
    "fintech",
    "saas",
    "healthcare",
    "insurance",
    "hosting",
    "vpn",
    "crypto",
    "travel",
    "recruitment",
    "shipping",
    "furniture",
    "electronics",
    "clothing",
    "beauty",
    "supplements",
    "marketing agency",
    "accounting",
    "crm",
]


def get_sheet():
    creds_dict = json.loads(os.environ.get("GOOGLE_CREDENTIALS"))
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1


def get_existing_companies(sheet):
    try:
        return set(sheet.col_values(1)[1:])
    except:
        return set()


def search_trustpilot(query, page=1):
    """Search Trustpilot business units by query."""
    try:
        resp = requests.get(
            f"{TP_BASE}/business-units/search",
            params={
                "apikey": TP_API_KEY,
                "query": query,
                "perPage": 20,
                "page": page,
                "country": "US,GB,AU,CA",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json().get("businesses", [])
        else:
            print(f"  API error {resp.status_code}: {resp.text[:100]}")
            return []
    except Exception as e:
        print(f"  Request error: {e}")
        return []


def get_business_details(business_id):
    """Get full details for a business unit."""
    try:
        resp = requests.get(
            f"{TP_BASE}/business-units/{business_id}",
            params={"apikey": TP_API_KEY},
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
        return {}
    except:
        return {}


def scrape_trustpilot(existing):
    prospects = []

    for query in SEARCH_QUERIES:
        print(f"Searching: '{query}'...")
        businesses = search_trustpilot(query)

        for biz in businesses:
            try:
                name = biz.get("displayName", biz.get("name", "")).strip()
                rating = float(biz.get("score", {}).get("trustScore", 0))
                count = int(biz.get("numberOfReviews", {}).get("total", 0))
                website = biz.get("websiteUrl", "")
                biz_id = biz.get("id", "")

                if not name or name in existing:
                    continue
                if not (MIN_RATING <= rating <= MAX_RATING):
                    continue
                if not (MIN_REVIEWS <= count <= MAX_REVIEWS):
                    continue

                # Get contact email if available
                email = ""
                if biz_id:
                    details = get_business_details(biz_id)
                    email = details.get("contact", {}).get("email", "")
                    time.sleep(0.3)

                prospects.append({
                    "company": name,
                    "website": website,
                    "rating": rating,
                    "platform": "Trustpilot",
                    "review_count": count,
                    "email": email,
                    "decision_maker_name": "",
                    "decision_maker_linkedin": "",
                    "pain_point": f"{rating}★ on Trustpilot ({count} reviews) — needs reputation help",
                    "status": "Not contacted",
                })
                existing.add(name)

            except Exception:
                continue

        print(f"  Qualified so far: {len(prospects)}")
        time.sleep(0.5)

        if len(prospects) >= 30:
            break

    return prospects


def push_to_sheet(sheet, prospects):
    if not prospects:
        print("No new prospects found today.")
        return

    rows = [
        [
            p["company"],
            p["website"],
            str(p["rating"]),
            p["platform"],
            str(p["review_count"]),
            p.get("decision_maker_name", ""),
            p.get("decision_maker_linkedin", ""),
            p["email"],
            p["pain_point"],
            p["status"],
        ]
        for p in prospects
    ]

    sheet.append_rows(rows, value_input_option="RAW")
    print(f"Added {len(rows)} new prospects to sheet.")


def main():
    print(f"ORM Scraper started — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    if not TP_API_KEY:
        print("ERROR: TRUSTPILOT_API_KEY not set.")
        return

    sheet = get_sheet()
    existing = get_existing_companies(sheet)
    print(f"Existing prospects: {len(existing)}")

    prospects = scrape_trustpilot(existing)
    prospects = enrich_prospects(prospects)
    push_to_sheet(sheet, prospects)
    print(f"Done. Total new prospects today: {len(prospects)}")


if __name__ == "__main__":
    main()
