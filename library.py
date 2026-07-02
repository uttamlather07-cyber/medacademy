"""
library.py
PDF/document library, organized by Subject -> Chapter (using the same
NEET_CHAPTERS list from chapters.py that the quiz topic picker uses, so
both features stay in sync).

Files are stored in Supabase Storage (see storage.py) — persistent across
Streamlit Cloud restarts/redeploys, unlike local disk. Only metadata
(storage_path/name/size/subject/chapter) is stored in the database.

INLINE READING:
Students (and admin) can read files without leaving the site, via a
popup-style dialog (st.dialog — Streamlit's closest equivalent to a
browser modal; it overlays the current page rather than opening a new
window/tab).
  - PDF: embedded directly in the dialog via a base64 <iframe>, the same
    reliable pattern chat.py already uses for inline images.
  - TXT: rendered as plain text in the dialog.
  - DOCX/PPTX: browsers cannot render these natively and there is no
    dependable in-app viewer for them here, so these stay download-only
    (per explicit decision — see README "Library" section). The "Read"
    button is simply not shown for these types; Download always is.
"""

import base64
import time
import uuid

import streamlit as st

from chapters import NEET_CHAPTERS, SUBJECTS, get_chapters
from database import save_db
from storage import upload_bytes, download_bytes, delete_file

ALLOWED_LIBRARY_TYPES = ["pdf", "docx", "doc", "pptx", "txt"]
MAX_LIBRARY_FILE_MB = 20

# Types that can be reliably rendered inline in-browser without a download.
INLINE_READABLE_TYPES = {"pdf", "txt"}


def _human_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes/1024:.1f} KB"
    return f"{num_bytes/(1024*1024):.1f} MB"


def add_library_file(db, uploaded_file, subject: str, chapter: str, uploaded_by: str):
    """Uploads a file to Supabase Storage and records it in db['library']."""
    ext = uploaded_file.name.split(".")[-1].lower()
    storage_path = upload_bytes(uploaded_file.getbuffer(), ext, folder="library")

    entry = {
        "id": uuid.uuid4().hex,
        "storage_path": storage_path,
        "file_name": uploaded_file.name,
        "file_size": _human_size(uploaded_file.size),
        "ext": ext,
        "subject": subject,
        "chapter": chapter,
        "uploaded_by": uploaded_by,
        "uploaded_at": time.time(),
    }
    db.setdefault("library", []).append(entry)
    save_db(db)
    return entry


def delete_library_file(db, file_id: str):
    """Removes a file from storage and from db['library']. Used by both
    admin (any file) and, if ever extended, a per-uploader check could be
    added here — currently any admin can delete any library file, matching
    how chat moderation already works (admin has full moderation
    authority)."""
    entry = next((f for f in db.get("library", []) if f["id"] == file_id), None)
    if entry:
        delete_file(entry.get("storage_path"))
    db["library"] = [f for f in db.get("library", []) if f["id"] != file_id]
    save_db(db)


def get_files_for(db, subject: str, chapter: str = None) -> list:
    files = [f for f in db.get("library", []) if f["subject"] == subject]
    if chapter:
        files = [f for f in files if f["chapter"] == chapter]
    return sorted(files, key=lambda f: -f["uploaded_at"])


FILE_ICONS = {"pdf": "📕", "docx": "📘", "doc": "📘", "pptx": "📙", "txt": "📄"}


@st.dialog("📖 Reader", width="large")
def _render_reader_dialog(entry: dict):
    """Popup dialog that renders a file inline. Only called for PDF/TXT —
    see INLINE_READABLE_TYPES."""
    st.markdown(f"#### {entry['file_name']}")
    st.caption(f"{entry['subject']} · {entry['chapter']}")

    file_bytes = download_bytes(entry.get("storage_path"))
    if file_bytes is None:
        st.error("This file is no longer available on the server.")
        return

    if entry["ext"] == "pdf":
        b64 = base64.b64encode(file_bytes).decode()
        st.markdown(
            f"<iframe src='data:application/pdf;base64,{b64}' "
            f"width='100%' height='600' style='border:none; border-radius:8px;'>"
            f"</iframe>",
            unsafe_allow_html=True,
        )
    elif entry["ext"] == "txt":
        content = file_bytes.decode(errors="replace")
        st.text_area("File contents", value=content, height=500, disabled=True, label_visibility="collapsed")

    st.divider()
    st.download_button(
        "⬇️ Download this file",
        data=file_bytes,
        file_name=entry["file_name"],
        key=f"dialog_dl_{entry['id']}",
    )


def render_library_browser(db, current_user: str, allow_delete: bool = False):
    """Shared browse/read/download UI used by both admin and student dashboards."""
    subject = st.selectbox("Subject", SUBJECTS, key="lib_subject_select")
    chapter = st.selectbox("Chapter", ["All Chapters"] + get_chapters(subject), key="lib_chapter_select")
    chapter_filter = None if chapter == "All Chapters" else chapter

    files = get_files_for(db, subject, chapter_filter)

    if not files:
        st.caption("📭 No files uploaded yet for this selection.")
        return

    for entry in files:
        icon = FILE_ICONS.get(entry["ext"], "📎")
        can_read_inline = entry["ext"] in INLINE_READABLE_TYPES

        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([4, 1, 1, 1])
            with c1:
                st.markdown(f"**{icon} {entry['file_name']}**")
                st.caption(f"{entry['chapter']} · {entry['file_size']} · uploaded by {entry['uploaded_by'].capitalize()}")
            with c2:
                if can_read_inline:
                    if st.button("📖 Read", key=f"lib_read_{entry['id']}"):
                        _render_reader_dialog(entry)
                else:
                    st.caption("Preview not available for this file type")
            with c3:
                file_bytes = download_bytes(entry.get("storage_path"))
                if file_bytes is not None:
                    st.download_button(
                        "⬇️ Download",
                        data=file_bytes,
                        file_name=entry["file_name"],
                        key=f"lib_dl_{entry['id']}",
                    )
                else:
                    st.caption("⚠️ File unavailable")
            with c4:
                if allow_delete:
                    if st.button("🗑️ Delete", key=f"lib_del_{entry['id']}"):
                        delete_library_file(db, entry["id"])
                        st.rerun()


def render_library_uploader(db, uploaded_by: str):
    """Admin-only upload form."""
    subject = st.selectbox("Subject", SUBJECTS, key="lib_upload_subject")
    chapter = st.selectbox("Chapter", get_chapters(subject), key="lib_upload_chapter")
    uploaded = st.file_uploader(
        "Choose a file",
        type=ALLOWED_LIBRARY_TYPES,
        key="lib_uploader",
    )
    if uploaded is not None:
        if uploaded.size > MAX_LIBRARY_FILE_MB * 1024 * 1024:
            st.error(f"File too large. Max size is {MAX_LIBRARY_FILE_MB} MB.")
        else:
            if st.button("📤 Add to Library", type="primary"):
                add_library_file(db, uploaded, subject, chapter, uploaded_by)
                st.success(f"Added to {subject} → {chapter}")
                st.rerun()
