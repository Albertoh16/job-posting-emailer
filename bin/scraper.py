from playwright.sync_api import sync_playwright
from config import USERS
from emailer import sendEmail
from linkFetcher import loadSession, isLoggedIn, loginToJobright, getApplicationURL
from datetime import datetime, timedelta, timezone
import asyncio

# We convert the millisecond timestamp to a UTC date and
# time, then we only accept posts from the last 13 hours.
def withinTimeLimit(time):
    posted = datetime.fromtimestamp(time / 1000)
    now = datetime.now()
    return (now - posted) <= timedelta(hours=13)

# We only take in jobs that are applicable to a given user's filters.
def validJob(job, filters):
    if not filters:
        return True

    jobTitle          = job["title"].lower()
    jobIndustry       = ", ".join(job["industry"]).lower()
    jobQualifications = job["qualifications"].lower()

    if filters.get("exclude position"):
        if any(word.lower() in jobTitle for word in filters["exclude position"]):
            return False
    if filters.get("exclude role"):
        if any(word.lower() in jobTitle for word in filters["exclude role"]):
            return False
    if filters.get("exclude specialization"):
        if any(word.lower() in jobTitle for word in filters["exclude specialization"]):
            return False
    if filters.get("exclude qualification"):
        if any(word.lower() in jobQualifications for word in filters["exclude qualification"]):
            return False
    if filters.get("exclude industry"):
        if any(word.lower() in jobIndustry for word in filters["exclude industry"]):
            return False

    hasPosition       = any(word.lower() in jobTitle for word in filters["position"])       if filters["position"]       else True
    hasRole           = any(word.lower() in jobTitle for word in filters["role"])           if filters["role"]           else True
    hasSpecialization = any(word.lower() in jobTitle for word in filters["specialization"]) if filters["specialization"] else True
    hasQualification  = any(word.lower() in jobQualifications for word in filters["qualification"]) if filters["qualification"] else True
    hasIndustry       = any(word.lower() in jobIndustry for word in filters["industry"])    if filters["industry"]       else True

    return hasPosition and hasRole and hasSpecialization and hasQualification and hasIndustry


initialTime = datetime.now(tz=timezone.utc)

if not USERS:
    print("No users found in sheet, exiting.")
    exit()

# Single browser runs everything 
with sync_playwright() as p:
    print("Launching Chromium...")
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()

    # Scrapes jobs from the listing page
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
                                "title":         job["properties"]["title"],
                                "company":       job["properties"]["company"],
                                "location":      job["properties"]["location"],
                                "workModel":     job["properties"]["workModel"],
                                "applyUrl":      f"https://jobright.ai/jobs/info/{jobId}",
                                "industry":      job["properties"]["industry"],
                                "qualifications": job["properties"]["qualifications"],
                                "postedDate":    job["postedAt"]
                            })
            except Exception as e:
                print(f"Error: {e}")

    scrapePage.on("response", handleResponse)
    scrapePage.goto("https://jobright.ai/minisites-jobs/intern/us/swe")
    scrapePage.wait_for_load_state("networkidle")

    # Captures initial jobs from table
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

    for _ in range(10):
        prevCount = len(seenIds)
        tableBody.evaluate("el => el.scrollTop += 3000")
        scrapePage.wait_for_timeout(800)
        
        if len(seenIds) == prevCount:
            print(f"No new jobs after scroll, stopping at {len(seenIds)} jobs.")
            break

    # Logs into Jobright in a new tab
    jobrightPage = context.new_page()

    sessionLoaded = loadSession(context)
    if sessionLoaded and isLoggedIn(jobrightPage):
        print("Reusing cached session, skipping login.")

    else:
        print("No valid session, logging in...")
        loginToJobright(jobrightPage, context)

    # Closes the scraping tab, no longer needed
    scrapePage.close()
    print("Scraping tab closed.")

    # Collects all recent jobs
    recentJobs = [job for job in jobs if withinTimeLimit(job["postedDate"])]
    print(f"Found {len(recentJobs)} jobs within time limit out of {len(jobs)} total.")

    allNeededJobs = {}

    for job in recentJobs:
        if job["company"] not in allNeededJobs:
            allNeededJobs[job["company"]] = []

        allNeededJobs[job["company"]].append((
            job["title"], job["applyUrl"], job["location"],
            job["workModel"], job["industry"], job["postedDate"],
            job["qualifications"]
        ))

    for company in allNeededJobs:
        allNeededJobs[company].sort(key=lambda x: x[5], reverse=True)

    # Fetches real URLs using the logged in tab.
    print("Fetching real application URLs...")
    resolvedJobs = {}

    for company, listings in allNeededJobs.items():
        print(f"\nProcessing company: {company} ({len(listings)} listings)")

        resolvedJobs[company] = []

        for (title, jobrightURL, location, workModel, industry, postDate, qualifications) in listings:
            print(f"Processing: {title}")

            realURL = getApplicationURL(jobrightPage, jobrightURL)
            resolvedJobs[company].append((title, realURL, location, workModel, industry, postDate, qualifications))

    browser.close()
    print("Browser closed.")

# Filters the resolved jobs for a single user based on their filters.
def filterJobs(filters, resolvedJobs):
    userJobs = {}

    for company, listings in resolvedJobs.items():
        for (title, url, location, workModel, industry, postDate, qualifications) in listings:
            job = { "title": title, "industry": industry, "qualifications": qualifications }
            
            if validJob(job, filters):
                if company not in userJobs:
                    userJobs[company] = []
                userJobs[company].append((title, url, location, workModel, industry, postDate, qualifications))

    return dict(sorted(userJobs.items(), key=lambda x: max(j[5] for j in x[1]), reverse=True)) if userJobs else {}

# Filters and emails a single user and runs concurrently with other users.
async def processUser(email, filters, resolvedJobs, initialTime):
    print(f"Processing user: {email}")
    userJobs = filterJobs(filters, resolvedJobs)

    print(f"Sending {sum(len(v) for v in userJobs.values())} jobs to {email}")

    await asyncio.to_thread(sendEmail, userJobs, initialTime, email)

# Runs all users concurrently.
async def processAllUsers(resolvedJobs, initialTime):
    tasks = [
        processUser(email, filters, resolvedJobs, initialTime)
        for email, filters in USERS.items()
    ]

    # We'll send every task individualized.
    await asyncio.gather(*tasks)

asyncio.run(processAllUsers(resolvedJobs, initialTime))