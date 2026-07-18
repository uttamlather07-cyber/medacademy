"""
ai_providers.py
Multi-key, multi-provider AI client rotation for question generation.

WHY THIS EXISTS:
The old quiz.py called Groq directly with a single hardcoded key and no
fallback. If that one key hit a rate limit, was exhausted, or Groq had a
blip, EVERY question generation call would fail outright (st.stop()) for
every student, mid-quiz. With multiple Groq keys AND Gemini as a second
provider, a single bad/limited key never takes down question generation —
we just move to the next key/provider in the pool.

SECRETS FORMAT (.streamlit/secrets.toml):
    GROQ_API_KEYS = ["gsk_xxx", "gsk_yyy", "gsk_zzz"]
    GEMINI_API_KEYS = ["AIzaxxx", "AIzayyy"]
Singular GROQ_API_KEY / GEMINI_API_KEY (one string) also works, for
backward compatibility with the old single-key setup — it's just wrapped
into a one-item list.

ROTATION STRATEGY:
Keys are shuffled once per process (not per call) so that with many
concurrent Streamlit sessions, they don't all hammer key #1 first, then
all fail over to key #2 at the same moment, etc. On each generation
attempt, the NEXT client in rotation is tried — a rate-limited or dead key
just gets skipped over, it doesn't block anything.
"""

import json
import random
import threading

import streamlit as st


class AllProvidersExhaustedError(Exception):
    """Every configured key, across every provider, failed. Distinct from
    a single bad key so callers can show an accurate, specific error
    instead of a generic failure message."""
    pass


class _ProviderClient:
    """One (provider, key) pair, wrapped behind a single .complete(prompt)
    -> dict interface so the rest of the app never needs to know which
    provider actually answered."""

    def __init__(self, provider: str, api_key: str):
        self.provider = provider
        self.api_key = api_key

    def complete(self, prompt: str) -> dict:
        if self.provider == "groq":
            return self._complete_groq(prompt)
        elif self.provider == "gemini":
            return self._complete_gemini(prompt)
        raise ValueError(f"Unknown provider: {self.provider}")

    def _complete_groq(self, prompt: str) -> dict:
        from groq import Groq
        client = Groq(api_key=self.api_key)
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            response_format={"type": "json_object"},
            timeout=20,
        )
        return json.loads(response.choices[0].message.content)

    def _complete_gemini(self, prompt: str) -> dict:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=self.api_key, http_options=types.HttpOptions(timeout=20000))
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                response_mime_type="application/json",
            ),
        )
        return json.loads(response.text)


def _read_key_list(*secret_names) -> list:
    """Reads the first secret name that exists, as either a list of keys
    or a single key string (wrapped into a one-item list)."""
    for name in secret_names:
        value = st.secrets.get(name)
        if not value:
            continue
        if isinstance(value, str):
            return [value]
        return list(value)
    return []


@st.cache_resource
def _build_client_pool() -> list:
    """Built once per process (cached), then shuffled fresh — see module
    docstring for why shuffling matters under concurrent load. Cast to a
    list (not shuffled in place on the cached object) so repeated calls to
    get_client_pool() below don't mutate the cached shared list."""
    groq_keys = _read_key_list("GROQ_API_KEYS", "GROQ_API_KEY")
    gemini_keys = _read_key_list("GEMINI_API_KEYS", "GEMINI_API_KEY")

    pool = (
        [_ProviderClient("groq", k) for k in groq_keys]
        + [_ProviderClient("gemini", k) for k in gemini_keys]
    )
    return pool


_shuffle_lock = threading.Lock()


def get_client_pool() -> list:
    """Returns a freshly-shuffled COPY of the client pool. Fresh shuffle
    per call (cheap — this is just reordering a short list of objects, no
    new connections) so concurrent Streamlit sessions calling this at the
    same moment don't all try the same first key in lockstep."""
    pool = list(_build_client_pool())
    if not pool:
        return pool
    with _shuffle_lock:
        random.shuffle(pool)
    return pool


def has_any_keys_configured() -> bool:
    return len(_build_client_pool()) > 0


def complete_with_rotation(prompt: str, max_attempts: int = None) -> tuple:
    """
    Tries the prompt against clients in rotation until one succeeds.
    Returns (result_dict, provider_name_used).
    Raises AllProvidersExhaustedError if every attempt fails.

    max_attempts: defaults to trying every configured client once. Pass a
    higher number to retry some clients more than once (useful for
    generation-shape validation retries where the caller wants several
    total tries even with few keys configured).
    """
    pool = get_client_pool()
    if not pool:
        raise AllProvidersExhaustedError(
            "No AI provider keys configured. Add GROQ_API_KEYS and/or GEMINI_API_KEYS "
            "to .streamlit/secrets.toml (a list of keys, or a single key string)."
        )

    attempts = max_attempts or len(pool)
    last_error = None

    for i in range(attempts):
        client = pool[i % len(pool)]
        try:
            result = client.complete(prompt)
            return result, client.provider
        except Exception as e:
            last_error = f"{client.provider}: {e}"
            continue

    raise AllProvidersExhaustedError(
        f"All {len(pool)} configured AI key(s) failed. Last error: {last_error}"
    )
