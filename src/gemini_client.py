"""Thin wrapper around the Google GenAI SDK (google-genai).

- Reads GEMINI_API_KEY (and optional GEMINI_MODEL / GEMINI_THINKING_LEVEL) from .env.
- Uses a low thinking level by default: resume and report writing does not need
  deep reasoning, and "low" is much faster than the model's "medium" default.
- Tries the preferred model first, then falls back through a known-good list
  when a model is retired (HTTP 404).
- Retries briefly on transient server errors (429 / 500 / 503).
- Gives up after REQUEST_TIMEOUT_MS so a stuck request cannot hang forever.
"""

import os
import re
import time
from typing import List, Optional

from google import genai
from google.genai import types

from src.logger import logging

# Newest GA model first. Override with GEMINI_MODEL in .env if needed.
DEFAULT_MODELS = [
    "gemini-3.8-flash",
    "gemini-2.5-flash",
]

RETRYABLE_STATUS_CODES = {429, 500, 503}
MAX_ATTEMPTS = 2
REQUEST_TIMEOUT_MS = 120_000  # 2 minutes per request

SAFETY_SETTINGS = [
    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_ONLY_HIGH"),
    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_ONLY_HIGH"),
    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_ONLY_HIGH"),
    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_ONLY_HIGH"),
]

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is missing. Add it to the .env file in the project root and restart the server."
            )
        _client = genai.Client(api_key=api_key)
        logging.info("Google GenAI client initialized.")
    return _client


def _model_chain() -> List[str]:
    preferred = os.getenv("GEMINI_MODEL", "").strip()
    models = [preferred] if preferred else []
    for name in DEFAULT_MODELS:
        if name not in models:
            models.append(name)
    return models


def _thinking_level() -> str:
    return os.getenv("GEMINI_THINKING_LEVEL", "low").strip().lower() or "low"


def _build_config(with_thinking: bool) -> types.GenerateContentConfig:
    kwargs = {
        "safety_settings": SAFETY_SETTINGS,
        "http_options": types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    }
    if with_thinking:
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=_thinking_level())
    return types.GenerateContentConfig(**kwargs)


def _status_code(error: Exception) -> Optional[int]:
    code = getattr(error, "code", None)
    if isinstance(code, int):
        return code
    match = re.search(r"\b([45]\d\d)\b", str(error))
    return int(match.group(1)) if match else None


def _is_thinking_rejected(error: Exception) -> bool:
    return _status_code(error) == 400 and "thinking" in str(error).lower()


def _is_timeout(error: Exception) -> bool:
    text = f"{type(error).__name__} {error}".lower()
    return "timeout" in text or "timed out" in text


def generate_text(prompt: str) -> str:
    """Send a prompt to Gemini and return the response text."""
    client = _get_client()
    use_thinking = True
    last_error: Optional[Exception] = None

    for model_name in _model_chain():
        for attempt in range(1, MAX_ATTEMPTS + 1):
            config = _build_config(use_thinking)
            started = time.perf_counter()
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
                text = (response.text or "").strip()
                if not text:
                    raise ValueError(
                        "Gemini returned an empty response. The content may have been blocked by safety filters."
                    )
                elapsed = time.perf_counter() - started
                logging.info(f"Gemini response received from {model_name} in {elapsed:.1f}s.")
                return text
            except Exception as error:
                last_error = error
                code = _status_code(error)

                if use_thinking and _is_thinking_rejected(error):
                    logging.warning(f"{model_name} rejected the thinking setting; retrying without it.")
                    use_thinking = False
                    continue

                if code is None and _is_timeout(error):
                    logging.error(f"Gemini request to {model_name} timed out: {error}")
                    raise RuntimeError(
                        f"The AI service did not respond within {REQUEST_TIMEOUT_MS // 1000} seconds. Please try again."
                    ) from error

                if code == 404:
                    logging.warning(f"Model {model_name} is not available, trying the next model. {error}")
                    break

                if code in RETRYABLE_STATUS_CODES and attempt < MAX_ATTEMPTS:
                    logging.warning(f"Transient Gemini error {code} on {model_name} (attempt {attempt}). Retrying.")
                    time.sleep(2 * attempt)
                    continue

                raise

    raise RuntimeError(f"No Gemini model could handle this request. Last error: {last_error}")
