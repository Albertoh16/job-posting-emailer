import ssl
import certifi

# This overrides the default SSL python has to the one provided by certifi
# to prevent issues that might come from being run on a different OS.
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
    if not value or not str(value).strip():
        return set()
    
    return {item.strip() for item in str(value).split(",") if item.strip()}

# Google Sheets stores time-only cells as fractional floats or Date objects.
def parseIntervals(value):
    if not value and value != 0:
        return set()
    
    # Sheets time-only cells arrive as a float fraction of a day.
    if isinstance(value, float) and 0 < value < 1:
        hour = round(value * 24)
        return {f"{hour:02d}:00"}
    
    result = set()

    for item in str(value).split(","):
        item = item.strip()

        if not item:
            continue
        
        if len(item) == 5 and item[2] == ":":
            result.add(item)

        # Serialized date/datetime from Sheets
        elif "T" in item or "1899" in item or "1900" in item:
            try:
                from datetime import datetime as dt
                parsed = dt.fromisoformat(item.replace("Z", "+00:00"))
                result.add(f"{parsed.hour:02d}:00")

            except Exception:
                result.add(item)

        else:
            result.add(item)

    return result

# Parses days string into a set of day names.
def parseDays(value):
    if not value or not str(value).strip():
        return set()
    
    return {item.strip() for item in str(value).split(",") if item.strip()}

# Parses the work-model field.
def parseWorkModel(value):
    if not value or not str(value).strip():
        return set()
    
    valid = {"remote", "hybrid", "on-site"}
    result = set()

    for item in str(value).split(","):
        item = item.strip().lower()

        if item in valid:
            result.add(item.title().replace("On-Site", "On-site"))

    return result

# Parses the job titles field.
def parseJobTitles(value):
    if not value or not str(value).strip():
        return set()
    
    return {item.strip() for item in str(value).split(",") if item.strip()}

# Parses the hierarchy field (e.g. "intern, new grad, senior").
def parseHierarchy(value):
    if not value or not str(value).strip():
        return set()

    valid = {"intern", "co-op", "new grad", "junior", "senior"}
    result = set()

    for item in str(value).split(","):
        item = item.strip().lower()
        if item in valid:
            result.add(item)

    return result

# Converts the sheet row into a filters map matching the scraper's expected format.
# Sheet column order:
# [0] Email | [1] Hierarchy | [2] Specialization | [3] Qualification
# [4] Industry | [5] Intervals | [6] Days | [7] Work Model | [8] Job Title
def rowToFilters(row):
    return {
        "hierarchy":      parseHierarchy(row[1]),
        "specialization": parseCell(row[2]),
        "qualification":  parseCell(row[3]),
        "industry":       parseCell(row[4]),
        "intervals":      parseIntervals(row[5]),
        "days":           parseDays(row[6]),
        "work-model":     parseWorkModel(row[7]) if len(row) > 7 else set(),
        "job-title":      parseJobTitles(row[8]) if len(row) > 8 else set(),
    }

# Fetches all user rows from the Google Sheet.
def fetchAllUsers():
    try:
        params = urllib.parse.urlencode({"action": "getAll"})
        url = f"{APPS_SCRIPT_URL}?{params}"

        with urllib.request.urlopen(url, timeout=10) as res:
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
                print(f"[config DEBUG] {email} intervals raw={row[9]!r} type={type(row[9]).__name__} parsed={users[email]['intervals']!r}")
        print(f"[config] Total users loaded: {len(users)}")

        return users

    except Exception as e:
        print(f"Failed to fetch users from sheet: {e}")
        print("Falling back to empty users.")
        
        return {}

# All users and their filters, keyed by their emails.
USERS = fetchAllUsers()