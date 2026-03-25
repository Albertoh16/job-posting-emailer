from playwright.sync_api import sync_playwright
from config import FILTERS
from emailer import sendEmail
from linkFetcher import skipJobrightPage
from datetime import datetime, timedelta, timezone

# We convert the millisecond timestamp to a UTC date and 
# time, then we only accept posts from the last 6 hours.
def withinTimeLimit(time):
    posted = datetime.fromtimestamp(time / 1000)
    now = datetime.now()
    return (now - posted) <= timedelta(hours=13)

# We only take in jobs that are applicable to our customized filter.
def validJob(job):
    # If we have no filters, we take any job we find.
    if not FILTERS:
        return True
    
    jobTitle = job["title"].lower()
    jobIndustry = ", ".join(job["industry"]).lower()
    jobQualifications = job["qualifications"].lower()

    # We check each field against its specific exclude list.
    if FILTERS.get("exclude position"):
        if any(word.lower() in jobTitle for word in FILTERS["exclude position"]):
            return False

    if FILTERS.get("exclude role"):
        if any(word.lower() in jobTitle for word in FILTERS["exclude role"]):
            return False

    if FILTERS.get("exclude specialization"):
        if any(word.lower() in jobTitle for word in FILTERS["exclude specialization"]):
            return False

    if FILTERS.get("exclude qualification"):
        if any(word.lower() in jobQualifications for word in FILTERS["exclude qualification"]):
            return False

    if FILTERS.get("exclude industry"):
        if any(word.lower() in jobIndustry for word in FILTERS["exclude industry"]):
            return False

    # We check if we find our keywords in the job title, also will return true for each filter that is empty.
    hasPosition = any(word.lower() in jobTitle for word in FILTERS["position"]) if FILTERS["position"] else True
    hasRole = any(word.lower() in jobTitle for word in FILTERS["role"]) if FILTERS["role"] else True
    hasSpecialization = any(word.lower() in jobTitle for word in FILTERS["specialization"]) if FILTERS["specialization"] else True
    hasQualification = any(word.lower() in jobQualifications for word in FILTERS["qualification"]) if FILTERS["qualification"] else True
    hasIndustry = any(word.lower() in jobIndustry for word in FILTERS["industry"]) if FILTERS["industry"] else True

    return hasPosition and hasRole and hasSpecialization and hasQualification and hasIndustry

initialTime = datetime.now(tz=timezone.utc)

# Creates an enviornment to utilize browser capabilities.
with sync_playwright() as p:
    # Opens the browser.
    browser = p.chromium.launch()

    # Creates a page within the browser.
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
                        if not withinTimeLimit(job["properties"]["postedAt"]):
                            break

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

    # When we get a response from the page, we run the handleResponse function to fetch our data.
    page.on("response", handleResponse)

    # We have the page go to a specific address.
    page.goto("https://jobright.ai/minisites-jobs/intern/us/swe")

    # We'll yield until the page has fully loaded.
    page.wait_for_load_state("networkidle")

    # We capture the initial jobs loaded on page load from __NEXT_DATA__.
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

    # We fetch the table body and scroll through it to load more rows.
    tableBody = page.query_selector(".index_bodyViewport__3xQLm")
    for _ in range(10):
        tableBody.evaluate("el => el.scrollTop += 3000")
        page.wait_for_timeout(1500)

    # We finally close our browser once we're done.
    browser.close()

newJobs = {}

# We go through all jobs in the rows and we append all 
# jobs that are in the last 6 hours and pass through our filter.
for job in jobs:
    if validJob(job):
        if job["company"] not in newJobs:
            newJobs[job["company"]] = []
        newJobs[job["company"]].append((job["title"], job["applyUrl"], job["location"], job["workModel"], job["industry"], job["postedDate"]))

# We sort the jobs within each company
for company in newJobs:
    newJobs[company].sort(key=lambda x: x[5], reverse=True)

# We'll then fetch the real links from all the jobright postings.
#newJobs = skipJobrightPage(newJobs) SKIPPED UNTIL THERE IS A CLEANER METHOD

# We then format and send our most to least recent sorted job list to an email.
sendEmail(dict(sorted(newJobs.items(), key=lambda x: max(j[5] for j in x[1]), reverse=True)), initialTime)
