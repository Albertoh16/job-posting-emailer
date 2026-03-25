from playwright.sync_api import sync_playwright
from config import USERS
from emailer import sendEmail
from linkFetcher import skipJobrightPage
from datetime import datetime, timedelta, timezone

# We convert the millisecond timestamp to a UTC date and
# time, then we only accept posts from the last 6 hours.
def withinTimeLimit(time):
    posted = datetime.fromtimestamp(time / 1000)
    now = datetime.now()
    return (now - posted) <= timedelta(hours=13)

# We only take in jobs that are applicable to a given user's filters.
def validJob(job, filters):
    # If the user has no filters, they get all jobs.
    if not filters:
        return True

    jobTitle = job["title"].lower()
    jobIndustry = ", ".join(job["industry"]).lower()
    jobQualifications = job["qualifications"].lower()

    # We check each field against its specific exclude list.
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

    # Returns true for each filter that is empty (no restriction).
    hasPosition = any(word.lower() in jobTitle for word in filters["position"]) if filters["position"] else True
    hasRole = any(word.lower() in jobTitle for word in filters["role"]) if filters["role"] else True
    hasSpecialization = any(word.lower() in jobTitle for word in filters["specialization"]) if filters["specialization"] else True
    hasQualification = any(word.lower() in jobQualifications for word in filters["qualification"]) if filters["qualification"] else True
    hasIndustry = any(word.lower() in jobIndustry for word in filters["industry"]) if filters["industry"] else True

    return hasPosition and hasRole and hasSpecialization and hasQualification and hasIndustry

initialTime = datetime.now(tz=timezone.utc)

# If there are no users in the sheet, there's nothing to do.
if not USERS:
    print("No users found in sheet, exiting.")
    exit()

# Scrapes all jobs once.
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()

    jobs = []
    seenIds = set()

    # When we load into the page, we take all data from the rows we can get.
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
                                "title": job["properties"]["title"],
                                "company": job["properties"]["company"],
                                "location": job["properties"]["location"],
                                "workModel": job["properties"]["workModel"],
                                "applyUrl": f"https://jobright.ai/jobs/info/{jobId}",
                                "industry": job["properties"]["industry"],
                                "qualifications": job["properties"]["qualifications"],
                                "postedDate": job["postedAt"]
                            })
            except Exception as e:
                print(f"Error: {e}")

    page.on("response", handleResponse)
    page.goto("https://jobright.ai/minisites-jobs/intern/us/swe")
    page.wait_for_load_state("networkidle")

    # Captures the initial jobs loaded on page load from the table.
    data = page.evaluate("""() => JSON.parse(document.getElementById('__NEXT_DATA__').textContent)""")
    for job in data["props"]["pageProps"]["initialJobs"]:
        jobId = job["id"]
        if jobId not in seenIds:
            seenIds.add(jobId)
            jobs.append({
                "title": job["title"],
                "company": job["company"],
                "location": job["location"],
                "workModel": job["workModel"],
                "applyUrl": job["applyUrl"],
                "industry": job["industry"],
                "qualifications": job["qualifications"],
                "postedDate": job["postedDate"]
            })

    # Scrolls to load more rows.
    tableBody = page.query_selector(".index_bodyViewport__3xQLm")
    for _ in range(10):
        prevCount = len(seenIds)
        tableBody.evaluate("el => el.scrollTop += 3000")
        page.wait_for_timeout(800)

        if len(seenIds) == prevCount:
            print(f"No new jobs found after scroll, stopping early at {len(seenIds)} jobs.")
            break

    browser.close()

# Filters to only jobs within the time window.
recentJobs = [job for job in jobs if withinTimeLimit(job["postedDate"])]
print(f"Found {len(recentJobs)} jobs within time limit out of {len(jobs)} total.")

# Collect all unique jobs needed across all users and fetches real URLs once for all jobs, 
# then filter per user.
allNeededJobs = {}
for job in recentJobs:
    if job["company"] not in allNeededJobs:
        allNeededJobs[job["company"]] = []
    allNeededJobs[job["company"]].append((
        job["title"], job["applyUrl"], job["location"],
        job["workModel"], job["industry"], job["postedDate"]
    ))

# Sorts jobs within each company by most recent first.
for company in allNeededJobs:
    allNeededJobs[company].sort(key=lambda x: x[5], reverse=True)

# Fetches all real application URLs once.
print("Fetching real application URLs...")
resolvedJobs = skipJobrightPage(allNeededJobs)

# Filters and emails each user individually
for email, filters in USERS.items():
    print(f"\nProcessing user: {email}")

    userJobs = {}
    for company, listings in resolvedJobs.items():
        for (title, url, location, workModel, industry, postDate) in listings:
            job = {
                "title": title,
                "industry": industry,
                "qualifications": "",  
            }
            if validJob(job, filters):
                if company not in userJobs:
                    userJobs[company] = []
                userJobs[company].append((title, url, location, workModel, industry, postDate))

    # Sorts companies by most recent job.
    sortedUserJobs = dict(sorted(userJobs.items(), key=lambda x: max(j[5] for j in x[1]), reverse=True)) if userJobs else {}

    print(f"Sending {sum(len(v) for v in sortedUserJobs.values())} jobs to {email}")
    sendEmail(sortedUserJobs, initialTime, email)
