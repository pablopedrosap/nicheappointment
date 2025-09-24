import subprocess
import json
import os
import smtplib
import csv
import threading
import time
from datetime import datetime
import pandas as pd
from flask import Flask, request, jsonify, Response, send_from_directory, render_template, stream_with_context
from crewai_needs import queries_leads
from email_automation import run_email_automation
from utils import setup_logging
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from email_spider import EmailSpider
import logging
from scrapy.utils.log import configure_logging

# Configure logging for both Flask and Scrapy
configure_logging()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__, template_folder='landing_page', static_folder='landing_page')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/logs')
def logs():
    return render_template('logs.html')

def run_js_scraper(query):
    query_json = json.dumps([query])
    escaped_query_json = query_json.replace('"', '\\"')
    js_command = f'node src/lead_scraper/scrape.js "{escaped_query_json}"'
    logging.info(f"Running command: {js_command}")
    process = subprocess.Popen(js_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               bufsize=1, universal_newlines=True)

    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            logging.info(output.strip())

    rc = process.poll()
    if rc != 0:
        error = process.stderr.read()
        logging.error(f"Error running JS scraper: {error}")
        raise subprocess.CalledProcessError(rc, js_command)

    return process

def run_email_scraper():
    try:
        process = CrawlerProcess(get_project_settings())
        process.crawl(EmailSpider)
        process.start()
        logging.info("Email scraper finished running")
    except Exception as e:
        logging.error(f"Error running email scraper: {str(e)}")

def setup_smtp(gmail, app_password):
    smtp_server = "smtp.gmail.com"
    port = 587  # For starttls
    smtp_connection = smtplib.SMTP(smtp_server, port)
    smtp_connection.starttls()
    smtp_connection.login(gmail, app_password)
    return smtp_connection

def register_user(niche, location, website, name, offer, gmail):
    user_data = {
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'niche': niche,
        'location': location,
        'website': website,
        'name': name,
        'offer': offer,
        'gmail': gmail
    }

    csv_file_path = 'data/registered_users.csv'
    file_exists = os.path.isfile(csv_file_path)

    with open(csv_file_path, 'a', newline='') as csvfile:
        fieldnames = ['timestamp', 'niche', 'location', 'website', 'name', 'offer', 'gmail']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        writer.writerow(user_data)
    logging.info(f"New user registered: {name}")

def process_rows(user_site, user_name, custom_offer, smtp_connection, gmail, app_password):
    if not os.path.exists('src/lead_scraper/business_leads_with_emails.csv'):
        logging.warning("business_leads_with_emails.csv not found.")
        return

    try:
        with open('src/lead_scraper/business_leads_with_emails.csv', 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)
            run_email_automation(user_site, user_name, custom_offer, smtp_connection, gmail, app_password, rows)
    except Exception as e:
        logging.error(f"Error processing rows: {str(e)}")

def main(niche, location, user_site, user_name, custom_offer, gmail, app_password, callback):
    setup_logging()
    smtp_connection = setup_smtp(gmail, app_password)
    # queries = queries_leads(niche, location)
    queries = 'ghhghghg'

    for query in queries:
        logging.info(f"Processing query: {query}")
        # run_js_scraper(query)

        if not os.path.exists('src/lead_scraper/business_leads.csv'):
            logging.warning("The business_leads.csv file was not created.")
            continue

        # run_email_scraper()
        process_rows(user_site, user_name, custom_offer, smtp_connection, gmail, app_password)
        logging.info(f"Completed processing for query: {query}")
        if callback:
            callback(f"Completed processing for query: {query}")

@app.route('/api/start-campaign', methods=['POST'])
def start_campaign():
    data = request.json

    def generate():
        yield f"data: {json.dumps({'type': 'status', 'message': 'Campaign started'})}\n\n"

        try:
            # Register user
            register_user(
                niche=data['niche'],
                location=data['location'],
                website=data['website'],
                name=data['name'],
                offer=data['offer'],
                gmail=data['gmail']
            )
            yield f"data: {json.dumps({'type': 'log', 'message': 'User registered'})}\n\n"

            # Start the campaign process in a background thread
            thread = threading.Thread(target=run_campaign, args=(data,))
            thread.start()

            yield f"data: {json.dumps({'type': 'status', 'message': 'Campaign processing'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/campaign-status')
def campaign_status():
    def generate():
        while True:
            # Check campaign status and yield updates
            # This is a placeholder - you'll need to implement actual status checking
            yield f"data: {json.dumps({'type': 'log', 'message': 'Campaign is running...'})}\n\n"
            time.sleep(5)  # Send an update every 5 seconds

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


def run_campaign(data):
    try:
        def callback(message):
            # You might want to implement a way to send these messages to the client
            # For now, we'll just log them
            logging.info(f"Campaign update: {message}")

        main(
            niche=data['niche'],
            location=data['location'],
            user_site=data['website'],
            user_name=data['name'],
            custom_offer=data['offer'],
            gmail=data['gmail'],
            app_password=data['appPassword'],
            callback=callback
        )
    except Exception as e:
        logging.error(f"Campaign error: {str(e)}")

@app.route('/<path:path>')
def send_js(path):
    return send_from_directory('landing_page', path)

if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))