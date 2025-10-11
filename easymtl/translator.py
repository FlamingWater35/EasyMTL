import google.generativeai as genai
from .config import GEMINI_API_KEY


def translate_text_with_gemini(text, logger):
    genai.configure(api_key=GEMINI_API_KEY)
    prompt = f"""Translate the following novel chapters into English.
If a chapter has a title, enclose the translated title in double asterisks, like this: **Chapter Title**.
Preserve any placeholder tags like `[IMAGE_PLACEHOLDER_N]` exactly as they appear in your translated output. Do not translate the content inside these tags.
Keep the content of each chapter separate.
Preserve the chapter separation markers ('---') at the end of each chapter's text.

---
{text}
---
"""
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
        logger("Translation received.")
        return response.text
    except Exception as e:
        logger(f"ERROR: An error occurred with the Gemini API: {e}")
        return None


def parse_translated_text(translated_text):
    return [ch.strip() for ch in translated_text.split("---") if ch.strip()]
