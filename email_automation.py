import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from dotenv import load_dotenv
from personalization import personalize_user_offer, personalize_prospect_email, craft_email, handle_email_response
import imaplib
import email
from datetime import datetime, timedelta
import pandas as pd
from typing import List, Dict, Any
import traceback
import random
import time

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


def send_email(recipient: str, subject: str, body: str, smtp_connection) -> bool:
    msg = MIMEMultipart()
    msg['Subject'], msg['From'], msg['To'] = subject, os.getenv('SMTP_USER'), recipient
    msg.attach(MIMEText(body, 'plain'))

    try:
        smtp_connection.sendmail(msg['From'], [msg['To']], msg.as_string())
        logging.info(f"Email sent to {recipient}")
        return True
    except Exception as e:
        logging.error(f"Failed to send email to {recipient}: {e}")
        return False


def check_for_responses(leads: List[Dict[str, Any]], gmail: str, app_password: str) -> None:
    try:
        with imaplib.IMAP4_SSL(os.getenv('IMAP_SERVER')) as mail:
            mail.login(gmail, app_password)
            mail.select('inbox')

            for lead in leads:
                if lead['Response'] is None:
                    _, search_data = mail.search(None, f'FROM {lead["Email"]}')
                    for num in search_data[0].split():
                        _, data = mail.fetch(num, '(RFC822)')
                        email_message = email.message_from_bytes(data[0][1])
                        lead['Response'] = 'Received'
                        lead['ResponseDate'] = datetime.now().isoformat()
                        lead['ResponseContent'] = get_email_content(email_message)
                        logging.info(f"Response received from {lead['Email']}")
    except Exception as e:
        logging.info(f"Error checking for responses: {e}")


def get_email_content(email_message):
    if email_message.is_multipart():
        for part in email_message.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode()
    else:
        return email_message.get_payload(decode=True).decode()


def get_email_thread(recipient: str, gmail: str, app_password: str) -> List[Dict[str, str]]:
    thread = []
    try:
        with imaplib.IMAP4_SSL(os.getenv('IMAP_SERVER')) as mail:
            mail.login(gmail, app_password)
            mail.select('sent')

            _, search_data = mail.search(None, f'TO {recipient}')
            for num in reversed(search_data[0].split()):  # Reverse to get most recent emails first
                _, data = mail.fetch(num, '(RFC822)')
                email_message = email.message_from_bytes(data[0][1])
                thread.append({
                    'subject': email_message['subject'],
                    'body': get_email_content(email_message),
                    'date': email.utils.parsedate_to_datetime(email_message['Date'])
                })
    except Exception as e:
        logging.info(f"Error retrieving email thread: {e}")

    return thread


def send_follow_ups(leads: List[Dict[str, Any]], user_offer: Dict[str, Any], smtp_connection, gmail: str,
                    app_password: str, user_name: str, user_web: str, last_positive_reply: str) -> None:
    for lead in leads:
        if lead['Response'] is not None and lead['FollowUpCount'] < 4:
            previous_emails = get_email_thread(lead['Email'], gmail, app_password)
            prospect_personalization = personalize_prospect_email(lead['Website'], '')

            response = handle_email_response(
                lead['ResponseContent'],
                user_offer,
                prospect_personalization,
                user_name,
                user_web,
                lead['Name'],
                previous_emails
            )

            follow_up_email = response['follow_up_email']

            if send_email(lead['Email'], follow_up_email['subject'], follow_up_email['body'], smtp_connection):
                lead['FollowUpCount'] += 1
                lead['LastEmailDate'] = datetime.now().isoformat()
                lead['LastEmailClassification'] = response['classification']
                logging.info(
                    f"Follow-up {lead['FollowUpCount']} sent to {lead['Email']} (Classification: {response['classification']})")

            # Update the last positive reply if this response was positive
            if response['classification'] == 'Interested' and response['last_positive_reply'] != "No positive reply found":
                last_positive_reply = response['last_positive_reply']


def run_email_automation(user_site: str, user_name: str, custom_offer, smtp_connection, gmail: str, app_password: str,
                         rows: List[Dict[str, Any]], callback=None) -> None:
    logging.info(f"Starting email automation for {len(rows)} leads")
    user_offer = personalize_user_offer(user_site, custom_offer)
    last_positive_reply = 'None'

    emails_to_send = random.randint(180, 220)
    logging.info(f"Aiming to send {emails_to_send} emails today")

    total_seconds = 8 * 60 * 60
    delay_between_emails = total_seconds / emails_to_send
    print(delay_between_emails)

    random.shuffle(rows)

    emails_sent = 0
    start_time = time.time()
    for lead in rows:
        print(lead)
        if emails_sent >= emails_to_send:
            break

        # if time.time() - start_time > 300:  # 5 minutes timeout
        #     logging.warning("Campaign duration exceeded 5 minutes. Stopping early.")
        #     break

        logging.info(f"Processing lead {emails_sent + 1}/{emails_to_send}: {lead.get('Name', 'Unknown')}")

        try:
            if lead.get('EmailSent') != 'True':
                logging.info(f"Personalizing prospect email for {lead.get('Name', 'Unknown')}")
                prospect_personalization = personalize_prospect_email(lead['Website'], custom_offer)

                logging.info(f"Crafting email for {lead.get('Name', 'Unknown')}")
                email_content = craft_email(user_offer, prospect_personalization, user_name, user_site,
                                            prospect_name=lead.get('Decision Maker', 'Unknown'),
                                            last_positive_reply=last_positive_reply)
                email_content = str(email_content)
                subject = email_content.split('\n')[0].split(': ', 1)[-1] if ': ' in email_content.split('\n')[0] else \
                email_content.split('\n')[0]
                body = '\n'.join(email_content.split('\n')[1:])

                logging.info(f"Sending email to {lead.get('Email', 'Unknown')}")

                if send_email(lead['Email'], subject, body, smtp_connection):
                    lead['EmailSent'] = 'True'
                    lead['LastEmailDate'] = datetime.now().isoformat()
                    emails_sent += 1
                    if callback:
                        callback(f"Email sent to: {lead.get('Name', 'Unknown')} ({lead['Email']})")

                    # Send CRM update every 2 emails
                    if emails_sent % 2 == 0:
                        if callback:
                            callback("CRM Update: " + json.dumps(rows[:emails_sent]))
                else:
                    if callback:
                        callback(f"Failed to send email to: {lead.get('Name', 'Unknown')} ({lead['Email']})")

                time.sleep(min(delay_between_emails + random.uniform(-5, 5), 10))  # Cap delay at 10 seconds for demo

            else:
                logging.info(f"Skipping lead {lead.get('Name', 'Unknown')}, email already sent")
        except Exception as e:
            logging.error(f"Error processing lead {lead.get('Name', 'Unknown')}: {str(e)}")
            logging.error(traceback.format_exc())

    logging.info(f"Sent {emails_sent} emails today")

    # Final CRM update
    if callback:
        callback("CRM Update: " + json.dumps(rows))

    logging.info(f"Sent {emails_sent} emails today")

    logging.info("Checking for responses")
    check_for_responses(rows, gmail, app_password)

    logging.info("Sending follow-ups")
    send_follow_ups(rows, user_offer, smtp_connection, gmail, app_password, user_name, user_site, last_positive_reply)

    logging.info("Updating CSV file")
    df = pd.DataFrame(rows)
    df.to_csv('src/lead_scraper/business_leads_with_emails.csv', index=False)
    logging.info("CSV file updated after follow-ups")

