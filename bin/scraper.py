import os
import urllib.request
import urllib.parse
import json
from dotenv import load_dotenv

load_dotenv()

APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL")


# Parses a comma separated string from the sheet into a set.
# Returns an empty set if the cell is blank.
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
    }


# Fetches all user rows from the Google Sheet.
# Returns a dict with { email: filters }
def fetchAllUsers():
    try:
        params = urllib.parse.urlencode({"action": "getAll"})
        url = f"{APPS_SCRIPT_URL}?{params}"
        with urllib.request.urlopen(url, timeout=10) as res:
            data = json.loads(res.read().decode())

        rows = data.get("rows", [])

        if not rows:
            print("No users found in sheet.")
            return {}

        users = {}
        for row in rows:
            email = row[0].strip()
            if email:
                users[email] = rowToFilters(row)
                print(f"Loaded filters for {email}")

        print(f"Total users loaded: {len(users)}")
        return users

    except Exception as e:
        print(f"Failed to fetch users from sheet: {e}")
        return {}


# All users and their filters, keyed by email.
USERS = fetchAllUsers()