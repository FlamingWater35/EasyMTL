import threading
from ebooklib import epub, ITEM_DOCUMENT
import dearpygui.dearpygui as dpg

from .utils import log_message
from .epub_handler import extract_content_from_chapters, create_translated_epub
from .translator import translate_text_with_gemini, parse_translated_text


def run_translation_process(epub_path, num_chapters):
    try:
        log_message("--- Starting Translation Process ---")
        book = epub.read_epub(epub_path)
        all_chapters = list(book.get_items_of_type(ITEM_DOCUMENT))
        chapters_to_translate_items = all_chapters[:num_chapters]
        log_message(
            f"Selected {len(chapters_to_translate_items)} of {len(all_chapters)} chapters."
        )

        content, data = extract_content_from_chapters(
            chapters_to_translate_items, log_message
        )
        if not content:
            log_message("ERROR: Failed to extract text.")
            return

        translated_text = translate_text_with_gemini(content, log_message)
        if translated_text:
            parsed = parse_translated_text(translated_text)
            log_message(f"Parsed {len(parsed)} translated chapters from API response.")
            create_translated_epub(
                epub_path, parsed, chapters_to_translate_items, data, log_message
            )
        else:
            log_message("Translation failed. The process was halted.")

    except Exception as e:
        log_message(f"An unexpected error occurred in the translation thread: {e}")
    finally:
        log_message("--- Process Finished ---")
        if dpg.is_dearpygui_running():
            dpg.configure_item("start_button", enabled=True)


def start_translation_thread():
    epub_path = dpg.get_value("app_state_filepath")
    total_chapters = dpg.get_value("app_state_total_chapters")
    chapters_to_translate = dpg.get_value("chapter_count_input")

    if not (1 <= chapters_to_translate <= total_chapters):
        log_message(f"ERROR: Chapter count must be between 1 and {total_chapters}.")
        return

    dpg.configure_item("start_button", enabled=False)
    thread = threading.Thread(
        target=run_translation_process, args=(epub_path, chapters_to_translate)
    )
    thread.start()
