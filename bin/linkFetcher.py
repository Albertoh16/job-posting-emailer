# DEPRICATED UNTIL I FIND A FASTER SOLUTION TO FETCH OUR LINKS.

import os
import time
import json
from dotenv import load_dotenv

load_dotenv()

EMAIL    = os.getenv("JOBRIGHT_EMAIL")
PASSWORD = os.getenv("JOBRIGHT_PASSWORD")

SESSION_FILE = "jobright_session.json"

# Saves the current browser context cookies to a file.
def saveSession(context):
    cookies = context.cookies()
    with open(SESSION_FILE, "w") as f:
        json.dump(cookies, f)
    print(f"Session saved ({len(cookies)} cookies).")


# Loads cookies from file into the browser context.
def loadSession(context):
    if not os.path.exists(SESSION_FILE):
        return False
    try:
        with open(SESSION_FILE, "r") as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        print(f"Session loaded ({len(cookies)} cookies).")
        return True
    except Exception as e:
        print(f"Failed to load session: {e}")
        return False
    
    # Checks if we're actually logged in by looking for a sign-in button.
def isLoggedIn(page):
    try:
        page.goto("https://jobright.ai/", timeout=10000)
        page.wait_for_load_state("domcontentloaded", timeout=5000)

    except Exception as e:
        print(f"Session check failed: {e}")
        return False
    
# Logs into Jobright on the given page and saves the session.
def loginToJobright(page, context):
    print("Navigating to https://jobright.ai/...")
    page.goto("https://jobright.ai/")

    print("Waiting for sign in button...")
    page.wait_for_selector("text=SIGN IN", timeout=10000)
    page.click("text=SIGN IN")

    print("Waiting for email input in popup...")
    page.wait_for_selector("input[placeholder='Email']", timeout=10000)

    page.fill("input[placeholder='Email']", EMAIL)
    page.fill("input[placeholder='Password']", PASSWORD)   

    print("Clicking submit...")
    page.click("#sign-in-content button:has-text('SIGN IN')")

    print("Waiting for login modal to close...")
    page.wait_for_selector(".ant-modal-content", state="hidden", timeout=15000)

    print(f"Login successful!")

    saveSession(context)

# Dismisses any blocking modals before we click the apply button.
def dismissModals(page):
    for closeSelector in [
        "button[aria-label='Close']",
        ".ant-modal-close",
        ".ant-modal-wrap",
    ]:
        try:
            btn = page.locator(closeSelector).first
            if btn.is_visible():
                btn.click(timeout=1000)
                page.wait_for_timeout(300)
                print(f"Dismissed modal with: {closeSelector}")
                break
        except:
            continue


# Fetches the real application URL from a single Jobright job page.
def getApplicationURL(page, jobURL):
    print(f"\nNavigating to job URL: {jobURL}")
    context = page.context
    page.goto(jobURL, timeout=15000)

    try:
        page.wait_for_load_state("domcontentloaded", timeout=5000)
    except:
        pass

    print(f"Page loaded. Current URL: {page.url}")

    try:
        applyButton = None

        for selector in [".index_applyButton__k3XwL", "text=Apply Now", "button:has-text('APPLY NOW')"]:
            try:
                btn = page.locator(selector).first
                if btn.is_visible():
                    print(f"Found apply button with selector: '{selector}'")
                    applyButton = btn
                    break
                else:
                    print(f"Selector '{selector}' found but not visible")
            except Exception as e:
                print(f"Selector '{selector}' failed: {e}")
                continue

        if not applyButton:
            print(f"No apply button found, returning original URL")
            return jobURL

        dismissModals(page)

        try:
            with context.expect_page(timeout=4000) as newPageInfo:
                try:
                    page.wait_for_selector("text=Apply Without Customizing", timeout=2000)
                    print("Resume modal appeared, clicking 'Apply Without Customizing'...")
                    page.click("text=Apply Without Customizing")
                except:
                    pass

            newPage = newPageInfo.value
            newPage.wait_for_load_state("domcontentloaded", timeout=5000)
            realURL = newPage.url
            print(f"New tab opened with URL: {realURL}")
            newPage.close()
            return realURL

        except Exception as e:
            print(f"No new tab detected ({e}), checking for same-tab redirect...")
            time.sleep(1)
            realURL = page.url

            if realURL != jobURL:
                print(f"Same-tab redirect to: {realURL}")
                page.go_back()
                return realURL

            print(f"No redirect found, returning original Jobright URL")
            return jobURL
        
    except Exception as e:
        print(f"Exception in getApplicationURL: {e}")
        return jobURL
    
# Receives an existing logged in page and resolves all job URLs.
# No browser is created here, scraper.py owns the browser.
def skipJobrightPage(jobs: dict, page) -> dict:
    print(f"\nskipJobrightPage called with {sum(len(v) for v in jobs.values())} total jobs across {len(jobs)} companies")

    fixedJobs = {}
    for company, listings in jobs.items():
        print(f"\nProcessing company: {company} ({len(listings)} listings)")
        fixedJobs[company] = []
        for (title, jobrightURL, location, workModel, industry, postDate) in listings:
            print(f"Processing: {title}")
            realURL = getApplicationURL(page, jobrightURL)
            fixedJobs[company].append((title, realURL, location, workModel, industry, postDate))

    print(f"\nDone! Resolved {sum(len(v) for v in fixedJobs.values())} jobs")
    return fixedJobs