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


_MODEL_LIMIT_CACHE = {}


def get_model_output_limit(logger):
    model_name = os.getenv("GEMINI_MODEL_NAME", DEFAULT_MODEL)

    if model_name in _MODEL_LIMIT_CACHE:
        return _MODEL_LIMIT_CACHE[model_name]

    client, error = get_client()
    if error:
        logger(f"Cannot get model limit: {error}", level="ERROR")
        return 8192

    try:
        full_model_name = (
            f"models/{model_name}"
            if not model_name.startswith("models/")
            else model_name
        )

        logger(f"Fetching details for model: {model_name}...")
        model_info = client.models.get(model=full_model_name)

        if hasattr(model_info, "output_token_limit"):
            limit = model_info.output_token_limit
            logger(
                f"Model '{model_name}' has an output token limit of {limit}.",
                level="SUCCESS",
            )
            _MODEL_LIMIT_CACHE[model_name] = limit
            return limit
        else:
            logger(
                f"Model '{model_name}' did not return an output token limit. Using default.",
                level="WARNING",
            )
            _MODEL_LIMIT_CACHE[model_name] = 8192
            return 8192

    except errors.APIError as e:
        logger(
            f"API Error fetching model details: {e.message}. Using default limit.",
            level="ERROR",
        )
        _MODEL_LIMIT_CACHE[model_name] = 8192
        return 8192


def list_models(logger):
    client, error = get_client()
    if error:
        logger(f"Could not list models: {error}", level="ERROR")
        return [DEFAULT_MODEL]

    try:
        all_models = [
            m.name
            for m in client.models.list()
            if "generateContent" in m.supported_actions
        ]
        filtered_models = []

        for name in all_models:
            lower_name = name.lower()

            if "image" in lower_name or "computer-use" in lower_name:
                continue

            if "gemma" in lower_name:
                filtered_models.append(name)
                continue

            if "gemini" in lower_name:
                match = re.search(r"gemini-(\d+(?:\.\d+)?)", lower_name)
                if match:
                    try:
                        version_val = float(match.group(1))
                        if version_val >= 2.5:
                            filtered_models.append(name)
                    except ValueError:
                        continue

        if not filtered_models:
            logger(
                "No models found matching criteria (Gemini >= 2.5 or Gemma). Showing default.",
                level="WARNING",
            )
            return [DEFAULT_MODEL]

        def get_version_val(model_name):
            match = re.search(r"(\d+(?:\.\d+)?)", model_name)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    pass
            return 0.0

        filtered_models.sort(
            key=lambda x: (
                "gemini" not in x.lower(),
                -get_version_val(x),
                "pro" not in x.lower(),
                x,
            )
        )
        return filtered_models
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
Follow these rules precisely:
1.  Preserve the `[CHAPTER_ID::...]` tag at the beginning of each chapter.
2.  If a chapter has a title, enclose the translated title in double asterisks, like this: **Chapter Title**.
3.  If the chapter has a number, preserve it in the title like this: **Chapter 1: The Beginning**.
4.  Maintain paragraph structure. Do not merge paragraphs.
5.  Preserve any placeholder tags like `[IMAGE_PLACEHOLDER_N]` exactly as they appear.
6.  **Maintain markdown formatting:** If the input text uses *italics* or **bold**, preserve that formatting in the translation.
7.  Keep the content of each chapter separate, preserving the '---' markers.

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

        if not response.candidates:
            logger("API returned no candidates (empty response).", level="WARNING")
            return {"status": "FAILED", "text": None}

        finish_reason = response.candidates[0].finish_reason
        raw_text = response.text

        if not raw_text:
            logger("API returned success status but no text content.", level="WARNING")
            return {"status": "FAILED", "text": None}

        final_text_to_parse = raw_text

        if finish_reason.name == "MAX_TOKENS":
            logger(
                "Output truncated by model. Verifying and trimming to the last complete chapter.",
                level="WARNING",
            )
            id_pattern = re.compile(r"\[CHAPTER_ID::([^]]+)\]")
            matches = list(id_pattern.finditer(raw_text))

            if len(matches) > 1:
                last_match_start = matches[-1].start()
                final_text_to_parse = raw_text[:last_match_start]
            elif not matches:
                final_text_to_parse = ""

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

        if "429" in error_message or "quota" in error_message or "resource exhausted" in error_message:
            logger(f"Google API Quota hit: {e.message}", level="WARNING")
            return {"status": "QUOTA_EXCEEDED", "text": None}

        elif "400" in error_message or "token" in error_message or "too large" in error_message:
            logger(f"Input text is too large for this model: {e.message}", level="ERROR")
            return {"status": "TOKEN_LIMIT_EXCEEDED", "text": None}

        else:
            logger(f"An API error occurred: {e.message}", level="ERROR")
            return {"status": "FAILED", "text": None}
    except Exception as e:
        logger(f"An unexpected error occurred: {e}", level="ERROR")
        return {"status": "FAILED", "text": None}


# Unused (needed for precise token calculation)
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
    if not translated_text:
        return {}

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


def estimate_tokens_fast(text):
    if not text:
        return 0

    length = len(text)

    sample = text[:500]
    non_ascii_count = sum(1 for c in sample if ord(c) > 127)

    is_mostly_non_english = non_ascii_count > (len(sample) * 0.2)

    if is_mostly_non_english:
        return int(length * 1.3)
    else:
        return int(length / 2.5)
