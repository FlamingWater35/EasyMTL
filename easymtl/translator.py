import os
import re
from google import genai
from google.genai import types
from google.genai import errors

from .config import DEFAULT_MODEL

_CLIENT_INSTANCE = None
_CLIENT_API_KEY = None


def get_client():
    global _CLIENT_INSTANCE, _CLIENT_API_KEY

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None, "API Key not found in environment."

    if _CLIENT_INSTANCE is None or _CLIENT_API_KEY != api_key:
        try:
            _CLIENT_INSTANCE = genai.Client(api_key=api_key)
            _CLIENT_API_KEY = api_key
            return _CLIENT_INSTANCE, None
        except Exception as e:
            return None, f"Failed to create GenAI client: {e}"

    return _CLIENT_INSTANCE, None


def list_models(logger):
    client, error = get_client()
    if error:
        logger(f"Could not list models: {error}", level="ERROR")
        return [DEFAULT_MODEL]

    try:
        models = [
            m.name
            for m in client.models.list()
            if "generateContent" in m.supported_actions
        ]
        models.sort(key=lambda x: "pro" not in x)
        return models
    except errors.APIError as e:
        logger(f"API Error while listing models: {e.message}", level="ERROR")
        return [DEFAULT_MODEL]
    except Exception as e:
        logger(f"An unexpected error occurred while listing models: {e}", level="ERROR")
        return [DEFAULT_MODEL]


def translate_text_with_gemini(text, logger, is_retry=False):
    client, error = get_client()
    if error:
        logger(error, level="ERROR")
        return {"status": "FAILED", "text": None}

    prompt = f"""Translate the following novel chapters into English.
It is critical that you preserve the `[CHAPTER_ID::...]` tag at the beginning of each chapter. Do not translate it or remove it.
If a chapter has a title, enclose the translated title in double asterisks, like this: **Chapter Title**.
Preserve any placeholder tags like `[IMAGE_PLACEHOLDER_N]` exactly as they appear.
Keep the content of each chapter separate, preserving the '---' markers.

---
{text}
---
"""
    if is_retry:
        retry_note = "IMPORTANT: Your previous response was not formatted correctly. Please pay close attention to the instructions and ensure you return the exact same number of chapters separated by '---' as you received.\n\n"
        prompt = retry_note + prompt
        logger("Retrying translation with additional instructions...", level="WARNING")
    else:
        logger("Sending text to Gemini for translation. This may take a while...")

    safety_settings = [
        types.SafetySetting(
            category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"
        ),
        types.SafetySetting(
            category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"
        ),
        types.SafetySetting(
            category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"
        ),
        types.SafetySetting(
            category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"
        ),
    ]
    config = types.GenerateContentConfig(safety_settings=safety_settings)

    try:
        model_name = os.getenv("GEMINI_MODEL_NAME", DEFAULT_MODEL)

        response = client.models.generate_content(
            model=model_name, contents=prompt, config=config
        )

        finish_reason = response.candidates[0].finish_reason
        raw_text = response.text

        final_text_to_parse = raw_text

        if finish_reason.name == "MAX_TOKENS":
            logger(
                "Output truncated by model. Trimming to last complete chapter.",
                level="WARNING",
            )
            parts = raw_text.split("---")
            complete_parts = parts[:-1]
            final_text_to_parse = "---".join(complete_parts) + "---"
            return {"status": "OUTPUT_TRUNCATED", "text": final_text_to_parse}
        elif finish_reason.name == "STOP":
            logger("Translation received successfully.", level="SUCCESS")
            return {"status": "SUCCESS", "text": final_text_to_parse}
        else:
            logger(
                f"Translation finished for an unusual reason: {finish_reason.name}.",
                level="WARNING",
            )
            return {"status": "FAILED", "text": None}

    except errors.APIError as e:
        error_message = str(e.message).lower()
        if "quota" in error_message or "token" in error_message:
            logger(f"API token/quota limit likely exceeded. {e.message}", level="ERROR")
            return {"status": "TOKEN_LIMIT_EXCEEDED", "text": None}
        else:
            logger(f"An API error occurred: {e.message}", level="ERROR")
            return {"status": "FAILED", "text": None}
    except Exception as e:
        logger(f"An unexpected error occurred: {e}", level="ERROR")
        return {"status": "FAILED", "text": None}


def count_tokens(text):
    client, error = get_client()
    if error or not text:
        return 999999
    try:
        model_name = os.getenv("GEMINI_MODEL_NAME", DEFAULT_MODEL)
        response = client.models.count_tokens(model=model_name, contents=text)
        return response.total_tokens
    except Exception:
        return 999999


def parse_translated_text(translated_text):
    id_pattern = re.compile(r"\[CHAPTER_ID::([^]]+)\]")
    translation_map = {}
    raw_chunks = translated_text.split("---")

    for chunk in raw_chunks:
        clean_chunk = chunk.strip()
        if not clean_chunk:
            continue
        match = id_pattern.search(clean_chunk)
        if match:
            chapter_id = match.group(1)
            content = clean_chunk[match.end() :].strip()
            translation_map[chapter_id] = content
    return translation_map
