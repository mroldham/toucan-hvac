from app import app, db, MonitoringAlert
from datetime import datetime
from dotenv import load_dotenv
import os
import smtplib
from email.message import EmailMessage

load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
FROM_EMAIL = os.getenv("FROM_EMAIL") or SMTP_USERNAME


def send_email(to_email, subject, body):
    msg = EmailMessage()
    msg["From"] = FROM_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)


with app.app_context():
    alerts = MonitoringAlert.query.filter(
        MonitoringAlert.notification_sent == False,
        MonitoringAlert.send_email == True,
        MonitoringAlert.email_address != None
    ).order_by(MonitoringAlert.timestamp.asc()).all()

    print(f"Pending email alerts: {len(alerts)}")

    for alert in alerts:
        subject = f"Toucan HVAC Alert: {alert.alert_type}"

        body = f"""
Toucan HVAC Monitoring Alert

Severity: {alert.severity}
Type: {alert.alert_type}
Message: {alert.message}
Time: {alert.timestamp}

Device ID: {alert.device_id}
Alert ID: {alert.id}
"""

        try:
            send_email(alert.email_address, subject, body)
            print(f"Email sent to {alert.email_address}")
        except Exception as e:
            print("EMAIL FAILED. Console fallback notification:")
            print("TO:", alert.email_address)
            print("SUBJECT:", subject)
            print(body)
            print("ERROR:", e)

        alert.notification_sent = True
        alert.notification_sent_at = datetime.utcnow()

        print(f"Sent alert {alert.id} to {alert.email_address}")

    db.session.commit()
    print("Done.")
