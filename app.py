import json

import streamlit as st
from google import genai
from google.genai import types
from twilio.rest import Client as TwilioClient

from prompts import SUMMARY_REQUEST_PROMPT, SYSTEM_PROMPT, WELCOME_MESSAGE_TEMPLATE


MODEL_NAME = "gemini-3.5-flash"

st.set_page_config(
    page_title="MacroSnap",
    page_icon="🥗"
)


# -----------------------------
# Secrets
# -----------------------------

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
TWILIO_ACCOUNT_SID = st.secrets["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = st.secrets["TWILIO_AUTH_TOKEN"]
TWILIO_WHATSAPP_FROM = st.secrets["TWILIO_WHATSAPP_FROM"]
TWILIO_CONTENT_SID = st.secrets["TWILIO_CONTENT_SID"]


# -----------------------------
# Cached clients
# -----------------------------

@st.cache_resource
def get_gemini_client():
    return genai.Client(api_key=GEMINI_API_KEY)


@st.cache_resource
def get_twilio_client():
    return TwilioClient(
        TWILIO_ACCOUNT_SID,
        TWILIO_AUTH_TOKEN
    )


gemini_client = get_gemini_client()
twilio_client = get_twilio_client()


# -----------------------------
# Message functions
# -----------------------------

def render_message(message):
    with st.chat_message(message["role"]):
        if message["kind"] == "text":
            st.write(message["content"])

        elif message["kind"] == "image":
            st.image(message["content"])


def add_message(role, kind, content):
    st.session_state.messages.append(
        {
            "role": role,
            "kind": kind,
            "content": content
        }
    )

    render_message(st.session_state.messages[-1])


# -----------------------------
# Gemini
# -----------------------------

def ask_gemini(parts):
    try:
        response = st.session_state.chat.send_message(parts)
        return response.text

    except Exception as error:
        return f"Sorry, something went wrong: {error}"


# -----------------------------
# WhatsApp helpers
# -----------------------------

def clean_whatsapp_text(text):
    if not text:
        return "No nutrition summary available."

    text = " ".join(text.split())

    if len(text) > 1500:
        return text[:1500] + "..."

    return text


def send_whatsapp(to_number, user_name, summary):
    try:
        message = twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{to_number}",
            body=f"Hi {user_name}! 🥗\n\nMacroSnap Nutrition Summary:\n\n{clean_whatsapp_text(summary)}"
        )

        return True, message.sid

    except Exception as error:
        return False, str(error)


# -----------------------------
# Onboarding
# -----------------------------

if "onboarded" not in st.session_state:

    st.title("🥗 MacroSnap")

    st.caption(
        "Snap it. Track it. Text yourself the results."
    )

    with st.form("onboarding_form"):

        name = st.text_input("Your name")

        whatsapp_number = st.text_input(
            "WhatsApp number (with country code)",
            placeholder="+91XXXXXXXXXX",
            help="This is the number MacroSnap will text your summary to.",
        )

        submitted = st.form_submit_button(
            "Let's go 🚀"
        )

    if submitted:

        if not name.strip() or not whatsapp_number.strip():

            st.warning(
                "Please fill in both your name and WhatsApp number."
            )

        else:

            st.session_state.name = name.strip()

            st.session_state.whatsapp_number = (
                whatsapp_number.strip()
            )

            st.session_state.chat = gemini_client.chats.create(
                model=MODEL_NAME,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT
                ),
            )

            st.session_state.messages = []

            st.session_state.onboarded = True

            st.rerun()

    st.stop()


# -----------------------------
# Header
# -----------------------------

header_col, button_col = st.columns(
    [5, 2],
    vertical_alignment="center"
)


with header_col:

    st.title("🥗 MacroSnap")


with button_col:

    send_disabled = (
        len(st.session_state.messages) <= 2
    )

    if st.button(
        "📤 Send to WhatsApp",
        disabled=send_disabled,
        use_container_width=True
    ):

        with st.spinner(
            "Summarizing your day..."
        ):

            summary = ask_gemini(
                [SUMMARY_REQUEST_PROMPT]
            )

        success, info = send_whatsapp(
            st.session_state.whatsapp_number,
            st.session_state.name,
            summary
        )

        if success:

            st.success(
                "Sent! Check your WhatsApp 📲"
            )

        else:

            st.error(
                f"Couldn't send that: {info}"
            )


st.caption(
    f"Logged in as {st.session_state.name} - "
    f"updates go to {st.session_state.whatsapp_number}"
)


# -----------------------------
# Chat history
# -----------------------------

if not st.session_state.messages:

    add_message(
        "assistant",
        "text",
        WELCOME_MESSAGE_TEMPLATE.format(
            name=st.session_state.name
        )
    )

else:

    for message in st.session_state.messages:

        render_message(message)


# -----------------------------
# Chat input
# -----------------------------

user_input = st.chat_input(
    "Ask a question, or attach a photo of your meal",
    accept_file=True,
    file_type=["jpg", "jpeg", "png"],
)


if user_input:

    photo = (
        user_input.files[0]
        if user_input.files
        else None
    )

    text = user_input.text

    parts = []


    # Photo
    if photo is not None:

        photo_bytes = photo.getvalue()

        add_message(
            "user",
            "image",
            photo_bytes
        )

        parts.append(
            types.Part.from_bytes(
                data=photo_bytes,
                mime_type=photo.type
            )
        )


    # Text
    if text:

        add_message(
            "user",
            "text",
            text
        )

        parts.append(text)


    # Photo without text
    elif photo is not None:

        parts.append(
            "What is this meal? Give me the calories and macros."
        )


    # Ask Gemini
    with st.spinner(
        "Crunching the numbers..."
    ):

        answer = ask_gemini(parts)


    add_message(
        "assistant",
        "text",
        answer
    )
