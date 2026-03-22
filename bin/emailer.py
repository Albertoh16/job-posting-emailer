import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from dotenv import load_dotenv
import os

load_dotenv()

# We format our job listing email using html.
def formatEmail(jobs):
    result = "<ul>"

    for job in jobs.keys():
        # We take the industries to place next to the company, but if there are no industries listed, 
        # then we'll just print nothing.
        industry = ", ".join(jobs[job][0][4])
        industryStr = f" ({industry})" if industry else ""
        result += f"<h2><b>{job}{industryStr}</b></h2>"
        
        for title, link, loc, model, _, time in jobs[job]:
            indent = "&nbsp;&nbsp;" * 6
            postTime = (datetime.fromtimestamp(time / 1000, tz=timezone.utc) + timedelta(hours=3)).strftime('%-I:%M%p')
            result += f'<p>{indent}<span style="font-size:16px">{postTime} | </span> <a href="{link}">{title} | {loc} | {model}</a></p>'
    result += "</ul>"

    return result

# We then send our formatted html to our email using the email in the env.
def sendEmail(jobs, runTime):
    # We don't send any email if there is nothing to send.
    if not jobs:
        return

    body = formatEmail(jobs)

    msg = MIMEText(body, "html")

    runTimeEDT = runTime - timedelta(hours=4)
    sixHoursAgo = runTimeEDT - timedelta(hours=6)
    timeRange = f"({sixHoursAgo.strftime('%-I:%M%p')} - {runTimeEDT.strftime('%-I:%M%p')})"
    dateStr = runTimeEDT.strftime("%m/%d/%Y")

    msg["Subject"] = f"{dateStr} {timeRange} Job Postings" 
    msg["From"] = "jobnotifier.bot@gmail.com"
    msg["To"] = os.getenv("EMAIL")

    with smtplib.SMTP_SSL(("smtp.gmail.com"), 465) as server:
        server.login("jobnotifier.bot@gmail.com", os.getenv("PASSWORD"))
        server.sendmail("jobnotifier.bot@gmail.com", os.getenv("EMAIL"), msg.as_string())
