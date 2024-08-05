import os
import requests
from bs4 import BeautifulSoup
from langchain_openai import ChatOpenAI
from crewai import Agent, Task, Crew
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()

openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("OPENAI_API_KEY not found in environment variables")

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)

def scrape_website(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        text_content = ' '.join([tag.get_text(strip=True) for tag in soup.find_all(['p', 'h1', 'h2', 'h3', 'li', 'span', 'div']) if tag.name not in ['script', 'style']])
        return ' '.join(text_content.split()[:2000])  # Adjusted to 2000 words
    except Exception as e:
        logging.error(f"Error scraping {url}: {str(e)}")
        return ""

def create_agent(role, goal, backstory):
    return Agent(role=role, goal=goal, backstory=backstory, tools=[], verbose=True, llm=llm)

def generate_personalized_content(website_content, query, expected_output, agent, custom_offer):
    task = Task(description=f"Analyze the following website content and {query}:\n\n{website_content}. {custom_offer}", agent=agent, expected_output=expected_output)
    crew = Crew(agents=[agent], tasks=[task], verbose=True)
    return crew.kickoff()

def personalize_user_offer(user_site, custom_offer):
    user_content = scrape_website(user_site)
    if not user_content:
        return "Unable to generate a personalized offer due to website scraping issues."

    content_generator = create_agent(
        role='Content Generator',
        goal='Generate concise yet compelling personalized content based on website data.',
        backstory='You are an expert in distilling complex information into clear, impactful marketing messages.'
    )

    query = 'Create a focused, compelling offer based on the user\'s website. Highlight key benefits and a clear value proposition.'
    expected_output = '''1. Unique Value Proposition (1 sentence)
    2. Key Benefits (2-3 bullet points)
    3. Target Audience Pain Point (1 sentence)
    4. Call-to-Action (1 concise sentence)'''

    if custom_offer:
        custom_offer = f'''---------THE USER WANTS TO:  {custom_offer}'''
    offer = generate_personalized_content(user_content, query, expected_output, content_generator, custom_offer)
    logging.info(f"Generated personalized offer for {user_site}")
    return offer

def personalize_prospect_email(lead_site, custom_offer):
    prospect_content = scrape_website(lead_site)
    if not prospect_content:
        return "Unable to personalize the email due to website scraping issues."

    content_generator = create_agent(
        role='Content Generator',
        goal='Extract key insights for personalized outreach.',
        backstory='You excel at identifying crucial business details for targeted, relevant communication.'
    )

    query = 'Identify the most relevant details about the prospect\'s business for a personalized email.'
    expected_output = '''1. Prospects's Main product/service focus (1 sentence)
    2. Prospects's Target audience or market (1 sentence)
    3. Prospects's Recent achievement or news (if any) (1 sentence)
    4. Prospects's Potential pain point or challenge (1-2 sentences)
    5. Language of the website:'''

    custom_offer = ''
    email_content = generate_personalized_content(prospect_content, query, expected_output, content_generator, custom_offer)
    logging.info(f"Generated personalized email content for {lead_site}")
    return email_content


def classify_email(email_content):
    email_classifier = create_agent(
        role='Email Intent Classifier',
        goal='Accurately classify incoming emails based on their content and intent.',
        backstory='You are an AI expert in understanding email communications and their underlying intents.'
    )

    task = Task(
        description=f'''Classify the following email based on its content and intent. Provide a classification and a brief explanation.

        Email Content:
        {email_content}

        Possible Classifications:
        1. Interested - Prospect shows clear interest in the offer
        2. Need More Info - Prospect requests additional information
        3. Not Interested - Prospect declines the offer
        4. Wrong Person - Email was sent to the wrong contact
        5. Out of Office - Automated response indicating unavailability
        6. Other - Any other type of response

        Guidelines:
        - Provide a single classification that best fits the email
        - Give a brief explanation (1-2 sentences) for your classification
        ''',
        agent=email_classifier,
        expected_output='''Classification: [One of the above categories]
        Explanation: [Brief explanation for the classification]'''
    )
    crew = Crew(agents=[email_classifier], tasks=[task], verbose=True)
    return crew.kickoff()


def get_last_positive_reply(previous_emails):
    email_classifier = create_agent(
        role='Email Classifier',
        goal='Identify the most recent positive reply from the prospect.',
        backstory='You are an expert in analyzing email sentiment and identifying positive responses.'
    )

    task = Task(
        description=f'''Analyze the following email thread and identify the most recent positive reply from the prospect. A positive reply shows interest, asks for more information, or expresses willingness to engage further.

        Email Thread:
        {previous_emails}

        Guidelines:
        - Focus on the prospect's replies, not the sender's emails
        - Look for expressions of interest, requests for more information, or willingness to continue the conversation
        - If there are multiple positive replies, choose the most recent one
        - If there are no positive replies, return "No positive reply found"
        ''',
        agent=email_classifier,
        expected_output='''Most recent positive reply: [Content of the positive reply or "No positive reply found"]'''
    )
    crew = Crew(agents=[email_classifier], tasks=[task], verbose=True)
    return crew.kickoff()


def craft_email(user_offer, prospect_personalization, user_name, user_web, prospect_name, last_positive_reply=None):
    if len(prospect_name) < 3:
        prospect_name = 'use business name'
    email_crafter = create_agent(
        role='Friendly Email Crafting Specialist',
        goal='Craft engaging, cold emails that feel like they\'re from a friend, offer real value, and intrigue the recipient.',
        backstory='You are an expert in writing impactful emails that are casual and focus on solving pain points rather than listing features.'
    )

    task_description = f'''Craft a short and concise friendly, intriguing ready to send email(no brackets[] to fill data) that feels like it's from a helpful and desinterested acquaintance, CANT'T feel like a sale.
    Include some sense of humor and light-hearted comment or observation.
    Sender: {user_name}
    sender website: {user_web}, put it once only.
    Prospect name: {prospect_name}
    Offer: {user_offer}\n\n
    Prospect Info: {prospect_personalization}

    Guidelines:
    VERY IMPORTANT: write the email in the language of the website even though this instructions are in english.
    1. Subject: Intriguing and casual, under 40 characters. example, Question or similar
    2. Opening: Super personalized, friendly sentence showing understanding of prospect's situation
    3. Body: focusing on solving pain points
    5. Tangible Value: Offer must be specific in object, quantity and time. 
    6. Call-to-Action: One clear, low-pressure ask for a future appointment
    7. Overall tone: Casual, valuable, desinterested and friendly, like a note from a helpful acquaintance
    8. No unnecessary mention of the product or service that has no relevance to the prospect'''

    if last_positive_reply and last_positive_reply != 'None':
        task_description += f'''\n\nLast Positive Reply Example:
        {last_positive_reply}

        Use this positive reply as inspiration for the tone and content of your email. Identify what worked well in this reply and incorporate similar elements into your new email.'''

    task = Task(
        description=task_description,
        agent=email_crafter,
        expected_output='''Complete email ready to send written with no placeholder text or anything below or after.'''
    )
    crew = Crew(agents=[email_crafter], tasks=[task], verbose=True)
    return crew.kickoff()


def craft_follow_up_email(user_offer, prospect_personalization, user_name, user_web, prospect_name, previous_emails,
                          email_classification, last_positive_reply=None):
    follow_up_crafter = create_agent(
        role='Follow-up Email Specialist',
        goal='Craft personalized and effective follow-up emails based on previous interactions.',
        backstory='You are an expert in nurturing leads through thoughtful and targeted follow-up communications.'
    )

    task_description = f'''Craft a personalized follow-up email based on the previous interaction and the prospect's response classification.

    Sender: {user_name}
    Sender Website: {user_web}
    Prospect Name: {prospect_name}
    Offer: {user_offer}
    Prospect Info: {prospect_personalization}
    Previous Emails: {previous_emails}
    Email Classification: {email_classification}

    Guidelines:
    1. Tailor the follow-up based on the email classification and previous interactions
    2. Maintain a friendly and helpful tone
    3. Address any concerns or questions raised in the prospect's response
    4. Provide additional value or information relevant to the prospect's situation
    5. Include a clear but low-pressure call-to-action
    6. Keep the email concise and focused
    7. Use the same language as the prospect's website'''

    if last_positive_reply:
        task_description += f'''\n\nLast Positive Reply Example:
        {last_positive_reply}

        Use this positive reply as inspiration for the tone and content of your follow-up email. Identify what worked well in this reply and incorporate similar elements into your new email.'''

    task = Task(
        description=task_description,
        agent=follow_up_crafter,
        expected_output='''Complete follow-up email ready to send, including subject line and body.'''
    )
    crew = Crew(agents=[follow_up_crafter], tasks=[task], verbose=True)
    return crew.kickoff()


def handle_email_response(response_content, user_offer, prospect_personalization, user_name, user_web, prospect_name,
                          previous_emails):
    # First, classify the email
    classification = classify_email(response_content)

    # Get the last positive reply
    last_positive_reply = get_last_positive_reply(previous_emails)

    # Then, craft an appropriate follow-up based on the classification and last positive reply
    follow_up_email = craft_follow_up_email(
        user_offer,
        prospect_personalization,
        user_name,
        user_web,
        prospect_name,
        previous_emails,
        classification,
        last_positive_reply
    )

    return {
        'classification': classification,
        'follow_up_email': follow_up_email,
        'last_positive_reply': last_positive_reply
    }


# def craft_email(user_offer, prospect_personalization, user_name, user_web, prospect_name):
#     if len(prospect_name) < 3:
#         prospect_name = 'use business name'
#     email_crafter = create_agent(
#         role='Friendly Email Crafting Specialist',
#         goal='Craft engaging, cold emails that feel like they\'re from a friend, offer real value, and intrigue the recipient.',
#         backstory='You are an expert in writing impactful emails that are casual and focus on solving pain points rather than listing features.'
#     )
#
#     task = Task(
#         description=f'''Craft a short and concise friendly, intriguing ready to send email(no brackets[] to fill data) that feels like it's from a helpful and desinterested acquaintance, CANT'T feel like a sale.
#         Include some sense of humor and light-hearted comment or observation.
#         Sender: {user_name}
#         sender website: {user_web}, put it once only.
#         Prospect name: {prospect_name}
#         Offer: {user_offer}\n\n
#         Prospect Info: {prospect_personalization}
#
#         Guidelines:
#         VERY IMPORTANT: write the email in the language of the website even though this instructions are in english.
#         1. Subject: Intriguing and casual, under 40 characters. example, Question or similar
#         2. Opening: Super personalized, friendly sentence showing understanding of prospect's situation
#         3. Body: focusing on solving pain points
#         5. Tangible Value: Offer must be specific in object, quantity and time.
#         6. Call-to-Action: One clear, low-pressure ask for a future appointment
#         7. Overall tone: Casual, valuable, desinterested and friendly, like a note from a helpful acquaintance
#         8. No unnecessary mention of the product or service that has no relevance to the prospect''',
#
#         agent=email_crafter,
#         expected_output='''Complete email ready to send written with no placeholder text or anything below or after.'''
#     )
#     crew = Crew(agents=[email_crafter], tasks=[task], verbose=True)
#     return crew.kickoff()
