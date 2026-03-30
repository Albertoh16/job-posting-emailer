# Job Posting Emailer

An automated service that scrapes recent software engineering internship listings from [Jobright.ai](https://jobright.ai), filters them based on each user's personal preferences, and delivers a personalized email digest every few hours — with one click to open every application at once.

---

## How to Sign Up

1. Visit **[albertoh16.github.io/job-posting-emailer](https://albertoh16.github.io/job-posting-emailer)**
2. Enter your email address and configure your filters:
   - **Position**: job title keywords to include or exclude (e.g. `Software, Engineer`)
   - **Role**: seniority or role type to include or exclude (e.g. `Intern, Junior`)
   - **Specialization**: focus areas to include or exclude (e.g. `Frontend, ML`)
   - **Qualification**: required skills to include or exclude (e.g. `Python, React`)
   - **Industry**: sectors to include or exclude (e.g. `Fintech, Healthcare`)
3. Submit the form, you'll start receiving emails automatically on the next scheduled run.

> **Tip:** Leave a filter field blank to match everything in that category. The more specific your filters, the more targeted your results.

---

## What You'll Receive

Each email covers a rolling **~13-hour window** of new postings and includes:

- Jobs grouped by company, with their industry noted
- Each listing shows the **post time**, **job title**, **location**, and **work model** (remote/hybrid/on-site) as a clickable link straight to the application
- An **"Open All Applications"** button at the top that launches every job in a new tab at once, your browser may ask permission to open multiple tabs; just click **Allow**

If no listings match your filters in a given interval, you'll receive a short email letting you know, with a link back to the site to adjust your preferences.

---

## How It Works

The service runs on a scheduled interval and executes the following pipeline:

### 1. Scraping: `scraper.py`
A headless Chromium browser (via **Playwright**) navigates to Jobright's public SWE internship listing page. It intercepts network responses to capture job data as it loads, then scrolls the listing table to paginate and collect additional results. Jobs posted outside the last 13 hours are discarded immediately.

### 2. Authentication: `linkFetcher.py`
The scraper opens a second browser tab and logs into Jobright using stored credentials. Sessions are cached to a local file so repeat logins are avoided. Once authenticated, each job's Jobright URL is visited and the real external application URL is resolved by clicking the "Apply" button and capturing where it redirects.

### 3. User Configuration: `config.py`
User emails and their filter preferences are fetched from a **Google Sheet** via a **Google Apps Script** web endpoint. Each row maps to one recipient. Filters are parsed into structured sets used to match against job titles, qualifications, and industries.

### 4. Filtering: `scraper.py`
For each user, the full resolved job list is run through their filter set. Jobs must match all active include filters (position, role, specialization, qualification, industry) and must not match any exclude filters. Each user gets a completely independent filtered result.

### 5. Emailing: `emailer.py`
Filtered results are formatted into an HTML email and sent via **Resend**. All users are processed concurrently using `asyncio`. The email includes an "Open All" button, company-grouped listings with timestamps, and direct links to each application.

---

## Stack

| Layer | Technology |
|---|---|
| Scraping & Automation | [Playwright](https://playwright.dev/python/) (headless Chromium) |
| Email Delivery | [Resend](https://resend.com) |
| User Data / Filters | Google Sheets + Google Apps Script |
| Scheduling | Cron (or any task scheduler) |
| Runtime | Python 3.14 |
| Concurrency | `asyncio` + `asyncio.to_thread` |
| Environment Config | `python-dotenv` |

---

## Environment Variables

The following variables must be set in a `.env` file at the project root:

```
JOBRIGHT_EMAIL=your_jobright_email
JOBRIGHT_PASSWORD=your_jobright_password
RESEND_API_KEY=your_resend_api_key
APPS_SCRIPT_URL=your_google_apps_script_url
```
