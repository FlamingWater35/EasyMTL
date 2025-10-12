import google.generativeai as genai
from .config import GEMINI_API_KEY


def translate_text_with_gemini(text, logger, is_retry=False):
    genai.configure(api_key=GEMINI_API_KEY)
    base_prompt = f"""Translate the following novel chapters into English.
If a chapter has a title, enclose the translated title in double asterisks, like this: **Chapter Title**. Always keep the chapter number in the title.
Preserve any placeholder tags like `[IMAGE_PLACEHOLDER_N]` exactly as they appear in your translated output. Do not translate the content inside these tags.
Keep the content of each chapter separate.
Preserve the chapter separation markers ('---') at the end of each chapter's text.

---
{text}
---
"""
    if is_retry:
        retry_note = "IMPORTANT: Your previous response was not formatted correctly. Please pay close attention to the instructions and ensure you return the exact same number of chapters separated by '---' as you received.\n\n"
        prompt = retry_note + base_prompt
    else:
        prompt = base_prompt

    if is_retry:
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

        if finish_reason.name == "MAX_TOKENS":
            logger(
                "The model's output was truncated because it reached the maximum token limit.",
                level="WARNING",
            )
            return {"status": "OUTPUT_TRUNCATED", "text": response.text}
        elif finish_reason.name == "STOP":
            logger("Translation received successfully.", level="SUCCESS")
            return {"status": "SUCCESS", "text": response.text}
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
    parsed_chapters = []
    raw_chunks = translated_text.split("---")

    for chunk in raw_chunks:
        clean_chunk = chunk.strip()
        if clean_chunk:
            parsed_chapters.append(clean_chunk)

    return parsed_chapters
