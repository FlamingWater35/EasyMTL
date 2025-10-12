import os
import threading
import time
from ebooklib import epub, ITEM_DOCUMENT
import dearpygui.dearpygui as dpg

from .config import DEFAULT_MODEL, TOKEN_SAFETY_MARGIN
from .utils import format_time, log_message
from .epub_handler import (
    create_cover_page_from_metadata,
    extract_content_from_chapters,
    create_translated_epub,
)
from .translator import (
    count_tokens,
    get_model_output_limit,
    list_models,
    translate_text_with_gemini,
    parse_translated_text,
)


def run_translation_process(epub_path, start_chapter, end_chapter):
    start_time = time.time()
    chapters_processed = 0
    total_chapters_to_process = 0
    try:
        if dpg.is_dearpygui_running():
            dpg.set_value("progress_bar", 0.0)
            dpg.configure_item("progress_bar", overlay="0/0 (0%)")
            dpg.set_value("elapsed_time_text", "Elapsed: 00:00")
            dpg.set_value("eta_time_text", "ETA: --:--")

        log_message("--- Starting Translation Process ---")
        book = epub.read_epub(epub_path)
        all_chapters = list(book.get_items_of_type(ITEM_DOCUMENT))
        chapters_to_translate_items = all_chapters[start_chapter - 1 : end_chapter]
        total_chapters_to_process = len(chapters_to_translate_items)
        log_message(
            f"Selected chapters {start_chapter} to {end_chapter} ({total_chapters_to_process} total)."
        )

        max_output_tokens = get_model_output_limit(log_message)
        safe_token_limit = max_output_tokens - TOKEN_SAFETY_MARGIN
        log_message(f"Using a safe input token limit of {safe_token_limit} per chunk.")

        log_message("Pre-processing chapters to count tokens...")
        chapter_data_list = []
        for item in chapters_to_translate_items:
            item_content, item_extraction_data = extract_content_from_chapters(
                [item], log_message, verbose=False
            )
            item_tokens = count_tokens(item_content)

            chapter_data_list.append(
                {
                    "item": item,
                    "content": item_content,
                    "tokens": item_tokens,
                    "extraction_data": item_extraction_data[0],
                }
            )
        log_message("Pre-processing complete.", level="SUCCESS")

        log_message(
            f"Building dynamic chunks with a token limit of {safe_token_limit}..."
        )
        chunks = []
        current_chunk_data = []
        current_chunk_tokens = 0
        for chapter_data in chapter_data_list:
            if current_chunk_data and (
                current_chunk_tokens + chapter_data["tokens"] > safe_token_limit
            ):
                chunks.append(current_chunk_data)
                current_chunk_data = []
                current_chunk_tokens = 0

            current_chunk_data.append(chapter_data)
            current_chunk_tokens += chapter_data["tokens"]

        if current_chunk_data:
            chunks.append(current_chunk_data)

        log_message(
            f"Dynamically created {len(chunks)} chunks based on token count.",
            level="SUCCESS",
        )

        translation_map = {}
        all_extraction_data = []

        while chunks:
            chunk_data = chunks.pop(0)
            chunk_items = [data["item"] for data in chunk_data]
            chunk_content = "".join([data["content"] for data in chunk_data])
            chunk_extraction_data = [data["extraction_data"] for data in chunk_data]

            log_message(f"--- Processing Chunk (Size: {len(chunk_items)} chapters) ---")

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
                        f"Chunk was truncated. Re-queuing missing chapters.",
                        level="WARNING",
                    )
                    translated_ids = set(chunk_translation_map.keys())

                    untranslated_data = [
                        data
                        for data in chunk_data
                        if data["item"].get_name() not in translated_ids
                    ]

                    if untranslated_data:
                        log_message(
                            f"Re-queuing a new chunk with {len(untranslated_data)} remaining chapters.",
                            level="INFO",
                        )
                        chunks.insert(0, untranslated_data)

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

            if dpg.is_dearpygui_running():
                elapsed_seconds = time.time() - start_time
                dpg.set_value(
                    "elapsed_time_text", f"Elapsed: {format_time(elapsed_seconds)}"
                )

                progress = (
                    chapters_processed / total_chapters_to_process
                    if total_chapters_to_process > 0
                    else 0
                )
                percent = int(progress * 100)
                overlay_text = (
                    f"{chapters_processed}/{total_chapters_to_process} ({percent}%)"
                )
                dpg.set_value("progress_bar", progress)
                dpg.configure_item("progress_bar", overlay=overlay_text)

                if chapters_processed > 0 and progress < 1.0:
                    time_per_chapter = elapsed_seconds / chapters_processed
                    remaining_chapters = total_chapters_to_process - chapters_processed
                    eta_seconds = time_per_chapter * remaining_chapters
                    dpg.set_value("eta_time_text", f"ETA: {format_time(eta_seconds)}")

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
            final_progress = (
                chapters_processed / total_chapters_to_process
                if total_chapters_to_process > 0
                else 0
            )
            final_percent = int(final_progress * 100)
            final_overlay = (
                f"{chapters_processed}/{total_chapters_to_process} ({final_percent}%)"
            )

            dpg.set_value("progress_bar", final_progress)
            dpg.configure_item("progress_bar", overlay=final_overlay)
            dpg.set_value("eta_time_text", "ETA: --:--")
            dpg.configure_item("start_button", enabled=True)


def start_translation_thread():
    if not os.getenv("GOOGLE_API_KEY"):
        log_message(
            "ERROR: API Key is not set. Please use Settings > Set API Key.",
            level="ERROR",
        )
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


def fetch_models_from_api():
    if not os.getenv("GOOGLE_API_KEY"):
        log_message("Cannot fetch models: API Key is not set.", level="WARNING")
        if dpg.is_dearpygui_running():
            dpg.configure_item("model_combo", items=[DEFAULT_MODEL])
            dpg.set_value("model_combo", DEFAULT_MODEL)
        return

    log_message("Fetching available models from the API...")
    if dpg.is_dearpygui_running():
        dpg.configure_item("model_combo", items=["Loading..."])
        dpg.set_value("model_combo", "Loading...")

    models = list_models(log_message)

    if dpg.is_dearpygui_running():
        dpg.configure_item("model_combo", items=models)
        current_model = os.getenv("GEMINI_MODEL_NAME", models[0])
        dpg.set_value("model_combo", current_model)
    log_message(f"Found {len(models)} available models.", level="SUCCESS")


def start_model_fetch_thread():
    thread = threading.Thread(target=fetch_models_from_api)
    thread.start()


def run_cover_creation_process(epub_path):
    try:
        if dpg.is_dearpygui_running():
            dpg.configure_item("cover_tool_button", enabled=False)

        create_cover_page_from_metadata(epub_path, log_message)

    except Exception as e:
        log_message(
            f"An unexpected error occurred in the cover creation thread: {e}",
            level="ERROR",
        )
    finally:
        log_message("--- Cover Process Finished ---")
        if dpg.is_dearpygui_running():
            dpg.configure_item("cover_tool_button", enabled=True)


def start_cover_creation_thread(epub_path):
    thread = threading.Thread(target=run_cover_creation_process, args=(epub_path,))
    thread.start()
