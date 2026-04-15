# cx_agent_demo

Automotive CX Retention Agent-
An Agentic AI proof of concept for proactive aftersales customer retention in automotive dealer networks.
What It Does
Four AI agents work through each customer from a live Salesforce CRM:

Risk Monitor — reads CRM signals and flags churn risk level
Persona Analyst — builds a dynamic customer profile from risk output
Action Advisor — autonomously decides whether to book a real service appointment via Google Calendar API
Email Drafter — writes a personalized outreach email in German, held for human review

Live Demo
cx-agent-aftersales.streamlit.app
Tech Stack

AI — Claude API (Anthropic), Agentic tool use with native function calling
CRM — Salesforce Developer Edition, queried live via simple-salesforce
Calendar — Google Calendar API, real appointment booking with conflict checking
Frontend — Streamlit
Language — Python

Key Features

Live Salesforce CRM connection — 16 customers with custom fields mirroring real dealer data structure
Genuine agentic behavior — Agent 3 autonomously decides whether to use the calendar tool based on customer risk profile
Real Google Calendar booking — conflict checking, Berlin timezone, confirmation codes generated
Human-in-the-loop — all outreach held for human review before any customer contact
Data stays within CRM infrastructure — no customer data leaves the environment without proper processing agreements

Project Structure
cx_agent_app.py      — Main Streamlit application
requirements.txt     — Python dependencies
Setup
Clone the repository and add the following secrets to Streamlit Cloud:
ANTHROPIC_API_KEY
SF_CLIENT_ID
SF_CLIENT_SECRET
SF_INSTANCE_URL
CALENDAR_ID
GOOGLE_CREDENTIALS
Disclaimer
All customer data shown is fictional and created solely for demonstration purposes.
Author
Siddharth Pandya — M.Sc. TU München
Customer Experience & AI | Audi Sport GmbH · Porsche AG · MHP – A Porsche Company
