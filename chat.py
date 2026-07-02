"""
chat.py
Chat rendering + file/image upload handling for the live class chat.

Files are saved to disk under UPLOAD_DIR with a unique name; only the
path/name/size are stored in database.json so the JSON file stays small.
"""

import os
import time
import uuid
import html as html_lib
from datetime import datetime, timezone, timedelta

import streamlit as st

from config import UPLOAD_DIR, MAX_FILE_SIZE_MB, ALLOWED_ALL_TYPES, ALLOWED_IMAGE_TYPES, CHAT_HISTORY_LIMIT
from database import save_db

IST = timezone(timedelta(hours=5, minutes=30))


def _format_ist(unix_time: float) -> str:
    """Formats a unix timestamp in IST (UTC+5:30), regardless of the
    server's local timezone (Streamlit Cloud runs in UTC, which is why
    times were showing several hours off before this fix)."""
    return datetime.fromtimestamp(unix_time, tz=IST).strftime("%I:%M %p")


FILE_ICONS = {
    "pdf": "📕", "docx": "📘", "doc": "📘", "txt": "📄", "pptx": "📙",
    "xlsx": "📗", "zip": "🗜️", "csv": "📊",
}


def ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def has_unread_messages(db, username: str) -> bool:
    """True if there are chat messages the user hasn't opened the Staff
    Room tab to see yet. Compares total message count against the count
    stored at the moment they last viewed the chat tab."""
    total = len(db.get("chat", []))
    user = db.get("users", {}).get(username, {})
    seen = user.get("last_seen_chat_count", 0)
    return total > seen


def unread_message_count(db, username: str) -> int:
    total = len(db.get("chat", []))
    user = db.get("users", {}).get(username, {})
    seen = user.get("last_seen_chat_count", 0)
    return max(0, total - seen)


def mark_chat_seen(db, username: str):
    """Call this when the user is actively viewing the Staff Room tab, so
    the unread badge clears for them."""
    if username in db.get("users", {}):
        db["users"][username]["last_seen_chat_count"] = len(db.get("chat", []))
        save_db(db)


def _human_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes/1024:.1f} KB"
    return f"{num_bytes/(1024*1024):.1f} MB"


def save_uploaded_file(uploaded_file) -> dict:
    """Saves a Streamlit UploadedFile to disk, returns metadata dict."""
    ensure_upload_dir()
    ext = uploaded_file.name.split(".")[-1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    dest_path = os.path.join(UPLOAD_DIR, unique_name)
    with open(dest_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    is_image = ext in ALLOWED_IMAGE_TYPES
    return {
        "type": "image" if is_image else "file",
        "file_path": dest_path,
        "file_name": uploaded_file.name,
        "file_size": _human_size(uploaded_file.size),
        "ext": ext,
    }


def append_message(db, sender: str, text: str = "", attachment: dict = None):
    msg = {
        "id": uuid.uuid4().hex,
        "sender": sender,
        "msg": text,
        "time": time.time(),
        "type": "text",
        "file_path": None,
        "file_name": None,
    }
    if attachment:
        msg["type"] = attachment["type"]
        msg["file_path"] = attachment["file_path"]
        msg["file_name"] = attachment["file_name"]
        msg["file_size"] = attachment.get("file_size", "")
    db["chat"].append(msg)
    save_db(db)


def render_chat_messages(messages, current_user):
    """Renders WhatsApp-style bubbles, including images and file attachments."""
    if not messages:
        st.markdown(
            "<div class='typing-hint'>No messages yet — say hello to the class.</div>",
            unsafe_allow_html=True,
        )
        return

    for msg in messages[-CHAT_HISTORY_LIMIT:]:
        is_admin = msg["sender"] == "admin"
        is_me = msg["sender"] == current_user

        row_class = "me" if is_me else "other"
        if is_admin:
            bubble_class = "admin"
        elif is_me:
            bubble_class = "student-me"
        else:
            bubble_class = "student-other"

        sender_label = "Dr. Admin" if is_admin else msg["sender"].capitalize()
        safe_text = html_lib.escape(msg.get("msg", ""))
        time_str = _format_ist(msg.get("time", time.time()))

        body_html = f"<div class='chat-text'>{safe_text}</div>" if safe_text else ""

        # Attachment rendering
        attachment_html = ""
        if msg.get("type") == "image" and msg.get("file_path") and os.path.exists(msg["file_path"]):
            # Streamlit can't inline arbitrary disk images via markdown reliably across
            # environments, so we base64-embed small chat images directly.
            import base64
            with open(msg["file_path"], "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            ext = msg["file_path"].split(".")[-1]
            attachment_html = (
                f"<div class='chat-image-wrap'>"
                f"<img src='data:image/{ext};base64,{b64}' />"
                f"</div>"
            )
        elif msg.get("type") == "file" and msg.get("file_path") and os.path.exists(msg["file_path"]):
            icon = FILE_ICONS.get(msg.get("file_path", "").split(".")[-1], "📎")
            fname = html_lib.escape(msg.get("file_name", "file"))
            fsize = msg.get("file_size", "")
            attachment_html = (
                f"<div class='chat-file-chip'>"
                f"<span class='chat-file-icon'>{icon}</span>"
                f"<div>"
                f"<div class='chat-file-name'>{fname}</div>"
                f"<div class='chat-file-meta'>{fsize}</div>"
                f"</div>"
                f"</div>"
            )

        bubble_html = (
            f"<div class='chat-row {row_class}'>"
            f"<div class='chat-bubble {bubble_class}'>"
            f"<div class='chat-sender'>{sender_label}</div>"
            f"{body_html}"
            f"{attachment_html}"
            f"<div class='chat-time'>{time_str}</div>"
            f"</div>"
            f"</div>"
        )
        st.markdown(bubble_html, unsafe_allow_html=True)

    # Download buttons for file attachments (rendered separately since markdown
    # links to local disk paths don't trigger downloads in the browser)
    file_msgs = [m for m in messages[-CHAT_HISTORY_LIMIT:] if m.get("type") == "file" and m.get("file_path") and os.path.exists(m["file_path"])]
    if file_msgs:
        with st.expander("📎 Download shared files"):
            for m in file_msgs:
                with open(m["file_path"], "rb") as f:
                    st.download_button(
                        label=f"⬇️ {m['file_name']} ({m.get('file_size','')})",
                        data=f.read(),
                        file_name=m["file_name"],
                        key=f"dl_{m['id']}",
                    )


def render_chat_composer(db, current_user, is_blocked: bool, key_prefix: str, is_admin: bool = False):
    """Text input + file/image uploader, WhatsApp-style, in one row.

    Chat can be globally disabled by the admin (db['chat_enabled'] = False).
    Admin can still post while it's off (e.g. to post a final note before
    closing the room); students cannot. A per-user `is_blocked` flag is
    checked independently and takes precedence either way.
    """
    if is_blocked:
        st.error("🚫 Your messaging privileges have been revoked by the Chief Medical Officer.")
        return

    if not db.get("chat_enabled", True) and not is_admin:
        st.info("🔒 The Chief Medical Officer has paused chat for now. Check back shortly.")
        return

    with st.expander("📎 Attach an image or file", expanded=False):
        uploaded = st.file_uploader(
            "Choose a file",
            type=ALLOWED_ALL_TYPES,
            key=f"{key_prefix}_uploader",
            label_visibility="collapsed",
        )
        if uploaded is not None:
            if uploaded.size > MAX_FILE_SIZE_MB * 1024 * 1024:
                st.error(f"File too large. Max size is {MAX_FILE_SIZE_MB} MB.")
            else:
                caption = st.text_input("Add a caption (optional)", key=f"{key_prefix}_caption")
                if st.button("Send attachment", key=f"{key_prefix}_send_file", type="primary"):
                    attachment = save_uploaded_file(uploaded)
                    append_message(db, current_user, text=caption, attachment=attachment)
                    st.rerun()

    text_msg = st.chat_input("Message the class...", key=f"{key_prefix}_text_input")
    if text_msg:
        append_message(db, current_user, text=text_msg)
        st.rerun()
