import os
import urllib.request
import urllib.parse
import json
from dotenv import load_dotenv

load_dotenv()

APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL")
EMAIL = os.getenv("EMAIL")

# This makes a set based off of the items listed by the user in the spreadsheet.
def parseCell(value):
    if not value or not value.strip():
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}

# This fetched the user's row from the Google Sheet.
def fetchFilters(email):
    try:
        params = urllib.parse.urlencode({"action": "get", "email": email})
        url = f"{APPS_SCRIPT_URL}?{params}"
        with urllib.request.urlopen(url, timeout=10) as res:
            data = json.loads(res.read().decode())

        row = data.get("row")

        # If no row was found for this email, then there are no filters.
        if not row:
            print(f"[config] No row found for {email}, using empty filters.")
            return {}

        return {
            "position": parseCell(row[1]),
            "exclude position": parseCell(row[2]),
            "role": parseCell(row[3]),
            "exclude role": parseCell(row[4]),
            "specialization": parseCell(row[5]),
            "exclude specialization": parseCell(row[6]),
            "qualification": parseCell(row[7]),
            "exclude qualification": parseCell(row[8]),
            "industry": parseCell(row[9]),
            "exclude industry": parseCell(row[10]),
        }

    except Exception as e:
        print(f"Failed to fetch filters from sheet: {e}")
        print("Falling back to empty filters.")
        return {}

FILTERS = fetchFilters(EMAIL)
print(f"Loaded filters for {EMAIL}: {FILTERS}")