import json
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict

import streamlit as st

from agents import plan_day_workflow

st.set_page_config(
    page_title="Agentic Day Planner",
    page_icon="🗓️",
    layout="wide",
)

st.markdown(
    """
    <style>
        .hero-card {
            padding: 1.5rem;
            border-radius: 18px;
            background: linear-gradient(135deg, #3b82f6, #9333ea);
            color: #fff;
            margin-bottom: 1.25rem;
            text-align: center;
        }
        .hero-card h1 {
            margin-bottom: 0.5rem;
            font-size: 2rem;
        }
        .status-log {
            font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
            background: #0f172a;
            color: #e2e8f0;
            padding: 1rem;
            border-radius: 12px;
            min-height: 120px;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
        }
        .status-log p {
            margin: 0.2rem 0;
            font-size: 1.2rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

REQUIREMENTS = [
    "Conversational greeting before showing the planner form",
    "Live agent-style progress updates while the crew works",
    "Post-plan feedback loop to regenerate the itinerary",
]

st.sidebar.title("📝 Requirements Tracker")
for requirement in REQUIREMENTS:
    st.sidebar.markdown(f"- {requirement}")


def safe_json(value: Any) -> Dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, (str, bytes, bytearray)):
        value = str(value)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def send_email_report(recipient: str, subject: str, body: str) -> str:
    # NOTE: You must allow "Less secure apps" or use an App Password if using Gmail.
    # Credentials are now managed here, NOT via UI input.
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = "durgaasus@gmail.com"
    sender_password = "rlbo tdsd zmqr mllc"  # WARNING: Avoid committing real passwords to repo

    try:
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        return "Email sent successfully!"
    except Exception as e:
        return f"Failed to send email: {e}"


def run_plan(
    user_data: Dict[str, str],
    plan_date_iso: str,
    commitments: str | None,
    *,
    adjustments: str | None = None,
    status_panel=None,
) -> None:
    status_panel = status_panel or st.container()
    icons = {
        "persona": "🧠",
        "weather": "🌤️",
        "insights": "🛰️",
        "planning": "🗺️",
        "done": "✅",
    }
    log: list[str] = []

    def push(stage: str, message: str) -> None:
        entry = f"{icons.get(stage, '🤖')} {message}"
        log.append(entry)
        # Update the status panel with ONLY the current message, replacing previous content
        status_panel.markdown(
            f"""
            <div class='status-log'>
                <p>{entry}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.spinner("Summoning your specialist crew..."):
        try:
            response = plan_day_workflow(
                user_data,
                plan_date=plan_date_iso,
                commitments=commitments,
                adjustments=adjustments,
                progress=push,
            )
            push("done", "All agents finished! Publishing your itinerary.")
            st.session_state["result"] = response
            st.session_state["last_status_log"] = log[:]
            st.session_state["last_payload"] = {
                "user_data": user_data,
                "plan_date": plan_date_iso,
                "commitments": commitments,
            }
        except Exception as exc:
            st.error(f"Plan generation failed: {exc}")


st.session_state.setdefault("show_form", False)
st.session_state.setdefault(
    "chat_history",
    [
        {
            "role": "assistant",
            "content": "Hey there! I'm your friendly planner bot. Share how you're feeling today "
            "and I'll get ready to craft your perfect day off. When you're ready, hit the "
            "**Plan my day** button and I'll spin up the crew.",
        }
    ],
)


def companion_reply(message: str) -> str:
    text = message.lower()
    if any(greet in text for greet in ("hi", "hello", "hey", "namaste", "hola")):
        return (
            "Hi! I'm all ears. Tell me the vibe you're chasing—chill, adventurous, foodie—and "
            "tap **Plan my day** whenever you want me to start the heavy lifting."
        )
    if "thanks" in text or "thank you" in text:
        return "Always happy to help! Want me to start planning? Tap the button when you're ready."
    if "who" in text or "what" in text:
        return (
            "I'm a mini crew of specialists—one grabs weather intel, another finds hyperlocal buzz, "
            "and I stitch the perfect schedule together just for you."
        )
    if "ready" in text or "start" in text or "plan" in text:
        return "Great! Press **Plan my day** below and I'll get to work."
    return (
        "Love the energy! Send me anything you'd like to focus on (movies, games, cozy cafes) "
        "and tap **Plan my day** when you want the full itinerary."
    )


# --- HERO SECTION ---
hero = st.container()
with hero:
    st.markdown(
        """
        <div class="hero-card">
            <h1>Hey there 👋 I'm your Day Planner Assistant</h1>
            <p>Tell me when you're free and what you feel like doing. I'll deploy a research crew to check the weather, scan city buzz, and build a perfectly paced plan.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

# --- CHAT SECTION ---
if not st.session_state["show_form"]:
    st.markdown("### 💬 Chat with your planner")
    for message in st.session_state["chat_history"]:
        with st.chat_message(message["role"]):
            st.write(message["content"])
    user_prompt = st.chat_input("Say hi or share your vibe")
    if user_prompt:
        st.session_state["chat_history"].append({"role": "user", "content": user_prompt})
        st.session_state["chat_history"].append({"role": "assistant", "content": companion_reply(user_prompt)})
        st.rerun()

    if st.button("Plan my day", use_container_width=True):
        st.session_state["show_form"] = True
        st.rerun()

# --- PLANNER FORM ---
main_container = st.container()
status_panel = st.container()

if st.session_state["show_form"]:
    with main_container:
        st.subheader("🎯 Tell me about your ideal day off")
        with st.form("user_form"):
            name = st.text_input("Full name")
            email = st.text_input("Email")
            location = st.text_input("Primary city / location")
            plan_date_val = st.date_input("Choose a date to plan", value=date.today())
            profession = st.text_input("Profession or current focus")
            hobbies = st.text_area("Hobbies (comma separated)")
            interests = st.text_area("Interests or ideal vibes for the day")
            commitments = st.text_area(
                "Must-do commitment(s) (optional)",
                placeholder="E.g., 16:00 meet friend at Gachibowli Stadium",
            )
            submit = st.form_submit_button("Launch agents 🚀")

        if submit:
            if not (name and email and location):
                st.error("Name, email, and location are required.")
            else:
                payload = {
                    "name": name,
                    "email": email,
                    "location": location,
                    "profession": profession,
                    "hobbies": hobbies,
                    "interests": interests,
                }
                st.session_state["latest_inputs"] = {
                    "user_data": payload,
                    "plan_date": plan_date_val.isoformat(),
                    "commitments": commitments.strip() or None,
                }
                run_plan(
                    payload,
                    plan_date_val.isoformat(),
                    commitments.strip() or None,
                    status_panel=status_panel,
                )

# --- RESULTS ---
result = st.session_state.get("result")
if result:
    st.divider()
    
    # Handle cases where persona isn't a clean dict
    persona_data = result.get("persona")
    if isinstance(persona_data, str):
        persona_json = safe_json(persona_data)
    else:
        persona_json = persona_data if isinstance(persona_data, dict) else {}
        
    user_name = "there"
    if persona_json and isinstance(persona_json, dict):
        user_name = persona_json.get("name", "there")
        
    weather_text = result["weather"]
    plan_text = result["plan"]
    local_text = result.get("local_insights")
    plan_day_str = result.get("date")
    fixed_notes = result.get("commitments")

    meta_line = " | ".join(
        filter(
            None,
            [
                f"🗓️ Plan date: {plan_day_str}" if plan_day_str else None,
                f"📌 Commitment: {fixed_notes}" if fixed_notes else None,
            ],
        )
    )
    if meta_line:
        st.caption(meta_line)

    info_col1, info_col2 = st.columns(2)

    with info_col1:
        st.markdown("### 👤 Persona Snapshot")
        if persona_json:
            st.json(persona_json)
        else:
            st.write(result["persona"])

    with info_col2:
        st.markdown("### 🌦 Weather Insights")
        st.write(weather_text)

    if local_text:
        st.markdown("### 📍 Local Events & Venues")
        st.write(local_text)

    st.markdown("### Your Day Planner Assistant")
    st.markdown(plan_text)

    if st.session_state.get("last_status_log"):
        with st.expander("See how the agents collaborated"):
            for entry in st.session_state["last_status_log"]:
                st.write(entry)

    # --- EMAIL SECTION ---
    st.markdown("---")
    st.subheader("📧 Share this plan")
    
    # No more UI input for credentials, just a send button
    if st.button("Send Plan to Mail"):
        with st.spinner("Sending email..."):
            # Construct the email body
            full_body = f"""
            Hi {user_name},

            Here is your custom day plan for {plan_day_str}:

            {plan_text}

            ---
            Weather:
            {weather_text}
            """
            
            recipient = st.session_state.get("latest_inputs", {}).get("user_data", {}).get("email", "test@example.com")
            status = send_email_report(
                recipient,
                f"Your Day Plan for {plan_day_str}",
                full_body
            )
            
            if "successfully" in status:
                st.success(f"Sent to {recipient}!")
            else:
                st.error(status)

    # --- FEEDBACK SECTION ---
    st.markdown("---")
    st.subheader("Need me to tweak the plan?")
    with st.form("feedback_form", clear_on_submit=True):
        feedback = st.text_area(
            "Tell me what to change (e.g., 'swap the afternoon to a movie', 'skip the gym')",
        )
        regen = st.form_submit_button("Regenerate with feedback")

    if regen:
        if not feedback.strip():
            st.warning("Please describe what you'd like to change before I try again.")
        else:
            payload = st.session_state.get("last_payload") or st.session_state.get("latest_inputs")
            if not payload:
                st.error("I couldn't find your previous inputs. Please run the planner again.")
            else:
                run_plan(
                    payload["user_data"],
                    payload["plan_date"],
                    payload.get("commitments"),
                    adjustments=feedback.strip(),
                    status_panel=st.container(),
                )
