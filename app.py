import streamlit as st
import google.generativeai as genai
import os
import json
import re
from datetime import datetime
from dotenv import load_dotenv
import socket
import time

# --- INITIAL SETUP ---
load_dotenv()
try:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
except (AttributeError, ValueError):
    st.error(
        "⚠️ Google API Key not found or invalid. Please check your .env file.", icon="🔥"
    )
    st.stop()

DATA_DIR = "data"
GEMS_DIR = "gems"
UPLOADS_DIR = "uploads"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(GEMS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

AVAILABLE_MODELS = {
    "Gemini 2.5 Pro": "models/gemini-2.5-pro",
    "Gemini 2.5 Flash": "models/gemini-2.5-flash",
    "Gemini 1.5 Pro": "models/gemini-1.5-pro-latest",
    "Gemini 1.5 Flash": "models/gemini-1.5-flash-latest",
}

# A list of models known to NOT support grounding
# We will use this to disable the toggle in the UI.
GROUNDING_UNSUPPORTED_MODELS = ["models/gemini-2.5-pro", "models/gemini-2.5-flash"]


def load_gems():
    gems = {}
    if not os.path.exists(GEMS_DIR):
        return gems
    for filename in os.listdir(GEMS_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(GEMS_DIR, filename)
            try:
                with open(filepath, "r") as f:
                    gem_data = json.load(f)
                    gem_key = os.path.splitext(filename)[0]
                    if "name" in gem_data and "prompt" in gem_data:
                        gems[gem_key] = gem_data
            except (json.JSONDecodeError, IOError):
                pass
    return gems


GEMS = load_gems()
if not GEMS:
    st.error(f"No valid gem files found in the '{GEMS_DIR}' directory.", icon="🔥")
    st.stop()


@st.cache_data
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def get_model(model_name, grounding_enabled):
    tools = ["google_search_retrieval"] if grounding_enabled else None
    return genai.GenerativeModel(model_name=model_name, tools=tools)


def sanitize_filename(name):
    return re.sub(r"[^\w\s.-]", "", name).strip().replace(" ", "_")


def get_chat_title(chat_data):
    for message in chat_data["messages"]:
        if message["role"] == "user":
            return message["content"][:40] + "..."
    return GEMS[chat_data.get("gem_key", "default")]["name"]


def load_chats():
    chat_files = sorted(
        [
            os.path.join(DATA_DIR, f)
            for f in os.listdir(DATA_DIR)
            if f.endswith(".json")
        ],
        key=os.path.getmtime,
        reverse=True,
    )
    chats = {}
    for filepath in chat_files:
        try:
            with open(filepath, "r") as f:
                chat_data = json.load(f)
                chat_id = os.path.basename(filepath)
                chats[chat_id] = chat_data
        except (json.JSONDecodeError, KeyError):
            pass
    return chats


def save_chat(chat_id, chat_data):
    filepath = os.path.join(DATA_DIR, chat_id)
    with open(filepath, "w") as f:
        json.dump(chat_data, f, indent=4)


# --- SESSION STATE INITIALIZATION ---
if "chats" not in st.session_state:
    st.session_state.chats = load_chats()
if "view" not in st.session_state:
    st.session_state.view = "new_chat"
if "active_chat_id" not in st.session_state:
    st.session_state.active_chat_id = None
if "search_query" not in st.session_state:
    st.session_state.search_query = ""
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []
if "save_uploads" not in st.session_state:
    st.session_state.save_uploads = False
if "params_checked" not in st.session_state:
    query_params = st.query_params
    if "gem" in query_params:
        gem_from_url = query_params["gem"]
        if gem_from_url in GEMS:
            st.session_state.view = "new_chat"
            st.session_state.preselected_gem = gem_from_url
    st.session_state.params_checked = True

# --- SIDEBAR UI ---
with st.sidebar:
    st.title("💎 Gemini Chats")
    st.write("Manage your conversations here.")
    if st.button("➕ New Chat", use_container_width=True):
        st.session_state.view = "new_chat"
        st.session_state.active_chat_id = None
        st.session_state.search_query = ""
        st.session_state.uploaded_files = []
        st.rerun()
    st.header("Conversations")
    st.session_state.search_query = st.text_input(
        "Search chats...",
        value=st.session_state.search_query,
        placeholder="Search content of all chats...",
    )
    filtered_chats = {}
    if st.session_state.search_query:
        query_lower = st.session_state.search_query.lower()
        for chat_id, chat_data in st.session_state.chats.items():
            for message in chat_data.get("messages", []):
                if query_lower in message.get("content", "").lower():
                    filtered_chats[chat_id] = chat_data
                    break
    else:
        filtered_chats = st.session_state.chats
    if not filtered_chats:
        st.caption("No chats found.")
    else:
        chat_id_list = list(filtered_chats.keys())
        if st.session_state.active_chat_id in chat_id_list:
            default_index = chat_id_list.index(st.session_state.active_chat_id)
        else:
            default_index = None
        selected_chat_id = st.radio(
            "Select a chat:",
            options=chat_id_list,
            format_func=lambda cid: get_chat_title(filtered_chats[cid]),
            label_visibility="collapsed",
            index=default_index,
            key=f"radio_{len(chat_id_list)}_{st.session_state.search_query}",
        )
        if selected_chat_id and selected_chat_id != st.session_state.active_chat_id:
            st.session_state.active_chat_id = selected_chat_id
            st.session_state.view = "chat"
            st.session_state.uploaded_files = []
            st.rerun()
    st.markdown("---")
    if st.session_state.view == "chat" and st.session_state.active_chat_id:
        if st.button("🗑️ Delete Current Chat", use_container_width=True):
            chat_to_delete = st.session_state.active_chat_id
            del st.session_state.chats[chat_to_delete]
            os.remove(os.path.join(DATA_DIR, chat_to_delete))
            st.session_state.active_chat_id = None
            st.session_state.view = "new_chat"
            st.session_state.search_query = ""
            st.session_state.uploaded_files = []
            st.rerun()
    st.markdown("---")
    st.header("Settings")
    st.session_state.save_uploads = st.toggle(
        "Save Uploads to Disk",
        value=st.session_state.save_uploads,
        help="If enabled, all uploaded files will be saved to the ./uploads folder.",
    )


def file_uploader_and_prompt_area():
    st.session_state.uploaded_files = st.file_uploader(
        "Upload files or drag and drop here",
        accept_multiple_files=True,
        key=f"file_uploader_{st.session_state.view}_{st.session_state.active_chat_id}",
    )
    if st.session_state.uploaded_files:
        with st.expander("Attached Files"):
            for f in st.session_state.uploaded_files:
                st.write(f.name)
    return st.chat_input("Ask Gemini anything...")


def stream_and_display_response(prompt, chat_session):
    content_parts = []
    if st.session_state.uploaded_files:
        for uploaded_file in st.session_state.uploaded_files:
            if st.session_state.save_uploads:
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                save_path = os.path.join(
                    UPLOADS_DIR, f"{timestamp}_{sanitize_filename(uploaded_file.name)}"
                )
                with open(save_path, "wb") as f:
                    f.write(uploaded_file.getvalue())
            content_parts.append(
                {"mime_type": uploaded_file.type, "data": uploaded_file.getvalue()}
            )
    content_parts.append(prompt)
    with st.chat_message("assistant"):
        placeholder = st.empty()
        thinking_html = """<style>@keyframes blink { 50% { opacity: 0; } } .blinking-dot { animation: blink 1s step-start 0s infinite; } </style><div class="blinking-dot">...</div>"""
        placeholder.markdown(thinking_html, unsafe_allow_html=True)
    try:
        response_stream = chat_session.send_message(content_parts, stream=True)
        full_response = ""
        first_chunk = True
        for chunk in response_stream:
            if chunk.text:
                if first_chunk:
                    placeholder.empty()
                    first_chunk = False
                full_response += chunk.text
                placeholder.markdown(full_response + "▌")
        placeholder.markdown(full_response)
    except Exception as e:
        full_response = f"An error occurred: {e}"
        placeholder.error(full_response)
    st.session_state.uploaded_files = []
    return full_response


# --- MAIN CHAT INTERFACE ---
if st.session_state.view == "new_chat":
    st.title("✨ Start a New Conversation")
    st.caption("Select your settings below, attach files, and send your first message.")
    st.subheader("1. Choose Persona (Gem)")
    gem_keys = sorted(GEMS.keys())
    preselected_key = st.session_state.get("preselected_gem", "default")
    try:
        default_gem_index = gem_keys.index(preselected_key)
    except ValueError:
        default_gem_index = 0
    selected_gem_key = st.selectbox(
        "Choose your Gem:",
        options=gem_keys,
        index=default_gem_index,
        format_func=lambda key: GEMS[key]["name"],
        label_visibility="collapsed",
    )
    if "preselected_gem" in st.session_state:
        del st.session_state["preselected_gem"]
    st.write("---")
    if st.button(f"🔗 Generate Bookmark Link", use_container_width=True):
        st.session_state.show_bookmark_url = True
    if st.session_state.get("show_bookmark_url", False):
        local_ip = get_local_ip()
        port = st.get_option("server.port")
        bookmark_url = f"http://{local_ip}:{port}?gem={selected_gem_key}"
        st.caption("Copy the full network URL below:")
        st.code(bookmark_url, language=None)
    st.write("---")

    st.subheader("2. Configure Model")
    col1, col2 = st.columns(2)
    with col1:
        selected_model_name = st.selectbox(
            "Select a Model:", options=list(AVAILABLE_MODELS.keys())
        )
        model_name_for_api = AVAILABLE_MODELS[selected_model_name]
    with col2:
        # This block now intelligently disables the toggle
        grounding_is_disabled = model_name_for_api in GROUNDING_UNSUPPORTED_MODELS

        use_grounding = st.toggle(
            "Ground with Google Search",
            value=False,
            disabled=grounding_is_disabled,  # The key change is here
            help="Enable the model to use Google Search. Not supported by all models.",
        )
        if grounding_is_disabled:
            st.caption("Not supported for this model.")

    if prompt := file_uploader_and_prompt_area():
        st.session_state.show_bookmark_url = False
        gem = GEMS[selected_gem_key]
        model_instance = get_model(model_name_for_api, use_grounding)
        chat_session = model_instance.start_chat(
            history=[
                {"role": "user", "parts": [gem["prompt"]]},
                {"role": "model", "parts": ["Understood. I'm ready."]},
            ]
        )
        with st.chat_message("user"):
            st.markdown(prompt)
        model_response = stream_and_display_response(prompt, chat_session)
        serializable_history = [
            {"role": msg.role, "parts": [part.text for part in msg.parts]}
            for msg in chat_session.history
        ]
        new_chat_data = {
            "gem_key": selected_gem_key,
            "model_name": model_name_for_api,
            "grounding_enabled": use_grounding,
            "api_history": serializable_history,
            "messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": model_response},
            ],
        }
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename_prompt = sanitize_filename(prompt)[:50]
        new_chat_id = f"{timestamp}-{filename_prompt}.json"
        save_chat(new_chat_id, new_chat_data)
        st.session_state.chats = load_chats()
        st.session_state.active_chat_id = new_chat_id
        st.session_state.view = "chat"
        st.session_state.search_query = ""
        st.rerun()

elif st.session_state.active_chat_id:
    if st.session_state.active_chat_id not in st.session_state.chats:
        st.session_state.active_chat_id = None
        st.session_state.view = "new_chat"
        st.rerun()
    active_chat_id = st.session_state.active_chat_id
    active_chat_data = st.session_state.chats[active_chat_id]
    chat_model_name = active_chat_data["model_name"]
    chat_grounding = active_chat_data["grounding_enabled"]
    gem_key = active_chat_data.get("gem_key", "default")
    display_model_name = next(
        (
            name
            for name, api_name in AVAILABLE_MODELS.items()
            if api_name == chat_model_name
        ),
        "Unknown Model",
    )
    st.title(f"Chat: {get_chat_title(active_chat_data)}")
    st.caption(
        f"**Gem:** {GEMS[gem_key]['name']} | **Model:** {display_model_name} | **Grounding:** {'On' if chat_grounding else 'Off'}"
    )
    model_instance = get_model(chat_model_name, chat_grounding)
    chat_session = model_instance.start_chat(history=active_chat_data["api_history"])
    for message in active_chat_data["messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    if prompt := file_uploader_and_prompt_area():
        with st.chat_message("user"):
            st.markdown(prompt)
        model_response = stream_and_display_response(prompt, chat_session)
        serializable_history = [
            {"role": msg.role, "parts": [part.text for part in msg.parts]}
            for msg in chat_session.history
        ]
        active_chat_data["api_history"] = serializable_history
        active_chat_data["messages"].append({"role": "user", "content": prompt})
        active_chat_data["messages"].append(
            {"role": "assistant", "content": model_response}
        )
        save_chat(active_chat_id, active_chat_data)
        st.rerun()
else:
    st.title("Welcome to Gemini Chats!")
    st.caption("Create a new chat from the sidebar to get started.")
