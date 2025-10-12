import re
import google.generativeai as genai
from .config import GEMINI_API_KEY


def translate_text_with_gemini(text, logger, is_retry=False):
    genai.configure(api_key=GEMINI_API_KEY)

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

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        response = model.generate_content(prompt, safety_settings=safety_settings)

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
                f"Translation finished for an unusual reason: {finish_reason.name}. Treating as failure.",
                level="WARNING",
            )
            return {"status": "FAILED", "text": None}

    except Exception as e:
        error_message = str(e).lower()
        if (
            "quota" in error_message
            or "token" in error_message
            or "resource has been exhausted" in error_message
        ):
            logger(
                f"API token/quota limit likely exceeded (input too large). {e}",
                level="ERROR",
            )
            return {"status": "TOKEN_LIMIT_EXCEEDED", "text": None}
        else:
            logger(f"An error occurred with the Gemini API: {e}", level="ERROR")
            return {"status": "FAILED", "text": None}


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
