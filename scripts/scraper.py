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

SEARCH_QUERIES = [
    "software company",
    "ecommerce store",
    "fintech",
    "healthcare software",
    "saas platform",
    "online marketplace",
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


def run_actor_and_wait(actor_id, input_data, wait=40):
    resp = requests.post(
        f"{APIFY_BASE}/acts/{actor_id}/runs",
        headers={"Authorization": f"Bearer {APIFY_TOKEN}"},
        json=input_data,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        print(f"  Failed to start {actor_id}: {resp.text[:150]}")
        return []

    run_id = resp.json()["data"]["id"]
    print(f"  Run started: {run_id}")

    for _ in range(24):
        time.sleep(5)
        status_resp = requests.get(
            f"{APIFY_BASE}/actor-runs/{run_id}",
            headers={"Authorization": f"Bearer {APIFY_TOKEN}"},
            timeout=15,
        )
        status = status_resp.json()["data"]["status"]
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            print(f"  Status: {status}")
            break

    if status != "SUCCEEDED":
        return []

    dataset_id = status_resp.json()["data"]["defaultDatasetId"]
    results = requests.get(
        f"{APIFY_BASE}/datasets/{dataset_id}/items?limit=100",
        headers={"Authorization": f"Bearer {APIFY_TOKEN}"},
        timeout=30,
    )
    return results.json() if isinstance(results.json(), list) else []


def scrape_trustpilot(existing):
    prospects = []

    for query in SEARCH_QUERIES:
        print(f"Searching Trustpilot: '{query}'...")
        items = run_actor_and_wait(
            "burbn~trustpilot-search-scraper",
            {"query": query, "maxItems": 100},
        )

        for item in items:
            try:
                name = item.get("name", "").strip()
                rating = float(item.get("trustScore", item.get("rating", 0)))
                count = int(item.get("reviewCount", 0))
                website = item.get("website", item.get("domain", ""))
                country = item.get("country", "")

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
                    "pain_point": f"{rating}★ on Trustpilot ({count} reviews) — needs reputation help",
                    "status": "Not contacted",
                })
                existing.add(name)

            except Exception:
                continue

        print(f"  Qualified prospects so far: {len(prospects)}")
        time.sleep(3)

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
        print("ERROR: APIFY_TOKEN not set.")
        return

    sheet = get_sheet()
    existing = get_existing_companies(sheet)
    print(f"Existing prospects: {len(existing)}")

    prospects = scrape_trustpilot(existing)
    push_to_sheet(sheet, prospects)
    print(f"Done. Total new prospects today: {len(prospects)}")


if __name__ == "__main__":
    main()
