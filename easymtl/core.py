import os
import re
import threading
import time
from bs4 import BeautifulSoup
from ebooklib import epub, ITEM_DOCUMENT
import dearpygui.dearpygui as dpg

from .config import (
    AVAILABLE_GEMMA_MODELS,
    TOKEN_LIMIT_PERCENTAGE,
    MAX_CHAPTERS_PER_CHUNK,
    DEFAULT_MODEL,
)
from .utils import (
    delete_local_model,
    format_time,
    get_reverse_model_map,
    log_message,
    open_text_in_editor,
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
    translate_text_with_local_model,
)

_TRANSLATION_STOP_EVENT = threading.Event()


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


def _process_with_local_model(
    chapters_to_translate, start_time, log_message, stop_event
):
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
        if stop_event.is_set():
            log_message("Translation stopped by user.", level="WARNING")
            break

        log_message(f"--- Processing Chapter {i + 1}/{total_chapters_to_process} ---")
        response = translate_text_with_local_model(chapter_data["content"], log_message)

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


def _process_with_cloud_model(
    chapters_to_translate, start_time, log_message, stop_event
):
    total_chapters_to_process = len(chapters_to_translate)
    max_output_tokens = get_model_output_limit(log_message)
    safe_token_limit = int(max_output_tokens * TOKEN_LIMIT_PERCENTAGE)
    log_message(f"Using a safe input token limit of {safe_token_limit} per chunk.")

    log_message("Pre-processing chapters to count tokens...")
    chapter_data_list = []
    for i, item in enumerate(chapters_to_translate):
        if stop_event.is_set():
            log_message("Translation stopped by user.", level="WARNING")
            return {}, [], 0

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
            or len(current_chunk_data) >= MAX_CHAPTERS_PER_CHUNK
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
        if stop_event.is_set():
            log_message("Translation stopped by user.", level="WARNING")
            break

        chunk_data = chunks.pop(0)
        chunk_items = [data["item"] for data in chunk_data]
        chunk_content = "".join([data["content"] for data in chunk_data])
        log_message(f"--- Processing Chunk (Size: {len(chunk_items)} chapters) ---")

        chunk_translation_map, response_status, response = None, None, None
        max_api_retries = 2
        for attempt in range(max_api_retries):
            response = translate_text_with_gemini(
                chunk_content, log_message, is_retry=False
            )
            response_status = response["status"]
            if response_status != "FAILED":
                break
            wait_time = 2 * (attempt + 2)
            log_message(
                f"API call failed. Waiting {wait_time}s before retrying ({attempt + 1}/{max_api_retries})...",
                level="WARNING",
            )
            if attempt < max_api_retries - 1:
                time.sleep(wait_time)

        if response_status in ["SUCCESS", "OUTPUT_TRUNCATED"]:
            chunk_translation_map = parse_translated_text(response["text"])

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
                log_message(
                    f"Model response was incomplete. Re-queuing {len(untranslated_data)} missing chapters.",
                    level="WARNING",
                )
                if len(untranslated_data) > 1:
                    mid_point = len(untranslated_data) // 2
                    first_half = untranslated_data[:mid_point]
                    second_half = untranslated_data[mid_point:]
                    chunks.insert(0, second_half)
                    chunks.insert(0, first_half)
                    log_message(
                        f"Split remainder into two new chunks of size {len(first_half)} and {len(second_half)}."
                    )
                else:
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


def run_translation_process(epub_path, start_chapter, end_chapter, stop_event):
    start_time = time.time()
    chapters_processed = 0
    total_chapters_to_process = 0
    process_halted = False

    timer_stop_event = threading.Event()
    timer_thread = threading.Thread(
        target=_update_elapsed_time_continuously, args=(start_time, timer_stop_event)
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
                    chapters_to_translate_items, start_time, log_message, stop_event
                )
            )
        else:
            try:
                translation_map, all_extraction_data, chapters_processed = (
                    _process_with_cloud_model(
                        chapters_to_translate_items, start_time, log_message, stop_event
                    )
                )
            except InterruptedError:
                process_halted = True

        if stop_event.is_set():
            process_halted = True
            log_message(
                "Process was stopped by user. No EPUB file will be created.",
                level="WARNING",
            )
        elif translation_map:
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
        timer_stop_event.set()
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
            dpg.configure_item(
                "stop_button", show=False, enabled=False, label="Stop Translation"
            )


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
    dpg.configure_item("stop_button", show=True, enabled=True)

    _TRANSLATION_STOP_EVENT.clear()

    thread = threading.Thread(
        target=run_translation_process,
        args=(epub_path, start_chapter, end_chapter, _TRANSLATION_STOP_EVENT),
    )
    thread.start()


def request_translation_stop():
    if not _TRANSLATION_STOP_EVENT.is_set():
        log_message(
            "Stop request received. Finishing current chapter/chunk...", level="INFO"
        )
        _TRANSLATION_STOP_EVENT.set()
        if dpg.is_dearpygui_running():
            dpg.configure_item("stop_button", enabled=False, label="Stopping...")


def run_proofreading_tool(epub_path):
    try:
        if dpg.is_dearpygui_running():
            dpg.configure_item("proofread_tool_button", enabled=False)
        log_message("--- Starting Proofreading Tool ---")
        book = epub.read_epub(epub_path)
        chapters = list(book.get_items_of_type(ITEM_DOCUMENT))

        non_english_errors = []
        end_mark_errors = []

        log_message(f"Scanning {len(chapters)} chapters...")
        non_english_pattern = re.compile(r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+")
        valid_end_marks = {".", "?", "!", '"', "'", "”", "’", ")", "]", "*"}

        for item in chapters:
            soup = BeautifulSoup(item.get_content(), "html.parser")
            title_tag = soup.find("h1") or soup.find("title")
            chapter_title = (
                title_tag.get_text().strip() if title_tag else item.get_name()
            )

            paragraphs = soup.find_all("p")
            for i, p in enumerate(paragraphs):
                p_text = p.get_text().strip()
                if not p_text:
                    continue

                if non_english_pattern.search(p_text):
                    non_english_errors.append(
                        {"chapter": chapter_title, "p_num": i + 1, "text": p_text}
                    )

                if p_text[-1] not in valid_end_marks:
                    end_mark_errors.append(
                        {"chapter": chapter_title, "p_num": i + 1, "text": p_text}
                    )

        log_message("Scan complete. Generating reports...")

        if non_english_errors:
            log_message(
                f"Found {len(non_english_errors)} paragraphs with non-English characters.",
                level="WARNING",
            )
            report_content = "Non-English Character Report\n" + "=" * 30 + "\n\n"
            for error in non_english_errors:
                report_content += f"--------------------\n"
                report_content += f"Chapter: {error['chapter']}\n"
                report_content += f"Paragraph: {error['p_num']}\n\n"
                report_content += f"{error['text']}\n"
                report_content += f"--------------------\n\n"
            open_text_in_editor(report_content, "non_english", log_message)
        else:
            log_message("No non-English characters found.", level="SUCCESS")

        if end_mark_errors:
            log_message(
                f"Found {len(end_mark_errors)} paragraphs with missing end marks.",
                level="WARNING",
            )
            report_content = "Missing End Mark Report\n" + "=" * 30 + "\n\n"
            for error in end_mark_errors:
                report_content += f"--------------------\n"
                report_content += f"Chapter: {error['chapter']}\n"
                report_content += f"Paragraph: {error['p_num']}\n\n"
                report_content += f"{error['text']}\n"
                report_content += f"--------------------\n\n"
            open_text_in_editor(report_content, "end_marks", log_message)
        else:
            log_message("No missing end marks found.", level="SUCCESS")

    except Exception as e:
        log_message(
            f"An unexpected error occurred during proofreading: {e}", level="ERROR"
        )
    finally:
        log_message("--- Proofreading Finished ---")
        if dpg.is_dearpygui_running():
            dpg.configure_item("proofread_tool_button", enabled=True)


def start_proofreading_thread(epub_path):
    thread = threading.Thread(target=run_proofreading_tool, args=(epub_path,))
    thread.start()


def run_stylesheet_fix_process(epub_path):
    try:
        if dpg.is_dearpygui_running():
            dpg.configure_item("fix_styles_button", enabled=False)
        log_message("--- Starting Stylesheet Fixer Tool ---")
        book = epub.read_epub(epub_path)

        style_item = book.get_item_with_id("style_default")
        if not style_item:
            log_message(
                "The 'style/default.css' file is missing from this EPUB. Cannot perform fix.",
                level="ERROR",
            )
            return

        chapters = list(book.get_items_of_type(ITEM_DOCUMENT))
        fixed_count = 0
        log_message(
            f"Scanning {len(chapters)} chapter files for missing stylesheet links..."
        )

        for item in chapters:
            soup = BeautifulSoup(item.get_content(), "xml")
            head = soup.find("head")
            if not head:
                continue

            has_link = any(
                link.get("href") and "default.css" in link.get("href")
                for link in head.find_all("link")
            )

            if not has_link:
                chapter_dir = os.path.dirname(item.get_name())
                relative_path = os.path.relpath(
                    style_item.get_name(), chapter_dir
                ).replace("\\", "/")
                new_link_tag = soup.new_tag(
                    "link",
                    rel="stylesheet",
                    type="text/css",
                    href=relative_path,
                )
                head.append(new_link_tag)
                item.set_content(str(soup).encode("utf-8"))
                item.add_item(style_item)
                fixed_count += 1

        if fixed_count > 0:
            dir_name, file_name = os.path.split(epub_path)
            new_file_name = os.path.splitext(file_name)[0] + "_fixed.epub"
            new_file_path = os.path.join(dir_name, new_file_name)

            epub.write_epub(new_file_path, book, {})
            log_message(
                f"Successfully fixed {fixed_count} chapters. New file saved as: {new_file_path}",
                level="SUCCESS",
            )
        else:
            log_message(
                "No missing stylesheet links found. The book is already correct.",
                level="SUCCESS",
            )

    except Exception as e:
        log_message(
            f"An unexpected error occurred during the fix process: {e}", level="ERROR"
        )
    finally:
        log_message("--- Stylesheet Fixer Finished ---")
        if dpg.is_dearpygui_running():
            dpg.configure_item("fix_styles_button", enabled=True)


def start_stylesheet_fix_thread(epub_path):
    thread = threading.Thread(target=run_stylesheet_fix_process, args=(epub_path,))
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
