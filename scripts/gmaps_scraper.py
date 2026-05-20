"""
Google Maps ORM Prospect Scraper
Based on: github.com/HasData/google-maps-scraper (playwright_scraper.py)

Searches Google Maps for businesses with low ratings (2.0-3.9 stars)
across target industries and pushes results to Google Sheets.
"""

from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
import time
import random
import re
import json
import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# ---------- Config ----------
SHEET_ID = "1gqiRjuyaxVuas6dKFseGhbp0wSkY_WLC8KPIEeB9-aY"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
MIN_RATING = 2.0
MAX_RATING = 3.9
MIN_REVIEWS = 50
MAX_REVIEWS = 2000
MAX_PROSPECTS = 30
SCROLL_PAUSE = 2.5
MAX_SCROLLS = 15

# Search queries — city + industry combos that surface weak-reputation businesses
SEARCH_QUERIES = [
    "ecommerce store",
    "online software company",
    "digital marketing agency",
    "accounting firm",
    "insurance company",
    "recruitment agency",
    "web hosting company",
    "fintech company",
    "health supplement company",
    "online furniture store",
    "electronics retailer",
    "beauty salon",
    "real estate agency",
    "travel agency",
    "moving company",
]

# ---------- Google Sheets ----------

def get_sheet():
    raw = os.environ.get("GOOGLE_CREDENTIALS")
    if not raw:
        cfg = json.load(open(os.path.join(os.path.dirname(__file__), "../.env.json")))
        raw = cfg["GOOGLE_CREDENTIALS"]
    creds = Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    return gspread.authorize(creds).open_by_key(SHEET_ID).sheet1


def get_existing(sheet):
    try:
        return set(sheet.col_values(1)[1:])
    except Exception:
        return set()


def push_to_sheet(sheet, prospects):
    if not prospects:
        print("No new prospects to push.")
        return
    rows = [
        [
            p["company"], p["website"], str(p["rating"]), p["platform"],
            str(p["review_count"]), p.get("decision_maker_name", ""),
            p.get("decision_maker_linkedin", ""), p.get("email", ""),
            p["pain_point"], p["status"],
        ]
        for p in prospects
    ]
    sheet.append_rows(rows, value_input_option="RAW")
    print(f"Pushed {len(rows)} prospects to sheet.")


# ---------- Scraper ----------

def scrape_query(page, query, existing, prospects):
    print(f"\nSearching: '{query}'")

    page.goto("https://www.google.com/maps")
    time.sleep(random.uniform(3, 5))

    search = page.locator("#searchboxinput")
    search.fill(query)
    search.press("Enter")
    time.sleep(random.uniform(4, 6))

    # Scroll results feed to load more
    try:
        feed = page.locator('div[role="feed"]')
        for _ in range(MAX_SCROLLS):
            if len(prospects) >= MAX_PROSPECTS:
                break
            page.evaluate('(el) => el.scrollTop += el.offsetHeight', feed.element_handle())
            time.sleep(SCROLL_PAUSE)
    except Exception:
        pass

    # Parse cards
    cards = page.locator("div.Nv2PK")
    count = cards.count()
    print(f"  Found {count} cards")

    for i in range(count):
        if len(prospects) >= MAX_PROSPECTS:
            break
        try:
            card = cards.nth(i)

            # Name
            name_el = card.locator(".qBF1Pd")
            name = name_el.nth(0).inner_text().strip() if name_el.count() > 0 else ""
            if not name or name in existing:
                continue

            # Rating
            rating_el = card.locator('span[aria-label*="stars"]')
            rating = 0.0
            if rating_el.count() > 0:
                aria = rating_el.nth(0).get_attribute("aria-label") or ""
                m = re.search(r"([\d.]+)", aria)
                if m:
                    rating = float(m.group(1))

            if not (MIN_RATING <= rating <= MAX_RATING):
                continue

            # Review count
            reviews_el = card.locator(".UY7F9")
            review_count = 0
            if reviews_el.count() > 0:
                txt = reviews_el.nth(0).inner_text()
                m = re.search(r"([\d,]+)", txt)
                if m:
                    review_count = int(m.group(1).replace(",", ""))

            if not (MIN_REVIEWS <= review_count <= MAX_REVIEWS):
                continue

            # Website — click into detail to get it
            website = ""
            phone = ""
            try:
                link_el = card.locator("a.hfpxzc")
                if link_el.count() > 0:
                    with page.expect_navigation(wait_until="domcontentloaded", timeout=8000):
                        link_el.nth(0).click()
                    time.sleep(random.uniform(2, 3))

                    # Website button
                    web_btn = page.locator('a[data-item-id="authority"]')
                    if web_btn.count() > 0:
                        website = web_btn.nth(0).get_attribute("href") or ""

                    # Phone
                    phone_el = page.locator('button[data-item-id*="phone"] .Io6YTe')
                    if phone_el.count() > 0:
                        phone = phone_el.nth(0).inner_text().strip()

                    page.go_back()
                    time.sleep(random.uniform(2, 3))
            except Exception:
                pass

            prospects.append({
                "company": name,
                "website": website,
                "rating": rating,
                "platform": "Google Maps",
                "review_count": review_count,
                "email": "",
                "decision_maker_name": "",
                "decision_maker_linkedin": "",
                "pain_point": f"{rating}★ on Google Maps ({review_count} reviews) — needs reputation help",
                "status": "Not contacted",
            })
            existing.add(name)
            print(f"  + {name} ({rating}★, {review_count} reviews) {website}")

        except Exception as e:
            continue

    time.sleep(random.uniform(2, 4))


def run():
    print(f"Google Maps ORM Scraper — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    sheet = get_sheet()
    existing = get_existing(sheet)
    print(f"Existing prospects in sheet: {len(existing)}")

    prospects = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        stealth_sync(page)

        for query in SEARCH_QUERIES:
            if len(prospects) >= MAX_PROSPECTS:
                break
            scrape_query(page, query, existing, prospects)

        browser.close()

    print(f"\nTotal qualified prospects found: {len(prospects)}")
    push_to_sheet(sheet, prospects)
    print("Done.")


if __name__ == "__main__":
    run()
