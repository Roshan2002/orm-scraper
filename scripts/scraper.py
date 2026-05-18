import requests
import gspread
from google.oauth2.service_account import Credentials
import json
import os
import time
from datetime import datetime

SHEET_ID = "1gqiRjuyaxVuas6dKFseGhbp0wSkY_WLC8KPIEeB9-aY"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
APIFY_BASE = "https://api.apify.com/v2"

MIN_RATING = 2.0
MAX_RATING = 3.9
MIN_REVIEWS = 50
MAX_REVIEWS = 2000

TRUSTPILOT_CATEGORIES = [
    "software_company",
    "ecommerce",
    "money_insurance",
    "health_medical",
]

G2_CATEGORIES = [
    "crm",
    "ecommerce-platforms",
    "accounting",
    "project-management",
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


def run_apify_actor(actor_id, input_data):
    """Run an Apify actor and wait for results."""
    # Start the run
    resp = requests.post(
        f"{APIFY_BASE}/acts/{actor_id}/runs",
        headers={"Authorization": f"Bearer {APIFY_TOKEN}"},
        json=input_data,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        print(f"Failed to start actor {actor_id}: {resp.text[:200]}")
        return []

    run_id = resp.json()["data"]["id"]
    print(f"  Actor started, run ID: {run_id}")

    # Wait for completion (max 3 minutes)
    for _ in range(36):
        time.sleep(5)
        status_resp = requests.get(
            f"{APIFY_BASE}/actor-runs/{run_id}",
            headers={"Authorization": f"Bearer {APIFY_TOKEN}"},
            timeout=15,
        )
        status = status_resp.json()["data"]["status"]
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            print(f"  Run status: {status}")
            break

    if status != "SUCCEEDED":
        return []

    # Get results
    dataset_id = status_resp.json()["data"]["defaultDatasetId"]
    results_resp = requests.get(
        f"{APIFY_BASE}/datasets/{dataset_id}/items?limit=100",
        headers={"Authorization": f"Bearer {APIFY_TOKEN}"},
        timeout=30,
    )
    return results_resp.json()


def scrape_trustpilot(existing):
    prospects = []

    for category in TRUSTPILOT_CATEGORIES:
        print(f"Scraping Trustpilot: {category}...")
        items = run_apify_actor(
            "maxcopell~trustpilot-scraper",
            {
                "startUrls": [
                    {
                        "url": f"https://www.trustpilot.com/categories/{category}?sort=latest&ratingFilter=poor&ratingFilter=bad"
                    }
                ],
                "maxItems": 20,
            },
        )

        for item in items:
            try:
                name = item.get("name", "").strip()
                rating = float(item.get("score", item.get("rating", 0)))
                count = int(item.get("numberOfReviews", item.get("reviewCount", 0)))
                website = item.get("website", item.get("url", ""))

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
                    "platform": f"Trustpilot",
                    "review_count": count,
                    "pain_point": f"{rating}★ on Trustpilot — needs reputation help",
                    "status": "Not contacted",
                })
                existing.add(name)

            except Exception as e:
                continue

        print(f"  Found: {len([p for p in prospects if 'Trustpilot' in p['platform']])}")
        time.sleep(2)

    return prospects


def scrape_g2(existing):
    prospects = []

    for category in G2_CATEGORIES:
        print(f"Scraping G2: {category}...")
        items = run_apify_actor(
            "curious_coder~g2-scraper",
            {
                "categoryUrl": f"https://www.g2.com/categories/{category}?order=lowest_g2_score",
                "maxItems": 20,
            },
        )

        for item in items:
            try:
                name = item.get("name", item.get("productName", "")).strip()
                rating = float(item.get("rating", item.get("starRating", 0)))
                count = int(item.get("reviewCount", item.get("numberOfReviews", 100)))
                website = item.get("website", item.get("url", ""))

                if not name or name in existing:
                    continue
                if not (MIN_RATING <= rating <= MAX_RATING):
                    continue

                prospects.append({
                    "company": name,
                    "website": website,
                    "rating": rating,
                    "platform": "G2",
                    "review_count": count,
                    "pain_point": f"{rating}★ on G2 — needs reputation help",
                    "status": "Not contacted",
                })
                existing.add(name)

            except Exception:
                continue

        print(f"  Found: {len([p for p in prospects if p['platform'] == 'G2'])}")
        time.sleep(2)

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
            "",  # Decision maker name
            "",  # Decision maker LinkedIn
            "",  # Decision maker email
            p["pain_point"],
            p["status"],
        ]
        for p in prospects
    ]

    sheet.append_rows(rows, value_input_option="RAW")
    print(f"Added {len(rows)} new prospects to sheet.")


def main():
    print(f"ORM Scraper started — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    if not APIFY_TOKEN:
        print("ERROR: APIFY_TOKEN secret not set.")
        return

    sheet = get_sheet()
    existing = get_existing_companies(sheet)
    print(f"Existing prospects in sheet: {len(existing)}")

    all_prospects = []
    all_prospects.extend(scrape_trustpilot(existing))
    all_prospects.extend(scrape_g2(existing))

    push_to_sheet(sheet, all_prospects)
    print(f"Done. Total new prospects today: {len(all_prospects)}")


if __name__ == "__main__":
    main()
