import gspread
from google.oauth2.service_account import Credentials
import json
import os
from datetime import datetime

from trustpilot_scraper import scrape_trustpilot
from linkedin_enricher import enrich_prospects

SHEET_ID = "1gqiRjuyaxVuas6dKFseGhbp0wSkY_WLC8KPIEeB9-aY"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_sheet():
    creds_dict = json.loads(os.environ.get("GOOGLE_CREDENTIALS"))
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1


def get_existing_companies(sheet):
    try:
        return set(sheet.col_values(1)[1:])
    except Exception:
        return set()


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
            p.get("email", ""),
            p["pain_point"],
            p["status"],
        ]
        for p in prospects
    ]
    sheet.append_rows(rows, value_input_option="RAW")
    print(f"Added {len(rows)} new prospects to sheet.")


def main():
    print(f"ORM Scraper started — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    sheet = get_sheet()
    existing = get_existing_companies(sheet)
    print(f"Existing prospects in sheet: {len(existing)}")

    prospects = scrape_trustpilot(existing)
    prospects = enrich_prospects(prospects)
    push_to_sheet(sheet, prospects)
    print(f"Done. New prospects added: {len(prospects)}")


if __name__ == "__main__":
    main()
