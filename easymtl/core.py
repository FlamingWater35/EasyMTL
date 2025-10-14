import os
import threading
import time
from ebooklib import epub, ITEM_DOCUMENT
import dearpygui.dearpygui as dpg

from .config import AVAILABLE_GEMMA_MODELS, TOKEN_LIMIT_PERCENTAGE, DEFAULT_MODEL
from .utils import (
    delete_local_model,
    format_time,
    get_reverse_model_map,
    log_message,
    scan_for_local_models,
)
from .epub_handler import (
    create_cover_page_from_metadata,
    extract_content_from_chapters,
    create_translated_epub,
)
from .translator import (
    count_tokens as count_tokens_cloud,
    get_model_output_limit,
    list_models,
    translate_text_with_gemini,
    parse_translated_text,
)
from .local_translator import (
    download_model_from_hub,
    translate_text_with_gemma,
)


def is_local_model(model_name):
    return model_name and model_name.endswith(".gguf")


def _update_elapsed_time_continuously(start_time, stop_event):
    while not stop_event.is_set():
        if dpg.is_dearpygui_running():
            elapsed_seconds = time.time() - start_time
            dpg.set_value(
                "elapsed_time_text", f"Elapsed: {format_time(elapsed_seconds)}"
            )

            current_eta_str = dpg.get_value("eta_time_text")
            if (
                current_eta_str
                and current_eta_str.startswith("ETA: ")
                and "--" not in current_eta_str
            ):
                time_part = current_eta_str.replace("ETA: ", "")
                try:
                    minutes, seconds = map(int, time_part.split(":"))
                    total_seconds = (minutes * 60) + seconds
                    if total_seconds > 0:
                        new_total_seconds = total_seconds - 1
                        dpg.set_value(
                            "eta_time_text", f"ETA: {format_time(new_total_seconds)}"
                        )
                except (ValueError, IndexError):
                    pass
        time.sleep(1)


def _process_with_local_model(chapters_to_translate, start_time, log_message):
    total_chapters_to_process = len(chapters_to_translate)
    chapters_processed = 0
    translation_map, all_extraction_data = {}, []

    log_message("Pre-processing all chapters for local translation...")
    chapter_data_list = []
    for item in chapters_to_translate:
        item_content, item_extraction_data = extract_content_from_chapters(
            [item], log_message, verbose=False
        )
        chapter_data_list.append(
            {
                "item": item,
                "content": item_content,
                "extraction_data": item_extraction_data[0],
            }
        )
    log_message("Pre-processing complete.", level="SUCCESS")

    for i, chapter_data in enumerate(chapter_data_list):
        log_message(f"--- Processing Chapter {i + 1}/{total_chapters_to_process} ---")
        response = translate_text_with_gemma(chapter_data["content"], log_message)

        if response["status"] == "SUCCESS" and response["text"]:
            translated_text = response["text"].strip()
            if translated_text:
                chapter_id = chapter_data["item"].get_name()
                translation_map[chapter_id] = translated_text
                all_extraction_data.append(chapter_data["extraction_data"])
            else:
                log_message(
                    f"Local model returned an empty string for chapter {i+1}. Skipping.",
                    level="WARNING",
                )
        else:
            log_message(
                f"Translation failed for chapter {i+1}. Skipping.", level="ERROR"
            )

        chapters_processed += 1

        if dpg.is_dearpygui_running():
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
                elapsed_seconds = time.time() - start_time
                time_per_chapter = elapsed_seconds / chapters_processed
                remaining_chapters = total_chapters_to_process - chapters_processed
                eta_seconds = time_per_chapter * remaining_chapters
                dpg.set_value("eta_time_text", f"ETA: {format_time(eta_seconds)}")

    return translation_map, all_extraction_data, chapters_processed


def _process_with_cloud_model(chapters_to_translate, start_time, log_message):
    total_chapters_to_process = len(chapters_to_translate)
    max_output_tokens = get_model_output_limit(log_message)
    safe_token_limit = int(max_output_tokens * TOKEN_LIMIT_PERCENTAGE)
    log_message(f"Using a safe input token limit of {safe_token_limit} per chunk.")

    log_message("Pre-processing chapters to count tokens...")
    chapter_data_list = []
    for i, item in enumerate(chapters_to_translate):
        item_content, item_extraction_data = extract_content_from_chapters(
            [item], log_message, verbose=False
        )
        chapter_data_list.append(
            {
                "item": item,
                "content": item_content,
                "tokens": 0,
                "extraction_data": item_extraction_data[0],
            }
        )
        if dpg.is_dearpygui_running():
            overlay_text = f"Analyzing {i + 1}/{total_chapters_to_process}..."
            dpg.configure_item("progress_bar", overlay=overlay_text)

    full_text_for_token_count = "".join([data["content"] for data in chapter_data_list])
    total_tokens = count_tokens_cloud(full_text_for_token_count)
    total_chars = len(full_text_for_token_count)
    if total_chars > 0:
        for data in chapter_data_list:
            char_proportion = len(data["content"]) / total_chars
            estimated_tokens = int(total_tokens * char_proportion)
            data["tokens"] = max(1, estimated_tokens)
    log_message("Pre-processing complete.", level="SUCCESS")

    log_message(f"Building dynamic chunks with a token limit of {safe_token_limit}...")
    chunks = []
    current_chunk_data, current_chunk_tokens = [], 0
    for chapter_data in chapter_data_list:
        if current_chunk_data and (
            current_chunk_tokens + chapter_data["tokens"] > safe_token_limit
        ):
            chunks.append(current_chunk_data)
            current_chunk_data, current_chunk_tokens = [], 0
        current_chunk_data.append(chapter_data)
        current_chunk_tokens += chapter_data["tokens"]
    if current_chunk_data:
        chunks.append(current_chunk_data)

    log_message(f"Created {len(chunks)} chunks for processing.", level="SUCCESS")

    translation_map, all_extraction_data = {}, []
    chapters_processed = 0

    while chunks:
        chunk_data = chunks.pop(0)
        chunk_items = [data["item"] for data in chunk_data]
        chunk_content = "".join([data["content"] for data in chunk_data])
        log_message(f"--- Processing Chunk (Size: {len(chunk_items)} chapters) ---")

        chunk_translation_map, response_status = None, None
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
            translated_ids = set(chunk_translation_map.keys())
            for data in chunk_data:
                if data["item"].get_name() in translated_ids:
                    all_extraction_data.append(data["extraction_data"])
            chapters_processed += len(translated_ids)
            untranslated_data = [
                data
                for data in chunk_data
                if data["item"].get_name() not in translated_ids
            ]
            if untranslated_data:
                if response_status == "OUTPUT_TRUNCATED":
                    log_message(
                        "Output truncated by model. Re-queuing missing chapters.",
                        level="WARNING",
                    )
                else:
                    log_message(
                        "Model response was incomplete. Re-queuing missing chapters.",
                        level="WARNING",
                    )
                log_message(
                    f"Re-queuing a new chunk with {len(untranslated_data)} remaining chapters.",
                    level="INFO",
                )
                chunks.insert(0, untranslated_data)
        elif response_status == "TOKEN_LIMIT_EXCEEDED":
            log_message("Halting translation due to input token limit.", level="ERROR")
            raise InterruptedError("TOKEN_LIMIT_EXCEEDED")
        else:
            log_message(
                f"Translation failed for a chunk of {len(chunk_data)} chapters. Splitting and re-queuing.",
                level="ERROR",
            )
            if len(chunk_data) > 1:
                mid_point = len(chunk_data) // 2
                first_half = chunk_data[:mid_point]
                second_half = chunk_data[mid_point:]
                chunks.insert(0, second_half)
                chunks.insert(0, first_half)
                log_message(
                    f"Split into two new chunks of size {len(first_half)} and {len(second_half)}."
                )
            else:
                log_message(
                    f"Unable to translate chapter {chunk_data[0]['item'].get_name()} after multiple attempts. Skipping.",
                    level="ERROR",
                )
                chapters_processed += 1

        if dpg.is_dearpygui_running():
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
                elapsed_seconds = time.time() - start_time
                time_per_chapter = elapsed_seconds / chapters_processed
                remaining_chapters = total_chapters_to_process - chapters_processed
                eta_seconds = time_per_chapter * remaining_chapters
                dpg.set_value("eta_time_text", f"ETA: {format_time(eta_seconds)}")
        time.sleep(1)

    return translation_map, all_extraction_data, chapters_processed


def run_translation_process(epub_path, start_chapter, end_chapter):
    start_time = time.time()
    chapters_processed = 0
    total_chapters_to_process = 0
    process_halted = False

    stop_event = threading.Event()
    timer_thread = threading.Thread(
        target=_update_elapsed_time_continuously, args=(start_time, stop_event)
    )
    timer_thread.start()

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

        model_name = os.getenv("GEMINI_MODEL_NAME", DEFAULT_MODEL)
        translation_map, all_extraction_data = {}, []

        if is_local_model(model_name):
            translation_map, all_extraction_data, chapters_processed = (
                _process_with_local_model(
                    chapters_to_translate_items, start_time, log_message
                )
            )
        else:
            try:
                translation_map, all_extraction_data, chapters_processed = (
                    _process_with_cloud_model(
                        chapters_to_translate_items, start_time, log_message
                    )
                )
            except InterruptedError:
                process_halted = True

        log_message(
            "--- All chapters/chunks processed. Building the final EPUB file. ---"
        )
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
                "Translation failed for all chapters. No EPUB file will be created.",
                level="ERROR",
            )

    except Exception as e:
        process_halted = True
        log_message(f"An unexpected error occurred: {e}", level="ERROR")
    finally:
        log_message("--- Process Finished ---")
        stop_event.set()
        if dpg.is_dearpygui_running():
            if not process_halted and total_chapters_to_process > 0:
                final_progress, final_chapters, final_percent = (
                    1.0,
                    total_chapters_to_process,
                    100,
                )
            else:
                final_progress = (
                    chapters_processed / total_chapters_to_process
                    if total_chapters_to_process > 0
                    else 0
                )
                final_chapters, final_percent = chapters_processed, int(
                    final_progress * 100
                )
            final_overlay = (
                f"{final_chapters}/{total_chapters_to_process} ({final_percent}%)"
            )
            dpg.set_value("progress_bar", final_progress)
            dpg.configure_item("progress_bar", overlay=final_overlay)
            dpg.set_value("eta_time_text", "ETA: --:--")
            dpg.configure_item("start_button", enabled=True)


def start_translation_thread():
    model_name = os.getenv("GEMINI_MODEL_NAME", DEFAULT_MODEL)
    if not is_local_model(model_name) and not os.getenv("GOOGLE_API_KEY"):
        log_message(
            "ERROR: API Key is not set. Please set it to use cloud models.",
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
        log_message("Cannot fetch cloud models: API Key is not set.", level="WARNING")
        if dpg.is_dearpygui_running():
            dpg.configure_item("model_combo", items=[DEFAULT_MODEL])
            dpg.set_value("model_combo", DEFAULT_MODEL)
        return

    log_message("Fetching available cloud models from the API...")
    if dpg.is_dearpygui_running():
        dpg.configure_item("model_combo", items=["Loading..."])
        dpg.set_value("model_combo", "Loading...")

    models = list_models(log_message)
    if dpg.is_dearpygui_running():
        dpg.configure_item("model_combo", items=models)
        current_model = os.getenv("GEMINI_MODEL_NAME", models[0])
        if not is_local_model(current_model):
            dpg.set_value("model_combo", current_model)
    log_message(f"Found {len(models)} available cloud models.", level="SUCCESS")


def start_model_fetch_thread():
    thread = threading.Thread(target=fetch_models_from_api)
    thread.start()


def run_delete_process(filename):
    try:
        if dpg.is_dearpygui_running():
            dpg.configure_item("delete_model_button", enabled=False)

        success = delete_local_model(filename, log_message)

        if success and dpg.is_dearpygui_running():
            local_model_files = scan_for_local_models()

            reverse_map = get_reverse_model_map()

            display_names = [reverse_map.get(f, f) for f in local_model_files]
            dpg.configure_item("local_model_listbox", items=display_names)

            downloadable_models = [
                name
                for name, info in AVAILABLE_GEMMA_MODELS.items()
                if info["file"] not in local_model_files
            ]
            dpg.configure_item(
                "gemma_model_to_download_combo", items=downloadable_models
            )
            if downloadable_models:
                dpg.set_value("gemma_model_to_download_combo", downloadable_models[0])

    except Exception as e:
        log_message(
            f"An unexpected error occurred during model deletion: {e}", level="ERROR"
        )
    finally:
        if dpg.is_dearpygui_running():
            dpg.configure_item("delete_model_button", enabled=True)


def start_delete_thread(filename):
    thread = threading.Thread(target=run_delete_process, args=(filename,))
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


def run_download_process(repo_id, filename):
    try:
        if dpg.is_dearpygui_running():
            dpg.configure_item("download_loading_indicator", show=True)
            dpg.configure_item("loading_indicator_label", show=True)
            dpg.configure_item("download_button", enabled=False)
            dpg.configure_item("delete_model_button", enabled=False)

        success = download_model_from_hub(repo_id, filename, log_message)

        if success and dpg.is_dearpygui_running():
            local_model_files = scan_for_local_models()

            reverse_map = get_reverse_model_map()

            display_names = [reverse_map.get(f, f) for f in local_model_files]
            dpg.configure_item("local_model_listbox", items=display_names)

            downloadable_models = [
                name
                for name, info in AVAILABLE_GEMMA_MODELS.items()
                if info["file"] not in local_model_files
            ]
            dpg.configure_item(
                "gemma_model_to_download_combo", items=downloadable_models
            )
            if downloadable_models:
                dpg.set_value("gemma_model_to_download_combo", downloadable_models[0])

    except Exception as e:
        log_message(f"An unexpected error occurred during download: {e}", level="ERROR")
    finally:
        if dpg.is_dearpygui_running():
            dpg.configure_item("download_loading_indicator", show=False)
            dpg.configure_item("loading_indicator_label", show=False)
            dpg.configure_item("download_button", enabled=True)
            dpg.configure_item("delete_model_button", enabled=True)


def start_download_thread(repo_id, filename):
    thread = threading.Thread(target=run_download_process, args=(repo_id, filename))
    thread.start()
