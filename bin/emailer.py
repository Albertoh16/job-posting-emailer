import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from dotenv import load_dotenv
import os

load_dotenv() 

def formatEmail(jobs):
    result = "<ul>"

    for job in jobs.keys():
        result += f"<h2><b>{job}</b></h2>"
        
        for title, link in jobs[job]:
            result += f'<p><a href="{link}">{title}</a></p>'

    result += "</ul>"

    return result

def sendEmail(jobs):
    today = datetime.now() 

    body = formatEmail(jobs)

    msg = MIMEText(body, "html")

    email = (os.getenv("EMAIL") + "@" + os.getenv("DOMAIN"))

    msg["Subject"] = f"{today.strftime("%m/%d/%Y")} {today.strftime("%I:%M %p")} Job postings"
    msg["From"] = email
    msg["To"] = email

    with smtplib.SMTP_SSL(("smtp." + os.getenv("DOMAIN")), int(os.getenv("PORT"))) as server:
        server.login(email, os.getenv("PASSWORD"))
        server.sendmail(email, email, msg.as_string())