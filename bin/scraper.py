from playwright.sync_api import sync_playwright
from config import FILTERS
from emailer import sendEmail
from datetime import datetime, timedelta

def within24Hours(time):
    posted = datetime.fromtimestamp(time / 1000)
    now = datetime.now()
    return (now - posted) <= timedelta(hours=24)

def validJob(job):
    words = job["title"].split()
    keys = ["position", "role"]

    for key in keys:
        skip = False
        left = 0
        right = len(words)-1

        while left < right:
            if words[left] in FILTERS[key] or words[left] in FILTERS[key]:
                skip = True
                break

            left += 1
            right -= 1

        if skip:
            continue
        
        return False
    
    return True

# Creates an enviornment to utilize a utilize browser capabilities.
with sync_playwright() as p:
    # Opens the browser (in this case chrome/edge).
    browser = p.chromium.launch()

    # Creates a page within the browser.
    page = browser.new_page()

    # We have the page go to a specific address.
    page.goto("https://jobright.ai/minisites-jobs/intern/us/swe")

    # We'll yield our script until we have nothing happening.
    # page.wait_for_load_state("networkidle")

    # Now we parse all the data from the json providing all the job listings from the site.
    data = page.evaluate("""() => JSON.parse(document.getElementById('__NEXT_DATA__').textContent)""")
    
    # We're now populating a list to contain all the jobs in the table.
    jobs = data["props"]["pageProps"]["initialJobs"]

newJobs = {}

for job in jobs:
    print(job["title"]+"\n")

    if validJob(job) and within24Hours(job["postedDate"]):
        print(job["title"])

        if job["company"] not in newJobs:
            newJobs[job["company"]] = []

        newJobs[job["company"]].append((job["title"], job["applyUrl"]))

# sendEmail(newJobs)