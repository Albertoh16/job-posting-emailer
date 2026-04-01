import ssl
import certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

import os
import urllib.request
import urllib.parse
import json
from dotenv import load_dotenv

load_dotenv()

APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL")

# This makes a set based off of the items listed by the user in the spreadsheet.
def parseCell(value):
    if not value or not value.strip():
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}

# Converts a sheet row into a filters dict matching the scraper's expected format.
def rowToFilters(row):
    return {
        "position":               parseCell(row[1]),
        "exclude position":       parseCell(row[2]),
        "role":                   parseCell(row[3]),
        "exclude role":           parseCell(row[4]),
        "specialization":         parseCell(row[5]),
        "exclude specialization": parseCell(row[6]),
        "qualification":          parseCell(row[7]),
        "exclude qualification":  parseCell(row[8]),
        "industry":               parseCell(row[9]),
        "exclude industry":       parseCell(row[10]),
        "intervals":              parseCell(row[11]),
    }

# Fetches all user rows from the Google Sheet.
def fetchAllUsers():
    try:
        params = urllib.parse.urlencode({"action": "getAll"})
        url = f"{APPS_SCRIPT_URL}?{params}"

        with urllib.request.urlopen(url, timeout=50) as res:
            data = json.loads(res.read().decode())

        rows = data.get("rows", [])

        # If no rows were found, then there are no users.
        if not rows:
            print(f"[config] No users found in sheet.")
            return {}

        users = {}
        for row in rows:
            email = row[0].strip()
            if email:
                users[email] = rowToFilters(row)
                print(f"[config] Loaded filters for {email}")

        print(f"[config] Total users loaded: {len(users)}")
        return users

    except Exception as e:
        print(f"Failed to fetch users from sheet: {e}")
        print("Falling back to empty users.")
        return {}

# All users and their filters, keyed by email.
USERS = fetchAllUsers()
