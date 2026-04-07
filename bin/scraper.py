from playwright.sync_api import sync_playwright
from config import USERS
from emailer import sendEmail
from filter import FilterJobs
from datetime import datetime, timedelta, timezone
import asyncio

from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")

initialTime = datetime.now(tz=timezone.utc)
currentHour = initialTime.astimezone(ET).strftime("%H:00")
currentDay  = initialTime.astimezone(ET).strftime("%A")

if not USERS:
    print("No users found in sheet, exiting.")
    exit()

# Filters down to only users scheduled for this hour and day.
# Users with no intervals or no days set receive emails every run.
activeUsers = {
    email: filters for email, filters in USERS.items()
    if (not filters.get("intervals") or currentHour in filters.get("intervals", set()))
    and (not filters.get("days") or currentDay in filters.get("days", set()))
}

# If there are no users scheduled for the current day and time, we stop the
# action completely.
if not activeUsers:
    print(f"No users scheduled for {currentDay} {currentHour}, exiting.")
    exit()

print(f"[{currentDay} {currentHour}] {len(activeUsers)} user(s) scheduled: {list(activeUsers.keys())}")

# We take the user's list of times and we'll display times between the user's decided times to get emails.
def getPreviousIntervalTime(intervals: set, currentTime: datetime) -> datetime:
    currentTimeET = currentTime.astimezone(ET)

    cutoff = currentTime - timedelta(hours=24)

    if not intervals or len(intervals) == 1:
        return cutoff

    sortedTimes = sorted(intervals, key=lambda t: int(t.split(":")[0]))
    currentHourStr = currentTimeET.strftime("%H:00")

    if currentHourStr not in sortedTimes:
        return cutoff

    idx = sortedTimes.index(currentHourStr)
    prevHourStr = sortedTimes[idx - 1]
    prevHour = int(prevHourStr.split(":")[0])
    currHour = int(currentHourStr.split(":")[0])

    if prevHour < currHour:
        windowStart = currentTimeET.replace(hour=prevHour, minute=0, second=0, microsecond=0)
    else:
        windowStart = (currentTimeET - timedelta(days=1)).replace(hour=prevHour, minute=0, second=0, microsecond=0)

    windowStart = windowStart.astimezone(timezone.utc)

    return max(windowStart, cutoff)

windowStarts = {
    email: getPreviousIntervalTime(filters.get("intervals", set()), initialTime)
    for email, filters in activeUsers.items()
}

earliestStart = min(windowStarts.values())

print(f"Scraping window: {earliestStart} -> {initialTime}")

# Uses a single browser to run everything.
with sync_playwright() as p:
    print("Launching Chromium...")
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()

    # Scrapes jobs from the listing page.
    scrapePage = context.new_page()

    jobs    = []
    seenIds = set()

    def handleResponse(response):
        if "swan/mini-sites/list" in response.url:
            try:
                data = response.json()
                if "result" in data and "jobList" in data["result"]:
                    for job in data["result"]["jobList"]:
                        jobId = job["jobId"]
                        if jobId not in seenIds:
                            seenIds.add(jobId)
                            jobs.append({
                                "title":          job["properties"]["title"],
                                "company":        job["properties"]["company"],
                                "location":       job["properties"]["location"],
                                "workModel":      job["properties"]["workModel"],
                                "applyUrl":       f"https://jobright.ai/jobs/info/{jobId}",
                                "industry":       job["properties"]["industry"],
                                "qualifications": job["properties"]["qualifications"],
                                "postedDate":     job["postedAt"]
                            })

            except Exception as e:
                print(f"Error: {e}")

    scrapePage.on("response", handleResponse)
    scrapePage.goto("https://jobright.ai/minisites-jobs/intern/us/swe")
    scrapePage.wait_for_load_state("domcontentloaded")

    # Captures initial jobs from table.
    data = scrapePage.evaluate("""() => JSON.parse(document.getElementById('__NEXT_DATA__').textContent)""")

    for job in data["props"]["pageProps"]["initialJobs"]:
        jobId = job["id"]

        if jobId not in seenIds:
            seenIds.add(jobId)
            
            jobs.append({
                "title":          job["title"],
                "company":        job["company"],
                "location":       job["location"],
                "workModel":      job["workModel"],
                "applyUrl":       job["applyUrl"],
                "industry":       job["industry"],
                "qualifications": job["qualifications"],
                "postedDate":     job["postedDate"]
            })

    # Scrolls to load more rows, stopping early if no new jobs appear.
    tableBody = scrapePage.query_selector(".index_bodyViewport__3xQLm")

    # This is the number of consecutive stale jobs required before stopping.
    STALE_STREAK_LIMIT = 5

    for _ in range(50):
        prevCount = len(seenIds)
        tableBody.evaluate("el => el.scrollTop += 3000")
        scrapePage.wait_for_timeout(600)

        if len(seenIds) == prevCount:
            print(f"No new jobs after scroll, stopping at {len(seenIds)} jobs.")
            break

        # Only stop once the last N loaded jobs are all within our window of time.
        recentJobs = sorted(jobs, key=lambda j: j["postedDate"], reverse=True)

        outOfWindow = sum(
            1 for j in recentJobs[:STALE_STREAK_LIMIT]
            if datetime.fromtimestamp(j["postedDate"] / 1000, tz=timezone.utc) < earliestStart
        )

        if outOfWindow >= STALE_STREAK_LIMIT:
            print(f"Last {STALE_STREAK_LIMIT} jobs all outside window, stopping at {len(seenIds)} jobs.")
            break

    scrapePage.close()
    print("Scraping tab closed.")

    allNeededJobs = {}

    for job in jobs:
        if job["company"] not in allNeededJobs:
            allNeededJobs[job["company"]] = []

        allNeededJobs[job["company"]].append((
            job["title"], job["applyUrl"], job["location"],
            job["workModel"], job["industry"], job["postedDate"],
            job["qualifications"]
        ))

    for company in allNeededJobs:
        allNeededJobs[company].sort(key=lambda x: x[5], reverse=True)

    # Fetches real URLs using the logged-in tab.
    print("Building job listings...")
    resolvedJobs = {}

    for company, listings in allNeededJobs.items():
        resolvedJobs[company] = []

        for (title, jobrightURL, location, workModel, industry, postDate, qualifications) in listings:
            resolvedJobs[company].append((title, jobrightURL, location, workModel, industry, postDate, qualifications))

    browser.close()
    print("Browser closed.")

# Filters and emails a single user, runs concurrently with other users.
async def processUser(email, filters, resolvedJobs, initialTime):
    windowStart = windowStarts[email]

    print(f"\n[{email}] Window: {windowStart} → {initialTime}")

    # Trims the resolvedJobs to this user's window.
    userResolvedJobs = {
        company: [
            job for job in listings
            if datetime.fromtimestamp(job[5] / 1000, tz=timezone.utc) >= windowStart
        ]

        for company, listings in resolvedJobs.items()
    }

    userResolvedJobs = {k: v for k, v in userResolvedJobs.items() if v}

    userJobs = await asyncio.to_thread(FilterJobs, filters, userResolvedJobs)
    totalJobs = sum(len(v) for v in userJobs.values())

    print(f"[{email}] Sending {totalJobs} jobs.")

    await asyncio.to_thread(sendEmail, userJobs, initialTime, email)

# Runs all users concurrently.
async def processAllUsers(resolvedJobs, initialTime):
    tasks = [
        processUser(email, filters, resolvedJobs, initialTime)
        for email, filters in activeUsers.items() 
    ]
    await asyncio.gather(*tasks)

asyncio.run(processAllUsers(resolvedJobs, initialTime))