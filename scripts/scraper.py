import requests
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials
import json
import os
import time
import random
from datetime import datetime

SHEET_ID = "1gqiRjuyaxVuas6dKFseGhbp0wSkY_WLC8KPIEeB9-aY"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADERS_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/118.0.0.0 Safari/537.36",
]

CATEGORIES = [
    ("software_company", "Software"),
    ("ecommerce", "E-commerce"),
    ("money_insurance", "Fintech"),
    ("health_medical", "Healthcare"),
    ("travel_holidays_tours", "Travel"),
]

MIN_RATING = 2.0
MAX_RATING = 3.9
MIN_REVIEWS = 50
MAX_REVIEWS = 2000
MAX_PER_CATEGORY = 15


def get_sheet():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).sheet1
    return sheet


def get_existing_companies(sheet):
    try:
        records = sheet.col_values(1)[1:]
        return set(records)
    except:
        return set()


def scrape_trustpilot_category(category_id, category_name, existing):
    results = []
    url = f"https://www.trustpilot.com/categories/{category_id}?sort=latest&ratingFilter=poor&ratingFilter=bad"

    try:
        headers = {"User-Agent": random.choice(HEADERS_LIST)}
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        cards = soup.select("div[class*='businessUnitResult']")
        if not cards:
            cards = soup.select("div[class*='styles_businessUnitResult']")

        for card in cards[:MAX_PER_CATEGORY]:
            try:
                name_el = card.select_one("p[class*='title']") or card.select_one("span[class*='title']")
                rating_el = card.select_one("span[class*='ratingText']") or card.select_one("p[class*='ratingText']")
                count_el = card.select_one("span[class*='reviewsCount']") or card.select_one("p[class*='reviewsCount']")
                link_el = card.select_one("a[href*='/review/']")

                if not name_el or not rating_el:
                    continue

                name = name_el.get_text(strip=True)
                rating_text = rating_el.get_text(strip=True).replace(",", ".")
                rating = float(''.join(c for c in rating_text if c.isdigit() or c == '.'))
                count_text = count_el.get_text(strip=True).replace(",", "").replace(".", "") if count_el else "0"
                count = int(''.join(c for c in count_text if c.isdigit()) or 0)

                if not (MIN_RATING <= rating <= MAX_RATING):
                    continue
                if not (MIN_REVIEWS <= count <= MAX_REVIEWS):
                    continue
                if name in existing:
                    continue

                website = ""
                if link_el:
                    slug = link_el["href"].replace("/review/", "")
                    website = f"https://www.{slug}"

                results.append({
                    "company": name,
                    "website": website,
                    "rating": rating,
                    "platform": f"Trustpilot ({category_name})",
                    "review_count": count,
                    "pain_point": f"{rating}★ on Trustpilot — reputation issue",
                    "status": "Not contacted"
                })

                existing.add(name)
                time.sleep(random.uniform(0.5, 1.5))

            except Exception:
                continue

    except Exception as e:
        print(f"Error scraping {category_name}: {e}")

    return results


def scrape_g2_category(category_slug, category_name, existing):
    results = []
    url = f"https://www.g2.com/categories/{category_slug}?order=lowest_g2_score"

    try:
        headers = {"User-Agent": random.choice(HEADERS_LIST)}
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        cards = soup.select("div.product-listing")
        if not cards:
            cards = soup.select("li[class*='product-listing']")

        for card in cards[:MAX_PER_CATEGORY]:
            try:
                name_el = card.select_one("div.product-listing__product-name") or card.select_one("a[class*='product-name']")
                rating_el = card.select_one("span[class*='fw-semibold']") or card.select_one("span[class*='rating']")
                count_el = card.select_one("span[class*='ratings-count']")

                if not name_el:
                    continue

                name = name_el.get_text(strip=True)
                rating = 3.0
                if rating_el:
                    try:
                        rating = float(rating_el.get_text(strip=True).split()[0])
                    except:
                        pass

                count = 100
                if count_el:
                    try:
                        count = int(''.join(c for c in count_el.get_text() if c.isdigit()) or 100)
                    except:
                        pass

                if not (MIN_RATING <= rating <= MAX_RATING):
                    continue
                if name in existing:
                    continue

                results.append({
                    "company": name,
                    "website": "",
                    "rating": rating,
                    "platform": f"G2 ({category_name})",
                    "review_count": count,
                    "pain_point": f"{rating}★ on G2 — reputation issue",
                    "status": "Not contacted"
                })

                existing.add(name)
                time.sleep(random.uniform(0.5, 1.5))

            except Exception:
                continue

    except Exception as e:
        print(f"Error scraping G2 {category_name}: {e}")

    return results


def push_to_sheet(sheet, prospects):
    if not prospects:
        print("No new prospects found today.")
        return

    rows = []
    for p in prospects:
        rows.append([
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
        ])

    sheet.append_rows(rows, value_input_option="RAW")
    print(f"Added {len(rows)} new prospects to sheet.")


def main():
    print(f"Starting ORM scraper — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    sheet = get_sheet()
    existing = get_existing_companies(sheet)
    print(f"Existing prospects: {len(existing)}")

    all_prospects = []

    for cat_id, cat_name in CATEGORIES:
        print(f"Scraping Trustpilot: {cat_name}...")
        results = scrape_trustpilot_category(cat_id, cat_name, existing)
        all_prospects.extend(results)
        print(f"  Found: {len(results)}")
        time.sleep(2)

    g2_categories = [
        ("crm", "CRM"),
        ("ecommerce-platforms", "E-commerce"),
        ("accounting", "Accounting"),
    ]

    for cat_slug, cat_name in g2_categories:
        print(f"Scraping G2: {cat_name}...")
        results = scrape_g2_category(cat_slug, cat_name, existing)
        all_prospects.extend(results)
        print(f"  Found: {len(results)}")
        time.sleep(2)

    push_to_sheet(sheet, all_prospects)
    print(f"Done. Total new prospects today: {len(all_prospects)}")


if __name__ == "__main__":
    main()
