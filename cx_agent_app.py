
import anthropic
import requests
import pandas as pd
import streamlit as st
from simple_salesforce import Salesforce
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import pytz
import json
import os

# ── Credentials from environment ─────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
SF_CLIENT_ID = os.environ.get("SF_CLIENT_ID")
SF_CLIENT_SECRET = os.environ.get("SF_CLIENT_SECRET")
SF_INSTANCE_URL = os.environ.get("SF_INSTANCE_URL")
CALENDAR_ID = os.environ.get("CALENDAR_ID")
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Google Calendar Connection ────────────────
@st.cache_resource
def get_calendar_service():
    SCOPES = ["https://www.googleapis.com/auth/calendar"]
    creds_dict = json.loads(GOOGLE_CREDENTIALS)
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=SCOPES
    )
    return build("calendar", "v3", credentials=credentials)

# ── Salesforce Connection ─────────────────────
@st.cache_resource
def get_salesforce():
    response = requests.post(
        f"{SF_INSTANCE_URL}/services/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": SF_CLIENT_ID,
            "client_secret": SF_CLIENT_SECRET
        }
    )
    token_data = response.json()
    return Salesforce(
        instance_url=token_data["instance_url"],
        session_id=token_data["access_token"]
    )

# ── Load Customers from Salesforce ───────────
@st.cache_data(ttl=86400)
def load_customers():
    sf = get_salesforce()
    result = sf.query("""
        SELECT Id, FirstName, LastName,
               Vehicle__c, Purchase_Months_Ago__c,
               Days_Since_Last_Contact__c, Missed_Service__c,
               Satisfaction_Score__c, Persona__c
        FROM Contact
        WHERE Vehicle__c != null
    """)
    customers = []
    for r in result["records"]:
        customers.append({
            "id": r["Id"],
            "name": f"{r['FirstName']} {r['LastName']}",
            "vehicle": r["Vehicle__c"],
            "purchase_months_ago": int(r["Purchase_Months_Ago__c"] or 0),
            "days_since_last_contact": int(r["Days_Since_Last_Contact__c"] or 0),
            "service_missed": r["Missed_Service__c"],
            "sentiment_score": float(r["Satisfaction_Score__c"] or 0),
            "persona": r["Persona__c"]
        })
    return pd.DataFrame(customers)

# ── Calendar Booking Tool ─────────────────────
def book_service_appointment(customer_name, vehicle, urgency):
    calendar_service = get_calendar_service()
    berlin_tz = pytz.timezone("Europe/Berlin")

    if urgency == "immediate":
        days_ahead = 1
    elif urgency == "this_week":
        days_ahead = 3
    else:
        days_ahead = 7

    for day_offset in range(days_ahead, days_ahead + 5):
        candidate = datetime.now(berlin_tz) + timedelta(days=day_offset)
        for hour in [10, 11, 14, 15]:
            start_time = candidate.replace(hour=hour, minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(hours=1)

            existing = calendar_service.events().list(
                calendarId=CALENDAR_ID,
                timeMin=start_time.isoformat(),
                timeMax=end_time.isoformat(),
                singleEvents=True
            ).execute()

            if not existing.get("items"):
                event = {
                    "summary": f"Service Appointment - {customer_name} ({vehicle})",
                    "description": f"Proactive retention appointment booked by CX AI Agent.\nCustomer: {customer_name}\nVehicle: {vehicle}\nUrgency: {urgency}",
                    "start": {"dateTime": start_time.isoformat(), "timeZone": "Europe/Berlin"},
                    "end": {"dateTime": end_time.isoformat(), "timeZone": "Europe/Berlin"},
                    "colorId": "11"
                }
                created = calendar_service.events().insert(
                    calendarId=CALENDAR_ID, body=event
                ).execute()
                return {
                    "booked": True,
                    "event_id": created["id"],
                    "slot": start_time.strftime("%A, %d %B at %H:%M"),
                    "advisor": "Servicemanager Weber",
                    "location": "Hauptfiliale Stuttgart",
                    "confirmation_code": f"SVC-{created['id'][:6].upper()}"
                }

    return {"booked": False, "message": "No available slots found"}

# ── Agent Tools Definition ────────────────────
tools = [
    {
        "name": "book_service_appointment",
        "description": "Books a real service appointment in the dealer Google Calendar. Use this when the customer is high risk and needs immediate proactive outreach with a concrete appointment offer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string", "description": "Full name of the customer"},
                "vehicle": {"type": "string", "description": "Customer vehicle model"},
                "urgency": {
                    "type": "string",
                    "enum": ["immediate", "this_week", "this_month"],
                    "description": "How urgently the appointment is needed"
                }
            },
            "required": ["customer_name", "vehicle", "urgency"]
        }
    }
]

# ── Agent Functions ───────────────────────────
def risk_agent(customer):
    prompt = f"""
    You are a CX analyst for a premium automotive dealer network.
    Analyze this customer and assess their churn risk:
    - Name: {customer["name"]}
    - Vehicle: {customer["vehicle"]}
    - Purchased: {customer["purchase_months_ago"]} months ago
    - Days since last contact: {customer["days_since_last_contact"]}
    - Missed last service: {customer["service_missed"]}
    - Satisfaction score: {customer["sentiment_score"]} out of 5
    - Persona: {customer["persona"]}
    Output exactly this format:
    RISK LEVEL: [Low / Medium / High]
    REASONS: [3 bullet points explaining why]
    KEY SIGNAL: [The single most alarming data point]
    """
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

def persona_agent(customer, risk_output):
    prompt = f"""
    You are a customer persona specialist for a premium automotive brand.
    CUSTOMER DATA:
    - Name: {customer["name"]}
    - Vehicle: {customer["vehicle"]}
    - Persona type: {customer["persona"]}
    - Satisfaction score: {customer["sentiment_score"]} out of 5
    - Purchased: {customer["purchase_months_ago"]} months ago
    RISK ASSESSMENT:
    {risk_output}
    Output exactly this format:
    WHO THEY ARE: [2 sentences]
    WHAT THEY VALUE: [3 bullet points]
    HOW TO COMMUNICATE: [tone, channel, approach]
    WHAT TO AVOID: [2 things]
    """
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

def action_agent(customer, risk_output, persona_output):
    messages = [
        {
            "role": "user",
            "content": f"""
You are a senior CX strategy advisor for a premium automotive dealer network.
Based on everything known about this customer, decide the best next action.
If the customer is high risk, use the booking tool to create a real appointment.

CUSTOMER: {customer["name"]} | {customer["vehicle"]} | {customer["persona"]}
RISK ASSESSMENT: {risk_output}
PERSONA BRIEF: {persona_output}

Provide your recommendation in exactly this format:
RECOMMENDED ACTION: [action]
WHY THIS ACTION: [2-3 sentences]
URGENCY: [Immediate / Within 1 week / Within 1 month]
SUCCESS METRIC: [How will we know this worked?]
CALENDAR SLOT: [slot details if booked, or N/A]
CONFIRMATION CODE: [code if booked, or N/A]
"""
        }
    ]

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        tools=tools,
        messages=messages
    )

    booked = False
    if response.stop_reason == "tool_use":
        tool_block = next(b for b in response.content if b.type == "tool_use")
        booking = book_service_appointment(
            tool_block.input["customer_name"],
            tool_block.input["vehicle"],
            tool_block.input["urgency"]
        )
        booked = booking.get("booked", False)
        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_block.id, "content": json.dumps(booking)}]
        })
        final_response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            tools=tools,
            messages=messages
        )
        return final_response.content[0].text, booked
    else:
        return response.content[0].text, booked

def communication_agent(customer, risk_output, persona_output, action_output):
    prompt = f"""
    You are a customer communication specialist for a premium automotive brand in Germany.
    Write a personalized email in German to this customer.
    CUSTOMER: {customer["name"]} | {customer["vehicle"]}
    PERSONA BRIEF: {persona_output}
    RECOMMENDED ACTION: {action_output}
    STRICT RULES:
    - Write in German
    - Maximum 120 words
    - Tone: direct, respectful, no marketing fluff
    - Do NOT mention satisfaction scores or internal data
    - Do NOT mention any internal AI systems or agents
    - Make it feel personal not automated
    - If a calendar slot was booked mention the specific date and time naturally
    - End with a specific call to action
    Output exactly this format:
    SUBJECT: [email subject line in German]
    EMAIL: [the full email body]
    """
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

# ── Streamlit UI ──────────────────────────────
st.set_page_config(page_title="CX Agent Demo", page_icon="🚗", layout="wide")

st.title("🚗 Automotive CX Retention Agent")
st.caption("Agentic AI Use Case | Salesforce CRM | Google Calendar ")

st.divider()

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Select Customer")

    with st.spinner("Loading from Salesforce CRM..."):
        df = load_customers()

    st.caption(f"✅ {len(df)} customers loaded from Salesforce")

    selected_name = st.selectbox("", df["name"])
    customer = df[df["name"] == selected_name].iloc[0]

    st.markdown("**Customer Profile**")
    st.markdown(f"🚙 **Vehicle:** {customer['vehicle']}")
    st.markdown(f"📅 **Ownership:** {customer['purchase_months_ago']} months")
    st.markdown(f"📞 **Last Contact:** {customer['days_since_last_contact']} days ago")
    st.markdown(f"🔧 **Missed Service:** {'Yes ⚠️' if customer['service_missed'] else 'No ✅'}")
    st.markdown(f"⭐ **Satisfaction:** {customer['sentiment_score']}/5")
    st.markdown(f"👤 **Persona:** {customer['persona']}")
    st.markdown(f"🔗 **Source:** Salesforce CRM")

    run = st.button("▶️ Run Agent Pipeline", use_container_width=True)

with col2:
    if run:
        st.subheader(f"Agent Pipeline — {selected_name}")

        with st.spinner("🔍 Agent 1: Analyzing churn risk from Salesforce data..."):
            risk = risk_agent(customer)
        with st.expander("🔍 Agent 1 — Risk Assessment", expanded=True):
            st.text(risk)

        with st.spinner("👤 Agent 2: Building persona profile..."):
            persona = persona_agent(customer, risk)
        with st.expander("👤 Agent 2 — Persona Profile", expanded=True):
            st.text(persona)

        with st.spinner("✅ Agent 3: Deciding action + checking Google Calendar..."):
            action, calendar_booked = action_agent(customer, risk, persona)
        with st.expander("✅ Agent 3 — Action + Calendar Tool", expanded=True):
            if calendar_booked:
                st.success("📅 Real appointment booked in Google Calendar")
            else:
                st.info("ℹ️ No calendar booking needed for this customer")
            st.text(action)

        with st.spinner("📧 Agent 4: Drafting personalized German email..."):
            communication = communication_agent(customer, risk, persona, action)
        with st.expander("📧 Agent 4 — Drafted Email", expanded=True):
            st.text(communication)

        st.success("✅ Pipeline Complete")
        st.caption("Data: Salesforce CRM | Calendar: Google Calendar | AI: Claude API")
    else:
        st.info("👈 Select a customer and click Run Agent Pipeline to start.")
