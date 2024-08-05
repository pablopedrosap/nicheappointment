import logging
import asyncio
from encodings import idna

import aiodns
import socket
from email_validator import validate_email, EmailNotValidError
import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.signalmanager import dispatcher
from scrapy import signals
import csv
import re
import pandas as pd
import random
from urllib.parse import urlparse, urljoin
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from scrapy.downloadermiddlewares.useragent import UserAgentMiddleware
import smtplib
import dns.resolver
import time
from concurrent.futures import ThreadPoolExecutor
import requests
from bs4 import BeautifulSoup
from twisted.internet.error import TCPTimedOutError, DNSLookupError
import unicodedata

class RotateUserAgentMiddleware(UserAgentMiddleware):
    def __init__(self, user_agent='Scrapy'):
        super().__init__()
        self.user_agent_list = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.157 Safari/537.36',
            'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1941.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; AS; rv:11.0) like Gecko',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2311.90 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.97 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:71.0) Gecko/20100101 Firefox/71.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.102 Safari/537.36',
        ]

    def process_request(self, request, spider):
        request.headers['User-Agent'] = random.choice(self.user_agent_list)

class EmailSpider(CrawlSpider):
    name = 'email_spider'

    custom_settings = {
        'DOWNLOADER_MIDDLEWARES': {
            'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
            'email_spider.RotateUserAgentMiddleware': 400,
        },
        'DOWNLOAD_DELAY': 2,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 8,
        'RETRY_TIMES': 3,
        'RETRY_HTTP_CODES': [500, 502, 503, 504, 522, 524, 408, 429],
        'LOG_LEVEL': 'INFO',
        'DOWNLOAD_TIMEOUT': 60,
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_START_DELAY': 5,
        'AUTOTHROTTLE_MAX_DELAY': 60,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 1.0,
        'CLOSESPIDER_TIMEOUT': 0,  # Disable auto-closing
        'CLOSESPIDER_PAGECOUNT': 0,  # Disable closing on page count
        'CONCURRENT_REQUESTS': 8,  # Reduce concurrent requests
    }

    def __init__(self, *args, **kwargs):
        super(EmailSpider, self).__init__(*args, **kwargs)
        self.start_urls = []
        self.visited_urls = set()
        self.visited_domains = {}
        self.missing_emails = []
        dispatcher.connect(self.spider_closed, signals.spider_closed)

        self.fieldnames = ['Name', 'Website', 'Email', 'Decision Maker']
        with open('src/lead_scraper/business_leads_with_emails.csv', 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            writer.writeheader()

        self.email_verification_pool = ThreadPoolExecutor(max_workers=10)
        # self.dns_resolver = aiodns.DNSResolver()
        self.verified_emails_cache = {}

    def start_requests(self):
        logging.info("Starting requests...")
        with open('src/lead_scraper/business_leads.csv', newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            self.fieldnames = reader.fieldnames + ['Email', 'Decision Maker']
            for row in reader:
                logging.info(f"Processing business: {row['Name']}")
                yield scrapy.Request(url=row['Website'], callback=self.process_business, meta={'row': row},
                                     errback=self.errback_httpbin, dont_filter=True)

    def errback_httpbin(self, failure):
        logging.error(f"Request failed: {failure.request.url}")
        if failure.check(TimeoutError, TCPTimedOutError, DNSLookupError, ConnectionRefusedError):
            request = failure.request
            logging.error(f"TimeoutError on {request.url}")
            yield scrapy.Request(request.url, callback=self.parse_item, dont_filter=True, meta=request.meta)

    def process_business(self, response):
        row = response.meta['row']
        domain = urlparse(row['Website']).netloc
        if domain.startswith("www."):
            domain = domain[4:]

        decision_maker = self.find_decision_maker(row['Name'], '')
        if decision_maker:
            logging.info(f"Found potential decision maker for {row['Name']}: {decision_maker}")
            # row['Decision Maker'] = decision_maker

            guessed_emails = self.guess_emails(decision_maker, domain)
            verified_email = None
            for email in guessed_emails:
                if self.verify_email(email):
                    row['Decision Maker'] = decision_maker
                    verified_email = email
                    break

            if verified_email:
                row['Email'] = verified_email
                self.write_to_csv(row)
                logging.info(f"Found and verified email: {verified_email} for {row['Name']}")
                return
            else:
                logging.info(
                    f"No verified email found for decision maker of {row['Name']}. Proceeding to crawl website.")

        logging.info(f"Crawling website for {row['Name']}: {row['Website']}")
        yield scrapy.Request(url=row['Website'], callback=self.parse_item, meta={'row': row, 'urls_crawled': 1},
                             errback=self.errback_httpbin, dont_filter=True)

    def parse_item(self, response):
        logging.info(f"Parsing {response.url}")
        row = response.meta['row']
        urls_crawled = response.meta.get('urls_crawled', 0)

        if urls_crawled > 10:
            logging.info(f"Reached maximum URLs for {row['Name']}. Moving to next business.")
            return

        emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", response.text)
        valid_emails = [email.lower() for email in emails if self.is_valid_email(email)]

        logging.info(f"Found {len(valid_emails)} potential emails on {response.url}")
        print(valid_emails)

        for email in valid_emails:
            row['Email'] = email
            self.write_to_csv(row)
            logging.info(f"Found and verified email: {email} for {row['Name']}")
            return

        domain = urlparse(row['Website']).netloc
        if domain.startswith("www."):
            domain = domain[4:]

        internal_links = self.get_internal_links(response, domain)
        for href in internal_links:
            if urls_crawled >= 10:
                break
            url = urljoin(response.url, href)
            if url.startswith('http'):
                urls_crawled += 1
                yield scrapy.Request(url, callback=self.parse_item, meta={'row': row, 'urls_crawled': urls_crawled}, errback=self.errback_httpbin)

    def find_decision_maker(self, company_name, location):
        search_query = f"{company_name} {location} linkedin"
        encoded_query = requests.utils.quote(search_query)
        url = f"https://www.google.com/search?q={encoded_query}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        try:
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')

            search_results = soup.find_all('h3', class_='LC20lb')

            for title in search_results:
                title_text = title.get_text()
                company_parts = company_name.lower().split()

                match = re.search(r'^([\w\s]+) - (.+)$', title_text)
                if match:
                    name = match.group(1)
                    company = match.group(2).lower()

                    if any(part in company for part in company_parts):
                        logging.info(f"Potential decision maker found: {name}")
                        return name

            return None
        except Exception as e:
            logging.error(f"Error finding decision maker for {company_name}: {e}")
            return None

    def get_internal_links(self, response, domain):
        links = response.css('a::attr(href)').getall()
        internal_links = [link for link in links if self.is_internal_link(link, domain)]
        important_pages = [link for link in internal_links if
                           any(page in link.lower() for page in ['about', 'team', 'contact', 'people'])]
        return important_pages + [link for link in internal_links if link not in important_pages]

    def is_internal_link(self, href, domain):
        parsed_href = urlparse(href)
        return parsed_href.netloc == '' or parsed_href.netloc == domain

    def guess_emails(self, name, domain):
        name_parts = name.lower().split()
        if len(name_parts) < 2:
            return []

        first_name, last_name = name_parts[0], name_parts[-1]
        patterns = [
            f"{first_name}.{last_name}@{domain}",
            f"{first_name}{last_name}@{domain}",
            f"{first_name}_{last_name}@{domain}",
            f"{first_name}-{last_name}@{domain}",
            f"{first_name}@{domain}",
            f"{last_name}@{domain}",
            f"{first_name[0]}{last_name}@{domain}",
            f"{first_name[0]}.{last_name}@{domain}",
            f"{first_name}{last_name[0]}@{domain}",
            f"{first_name}.{last_name[0]}@{domain}"
        ]
        return patterns

    def is_valid_email(self, email):
        if '@example.com' in email or 'test@' in email or 'filler@' in email or 'wix' in email or '@google.com' in email or 'name@' in email or 'example@' in email:
            return False
        if re.search(r"^\d", email) or re.search(r"^[^a-zA-Z]", email):
            return False
        if re.search(r"\d{2,}@|\W@", email):
            return False
        if re.search(r'\.(jpg|jpeg|png|webp|gif|bmp)$', email):
            return False
        return True

    def verify_email(self, email):
        domain = email.split('@')[-1]
        try:
            # Normalize the email address to handle non-ASCII characters
            email = unicodedata.normalize('NFKC', email)

            records = dns.resolver.resolve(domain, 'MX')
            mx_record = records[0].exchange.to_text().rstrip('.')
            with smtplib.SMTP(mx_record, timeout=10) as server:  # Increased timeout
                server.set_debuglevel(0)
                server.connect(mx_record)
                server.helo(server.local_hostname)
                server.mail('')
                code, _ = server.rcpt(str(email))
                server.quit()

                if code == 250:
                    logging.info(f"Verified email: {email}")
                    return True
                print(email)
                print(code)

        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, socket.timeout) as e:
            logging.warning(f"Connection issue while verifying {email}: {e}")
        except UnicodeEncodeError as e:
            logging.warning(f"Encoding issue with email {email}: {e}")
        except Exception as e:
            logging.error(f"Error verifying {email}: {e}")

        return False

    def write_to_csv(self, row):
        with open('src/lead_scraper/business_leads_with_emails.csv', 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            writer.writerow(row)
        logging.info(f"Wrote data for {row['Name']} to CSV")

    def spider_closed(self, spider):
        logging.info('Spider closed: CSV with emails saved.')
        df = pd.read_csv('src/lead_scraper/business_leads_with_emails.csv')
        df.drop_duplicates(subset=['Email'], inplace=True)
        df.to_excel('src/lead_scraper/business_leads_with_emails.xlsx', index=False)
        df.to_csv('src/lead_scraper/business_leads_with_emails.csv', index=False)
        logging.info('CSV converted to XLSX.')

        # Log businesses without emails
        businesses_with_emails = set(df['Name'])
        with open('src/lead_scraper/business_leads.csv', newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            all_businesses = set(row['Name'] for row in reader)

        businesses_without_emails = all_businesses - businesses_with_emails
        if businesses_without_emails:
            logging.info('Businesses without emails:')
            for business in businesses_without_emails:
                logging.info(business)

if __name__ == "__main__":
    process = CrawlerProcess()
    process.crawl(EmailSpider)
    process.start()