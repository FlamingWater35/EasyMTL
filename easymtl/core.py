import os
import threading
import time
from ebooklib import epub, ITEM_DOCUMENT
import dearpygui.dearpygui as dpg

from .config import CHAPTER_CHUNK_SIZE
from .utils import log_message
from .epub_handler import extract_content_from_chapters, create_translated_epub
from .translator import translate_text_with_gemini, parse_translated_text


def run_translation_process(epub_path, start_chapter, end_chapter):
    try:
        if dpg.is_dearpygui_running():
            dpg.set_value("progress_bar", 0.0)
        log_message("--- Starting Translation Process ---")
        book = epub.read_epub(epub_path)
        all_chapters = list(book.get_items_of_type(ITEM_DOCUMENT))
        chapters_to_translate_items = all_chapters[start_chapter - 1 : end_chapter]
        log_message(
            f"Selected chapters {start_chapter} to {end_chapter} ({len(chapters_to_translate_items)} total)."
        )

        chunks = [
            chapters_to_translate_items[i : i + CHAPTER_CHUNK_SIZE]
            for i in range(0, len(chapters_to_translate_items), CHAPTER_CHUNK_SIZE)
        ]
        log_message(
            f"Dividing the task into an initial {len(chunks)} chunks of up to {CHAPTER_CHUNK_SIZE} chapters each."
        )

        translation_map = {}
        all_extraction_data = []

        total_chapters_to_process = len(chapters_to_translate_items)
        chapters_processed = 0

        while chunks:
            chunk_items = chunks.pop(0)
            log_message(f"--- Processing Chunk (Size: {len(chunk_items)}) ---")

            chunk_content, chunk_extraction_data = extract_content_from_chapters(
                chunk_items, log_message
            )
            if not chunk_content:
                log_message(
                    f"Failed to extract text from chunk. Skipping.", level="WARNING"
                )
                continue

            chunk_translation_map = None
            response_status = None

            for attempt in range(2):
                is_retry = attempt > 0
                response = translate_text_with_gemini(
                    chunk_content, log_message, is_retry=is_retry
                )
                response_status = response["status"]

                if response_status in ["SUCCESS", "OUTPUT_TRUNCATED"]:
                    chunk_translation_map = parse_translated_text(response["text"])
                    break
                elif response_status == "TOKEN_LIMIT_EXCEEDED":
                    break
                elif response_status == "FAILED":
                    log_message(f"API call failed. Retrying...", level="ERROR")
                time.sleep(1)

            if chunk_translation_map:
                translation_map.update(chunk_translation_map)
                all_extraction_data.extend(chunk_extraction_data)

                chapters_processed += len(chunk_translation_map)

                if response_status == "OUTPUT_TRUNCATED":
                    log_message(
                        f"Chunk was truncated. Identifying and re-queuing missing chapters.",
                        level="WARNING",
                    )

                    translated_ids = set(chunk_translation_map.keys())
                    untranslated_items = [
                        item
                        for item in chunk_items
                        if item.get_name() not in translated_ids
                    ]

                    if untranslated_items:
                        log_message(
                            f"Re-queuing a new chunk with {len(untranslated_items)} remaining chapters.",
                            level="INFO",
                        )
                        chunks.insert(0, untranslated_items)
                    else:
                        log_message(
                            "All chapters in the truncated chunk were processed.",
                            level="SUCCESS",
                        )

            elif response_status == "TOKEN_LIMIT_EXCEEDED":
                log_message(
                    "Halting translation due to input token limit.", level="ERROR"
                )
                break

            else:
                log_message(
                    f"Translation failed for this chunk after all retries. Skipping.",
                    level="ERROR",
                )
                chapters_processed += len(chunk_items)

            progress = (
                chapters_processed / total_chapters_to_process
                if total_chapters_to_process > 0
                else 0
            )
            if dpg.is_dearpygui_running():
                dpg.set_value("progress_bar", progress)

            time.sleep(1)

        log_message("--- All chunks processed. Building the final EPUB file. ---")
        if translation_map:
            create_translated_epub(
                epub_path,
                translation_map,
                chapters_to_translate_items,
                all_extraction_data,
                log_message,
            )
        else:
            log_message(
                "Translation failed for all chunks. No EPUB file will be created.",
                level="ERROR",
            )

    except Exception as e:
        log_message(f"An unexpected error occurred: {e}", level="ERROR")
    finally:
        log_message("--- Process Finished ---")
        if dpg.is_dearpygui_running():
            dpg.configure_item("start_button", enabled=True)


def start_translation_thread():
    if not os.getenv("GEMINI_API_KEY"):
        log_message("ERROR: Gemini API Key is not set. Please set it via the Settings menu.", level="ERROR")
        dpg.show_item("api_key_modal")
        return

    epub_path = dpg.get_value("app_state_filepath")
    total_chapters = dpg.get_value("app_state_total_chapters")
    start_chapter = dpg.get_value("start_chapter_input")
    end_chapter = dpg.get_value("end_chapter_input")
    if start_chapter > end_chapter:
        log_message(
            "Start chapter cannot be greater than the end chapter.", level="ERROR"
        )
        return
    if not (
        1 <= start_chapter <= total_chapters and 1 <= end_chapter <= total_chapters
    ):
        log_message(
            f"Chapter range must be between 1 and {total_chapters}.", level="ERROR"
        )
        return
    dpg.configure_item("start_button", enabled=False)
    thread = threading.Thread(
        target=run_translation_process, args=(epub_path, start_chapter, end_chapter)
    )
    thread.start()
