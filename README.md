# Job Posting Emailer

This is an automated service that basically scrapes recent software engineering internship listings, filters them based on your personal preferences, and then delivers a personalized email digest on a schedule you choose.

---

## "Alright bro I heard enough, sign me up pls"

1. Just visit **[albertoh16.github.io/job-posting-emailer](https://albertoh16.github.io/job-posting-emailer)**
2. Enter your email and configure your filters, then submit and you'll start receiving emails on the next scheduled run.

---

## Filters

Each filter field accepts a list of keyword tags. Leave a field blank to match everything in that category.

| Filter | Description | Example |
|---|---|---|
| **Hierarchy** | Seniority or role type | `Intern, Co-op` |
| **Specialization** | Focus areas (matched against job title) | `Frontend, ML` |
| **Qualification** | Required skills (matched against job qualifications) | `Python, React` |
| **Industry** | Company sectors | `Fintech, Healthcare` |
| **Work Model** | Remote, Hybrid, or On-site | `Remote, Hybrid` |
| **Job Title** | Keywords used to semantically rank results | `Software Engineer` |
| **Intervals** | Times of day to receive emails (24h format) | `09:00, 17:00` |
| **Days** | Days of the week to receive emails | `Monday, Wednesday, Friday` |

---

## What You'll Receive

Each email covers the window of new postings since your last delivery and includes:

- Jobs grouped by company, with industry noted
- Each listing shows the **post time**, **job title**, **location**, and **work model** as a clickable link straight to the application

If no listings match your filters in a given interval, you'll get a short email letting you know, with a link back to the site to adjust your preferences.

---

## How It Works

### Scraping
Two job sources are scraped in parallel every time the service runs:

- **Jobright**: A headless Chromium browser (using Playwright) navigates Jobright's public SWE internship listing page, intercepts network responses to capture job data as it loads, and scrolls the table to collect additional results.
- **JobSpy**: Queries Indeed, LinkedIn, ZipRecruiter, Google, and Glassdoor concurrently using one search per unique job title across all active users.

Results from both sources are merged and deduplicated by company + title. Jobright listings are preferred when duplicates exist since they carry richer industry and qualifications data.

### User Configuration
User emails and filter preferences are stored in a Google Sheet managed via a Google Apps Script web endpoint. Each row maps to one recipient. The scraper fetches all rows at startup and parses them into structured filter sets.

### Filtering
For each user, the merged job list is run through their filters in two stages:

1. **Hard filters**: work model, hierarchy level, specialization (title), qualification, and industry must all match if set.
2. **ML title scoring**: if the user has set job title keywords, job titles are encoded using a sentence-transformer model (`all-MiniLM-L6-v2`) and scored against the query. Only jobs scoring above a dynamic z-score threshold are kept.

Each user gets a completely independent filtered result.

### Emailing
Filtered results are formatted into an HTML email and sent via Resend. All users are processed concurrently using `asyncio`.

---

## Stack

| Layer | Technology |
|---|---|
| Scraping & Automation | [Playwright](https://playwright.dev/python/) (headless Chromium) |
| Additional Job Sources | [JobSpy](https://github.com/Bunsly/JobSpy) |
| ML Filtering | [sentence-transformers](https://www.sbert.net/) (`all-MiniLM-L6-v2`) |
| Email Delivery | [Resend](https://resend.com) |
| User Data / Filters | Google Sheets + Google Apps Script |
| Scheduling | GitHub Actions (cron, runs hourly) |
| Runtime | Python 3.11 |
| Concurrency | `asyncio` + `concurrent.futures` |
| Environment Config | `python-dotenv` |

---

Alright tiger, now get out there and apply!
