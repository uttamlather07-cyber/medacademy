"""
storage.py
Centralized Supabase Storage helpers for file uploads (chat attachments
and library documents). Both chat.py and library.py use these functions
instead of writing to local disk — Streamlit Cloud's local disk is wiped
on restarts/redeploys, but Supabase Storage is a persistent, separate
service, so files uploaded here survive exactly like the database rows
in database.py do.

Uses the same Supabase client/credentials already configured for
database.py (SUPABASE_URL / SUPABASE_KEY in secrets.toml).

Bucket setup (one-time, done via the Supabase dashboard):
  Storage -> New bucket -> name it "class-files" -> keep it Private.
"""

import uuid

import streamlit as st

from database import _get_client

BUCKET = "class-files"


def upload_bytes(file_bytes: bytes, ext: str, folder: str = "") -> str:
    """Uploads raw bytes to the bucket under a random unique name.
    Returns the storage_path to save in database.json (via db['library']
    or db['chat']) — NOT the file bytes themselves and NOT a public URL.
    `folder` is an optional subfolder, e.g. 'chat' or 'library'."""
    client = _get_client()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    storage_path = f"{folder}/{unique_name}" if folder else unique_name
    client.storage.from_(BUCKET).upload(
        storage_path,
        file_bytes,
        file_options={"content-type": "application/octet-stream"},
    )
    return storage_path


@st.cache_data(ttl=300, show_spinner=False)
def download_bytes(storage_path: str) -> bytes | None:
    """Downloads a file's raw bytes from the bucket. Returns None if the
    file doesn't exist or the download fails, so callers can show a
    friendly 'no longer available' message instead of crashing.

    Cached for 5 minutes per storage_path: chat/library re-render on every
    autorefresh tick (every few seconds), and file contents never change
    for a given storage_path (uploads always get a fresh random name), so
    re-fetching identical bytes from the network on every tick would be
    wasteful. Deleting a file (delete_file) clears its cache entry so a
    deleted file doesn't keep appearing to work."""
    if not storage_path:
        return None
    client = _get_client()
    try:
        return client.storage.from_(BUCKET).download(storage_path)
    except Exception:
        return None


def delete_file(storage_path: str):
    """Deletes a file from the bucket and clears its cached bytes. Safe to
    call even if it's already gone — Supabase Storage won't error loudly
    on a missing path here."""
    if not storage_path:
        return
    client = _get_client()
    try:
        client.storage.from_(BUCKET).remove([storage_path])
    except Exception:
        pass
    download_bytes.clear(storage_path)
