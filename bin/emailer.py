import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from dotenv import load_dotenv
import os

load_dotenv()

# We format our job listing email using html.
def formatEmail(jobs):
    result = "<ul>"

    for job in jobs.keys():
        industry = ", ".join(jobs[job][0][4])
        result += f"<h2><b>{job} ({industry})</b></h2>"
        
        for title, link, loc, model, _, time in jobs[job]:
            indent = "&nbsp;&nbsp;" * 6
            postTime = (datetime.fromtimestamp(time / 1000) + timedelta(hours=8)).strftime('%-I:%M%p')
            result += f'<p>{indent}<span style="font-size:16px">{postTime} | </span> <a href="{link}">{title} | {loc} | {model}</a></p>'
    result += "</ul>"

    return result

# We then send our formatted html to our email using the email in the env.
def sendEmail(jobs):
    # We don't send any email if there is nothing to send.
    if not jobs:
        return
    
    today = datetime.now()

    body = formatEmail(jobs)

    msg = MIMEText(body, "html")

    sixHoursAgo = today - timedelta(hours=6)
    timeRange = f"({sixHoursAgo.strftime('%-I:%M%p')} - {today.strftime('%-I:%M%p')})"

    dateStr = today.strftime("%m/%d/%Y")
    
    msg["Subject"] = f"{dateStr} {timeRange} Job Postings" 
    msg["From"] = "jobnotifier.bot@gmail.com"
    msg["To"] = os.getenv("EMAIL")

    with smtplib.SMTP_SSL(("smtp.gmail.com"), 465) as server:
        server.login("jobnotifier.bot", os.getenv("PASSWORD"))
        server.sendmail("jobnotifier.bot", os.getenv("EMAIL"), msg.as_string())