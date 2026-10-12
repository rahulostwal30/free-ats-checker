"""Thin wrapper around the Google GenAI SDK (google-genai).

- Reads GEMINI_API_KEY, GEMINI_MODEL and GEMINI_THINKING_LEVEL from .env.
- Tries the preferred model first, then the fallback models in order.
- Moves on to the next model when the current one is retired (404), over its
  rate/quota limit (429), or overloaded (500/503). Every model has its own
  quota, so a fallback is a real alternative when one of them is full.
- Retries a busy model once before giving up on it.
- Stops at once on errors another model cannot fix (bad key, permissions).
- Raises GeminiError with a short message that is safe to show on the website.
  The technical detail is written to the log file.
"""

import os
import re
import time
from typing import List, Optional

from google import genai
from google.genai import types

from src.logger import logging

# Preferred model first (GEMINI_MODEL from .env, if set), then these in order.
DEFAULT_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
]

VALID_THINKING_LEVELS = {"MINIMAL", "LOW", "MEDIUM", "HIGH"}
DEFAULT_THINKING_LEVEL = "LOW"

REQUEST_TIMEOUT_MS = 120_000  # 2 minutes per request
MAX_BUSY_RETRIES = 2          # extra tries on the same model for 500/503
BUSY_CODES = {500, 503}
SWITCH_MODEL_CODES = {404, 429, 500, 503}  # this model cannot serve now

SAFETY_SETTINGS = [
    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_ONLY_HIGH"),
    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_ONLY_HIGH"),
    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_ONLY_HIGH"),
    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_ONLY_HIGH"),
]

# Messages shown to the user on the website.
MSG_NO_KEY = "GEMINI_API_KEY is missing. Add it to the .env file in the project root and restart the server."
MSG_BAD_KEY = (
    "Gemini rejected the API key. Check GEMINI_API_KEY in the .env file "
    "(create a new key in Google AI Studio if needed) and restart the server."
)
MSG_PERMISSION = (
    "Gemini refused this request. The API key's Google project may lack access "
    "to the Gemini API or billing is not set up. Check it in Google AI Studio."
)
MSG_QUOTA = (
    "Gemini rate or quota limit reached for every model in the list. Wait a minute "
    "and try again. Check your usage at https://aistudio.google.com/rate-limit"
)
MSG_BUSY = "Gemini is busy right now. Please try again in a few seconds."
MSG_NO_MODEL = (
    "None of the configured Gemini models are available. Set GEMINI_MODEL in .env "
    "to a current model from https://ai.google.dev/gemini-api/docs/models"
)
MSG_EMPTY = (
    "Gemini returned no text. The content may have been blocked by its safety "
    "filters. Try a different file or wording."
)
MSG_TIMEOUT = f"The AI service did not respond within {REQUEST_TIMEOUT_MS // 1000} seconds. Please try again."

_client: Optional[genai.Client] = None
_thinking_rung: dict = {}  # model name -> index of the thinking setting that worked


class GeminiError(Exception):
    """An error whose user_message is safe to show on the website."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


class _SwitchModel(Exception):
    """Internal: this model cannot serve the request right now."""

    def __init__(self, code: Optional[int], error: Exception):
        super().__init__(str(error))
        self.code = code


def _fail(user_message: str, detail: str) -> GeminiError:
    logging.error(f"Gemini error: {detail}")
    return GeminiError(user_message)


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise _fail(MSG_NO_KEY, "GEMINI_API_KEY not set")
        _client = genai.Client(api_key=api_key)
        logging.info("Google GenAI client initialized.")
    return _client


def _model_chain() -> List[str]:
    preferred = os.getenv("GEMINI_MODEL", "").strip()
    models: List[str] = []
    for name in ([preferred] if preferred else []) + DEFAULT_MODELS:
        if name and name not in models:
            models.append(name)
    return models


def _requested_thinking_level() -> str:
    raw = os.getenv("GEMINI_THINKING_LEVEL", "").strip().upper()
    if raw in VALID_THINKING_LEVELS:
        return raw
    if raw:
        logging.warning(f"Unknown GEMINI_THINKING_LEVEL '{raw}', using {DEFAULT_THINKING_LEVEL}.")
    return DEFAULT_THINKING_LEVEL


def _thinking_levels_for(model_name: str) -> List[Optional[str]]:
    """Thinking settings to try, in order. Gemini 3 models take thinking_level.
    Other models get no thinking setting, so their default is used."""
    if not model_name.startswith("gemini-3"):
        return [None]
    # Requested level, then LOW (accepted by all Gemini 3 models), then no setting.
    return list(dict.fromkeys([_requested_thinking_level(), "LOW", None]))


def _build_config(thinking_level: Optional[str]) -> types.GenerateContentConfig:
    kwargs = {
        "safety_settings": SAFETY_SETTINGS,
        "http_options": types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    }
    if thinking_level:
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level)
    return types.GenerateContentConfig(**kwargs)


def _status_code(error: Exception) -> Optional[int]:
    code = getattr(error, "code", None)
    if isinstance(code, int):
        return code
    text = str(error)
    match = re.match(r"\s*(\d{3})\b", text) or re.search(r"['\"]?code['\"]?\s*[:=]\s*(\d{3})", text)
    return int(match.group(1)) if match else None


def _is_timeout(error: Exception) -> bool:
    text = f"{type(error).__name__} {error}".lower()
    return "timeout" in text or "timed out" in text


def _message_for_code(code: Optional[int], message: str) -> str:
    lowered = message.lower()
    if code == 401 or (code == 400 and "api key" in lowered):
        return MSG_BAD_KEY
    if code == 403:
        return MSG_PERMISSION
    suffix = f" (HTTP {code})" if code else ""
    return f"Gemini could not process this request{suffix}. Check the server log for details."


def _generate_with_model(client: genai.Client, model_name: str, prompt: str) -> str:
    levels = _thinking_levels_for(model_name)
    rung = _thinking_rung.get(model_name, 0)
    busy_retries = 0

    while True:
        level = levels[rung]
        started = time.perf_counter()
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=_build_config(level),
            )
        except Exception as error:
            code = _status_code(error)
            message = str(error)

            # This model rejected the thinking setting: try the next one, and
            # remember it so later requests skip the rejected setting.
            if code == 400 and "thinking" in message.lower() and rung + 1 < len(levels):
                rung += 1
                _thinking_rung[model_name] = rung
                logging.warning(f"{model_name} rejected thinking level {level}; trying {levels[rung]}.")
                continue

            if code in BUSY_CODES and busy_retries < MAX_BUSY_RETRIES:
                busy_retries += 1
                wait = 2 ** busy_retries  # 2s, then 4s
                logging.warning(f"{model_name} is busy (HTTP {code}); retrying in {wait}s.")
                time.sleep(wait)
                continue

            if code in SWITCH_MODEL_CODES:
                raise _SwitchModel(code, error) from error

            if code is None and _is_timeout(error):
                raise _fail(MSG_TIMEOUT, f"{model_name} timed out: {message}") from error

            raise _fail(_message_for_code(code, message), f"{model_name} HTTP {code}: {message}") from error

        text = (response.text or "").strip()
        if not text:
            raise _fail(MSG_EMPTY, f"{model_name} returned no text (possibly safety-blocked).")

        elapsed = time.perf_counter() - started
        logging.info(f"Gemini response received from {model_name} (thinking={level}) in {elapsed:.1f}s.")
        return text


def generate_text(prompt: str) -> str:
    """Send a prompt to Gemini and return the response text."""
    client = _get_client()
    failures: List[str] = []
    codes: List[Optional[int]] = []

    for model_name in _model_chain():
        try:
            return _generate_with_model(client, model_name, prompt)
        except _SwitchModel as switch:
            codes.append(switch.code)
            failures.append(f"{model_name} (HTTP {switch.code})")
            logging.warning(f"{model_name} unavailable (HTTP {switch.code}). Trying the next model.")

    if 429 in codes:
        user_message = MSG_QUOTA
    elif codes and all(code == 404 for code in codes):
        user_message = MSG_NO_MODEL
    else:
        user_message = MSG_BUSY
    raise _fail(user_message, "No Gemini model could handle the request: " + ", ".join(failures))