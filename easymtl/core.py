import threading
import time
from ebooklib import epub, ITEM_DOCUMENT
import dearpygui.dearpygui as dpg

from .config import CHAPTER_CHUNK_SIZE
from .utils import log_message
from .epub_handler import extract_content_from_chapters, create_translated_epub
from .translator import translate_text_with_gemini, parse_translated_text


def run_translation_process(epub_path, num_chapters):
    try:
        if dpg.is_dearpygui_running():
            dpg.set_value("progress_bar", 0.0)
        log_message("--- Starting Translation Process ---")
        book = epub.read_epub(epub_path)
        all_chapters = list(book.get_items_of_type(ITEM_DOCUMENT))
        chapters_to_translate_items = all_chapters[:num_chapters]
        log_message(
            f"Selected {len(chapters_to_translate_items)} of {len(all_chapters)} chapters."
        )

        chapter_chunks = [
            chapters_to_translate_items[i : i + CHAPTER_CHUNK_SIZE]
            for i in range(0, len(chapters_to_translate_items), CHAPTER_CHUNK_SIZE)
        ]
        log_message(
            f"Dividing the task into {len(chapter_chunks)} chunks of up to {CHAPTER_CHUNK_SIZE} chapters each."
        )

        translation_map = {}
        all_extraction_data = []
        stop_processing = False

        for i, chunk_items in enumerate(chapter_chunks):
            log_message(f"--- Processing Chunk {i + 1}/{len(chapter_chunks)} ---")

            chunk_content, chunk_extraction_data = extract_content_from_chapters(
                chunk_items, log_message
            )
            if not chunk_content:
                log_message(
                    f"Warning: Failed to extract text from chunk {i+1}. Skipping."
                )
                continue

            parsed_chapters_chunk = None
            for attempt in range(2):
                is_retry = attempt > 0
                response = translate_text_with_gemini(
                    chunk_content, log_message, is_retry=is_retry
                )

                if response['status'] == 'SUCCESS':
                    parsed_chapters_chunk = parse_translated_text(response['text'])
                    if len(parsed_chapters_chunk) == len(chunk_items):
                        log_message(f"Successfully translated {len(parsed_chapters_chunk)} chapters in this chunk.")
                        break
                    else:
                        log_message(f"Warning: Chunk {i+1} sent {len(chunk_items)} but received {len(parsed_chapters_chunk)}. Retrying...")
                
                elif response['status'] == 'OUTPUT_TRUNCATED':
                    log_message("Accepting truncated output. The last chapter in this chunk may be incomplete. No retry will be attempted.")
                    parsed_chapters_chunk = parse_translated_text(response['text'])
                    break
                
                elif response['status'] == 'TOKEN_LIMIT_EXCEEDED':
                    log_message("Stopping translation process due to input token limit.")
                    stop_processing = True
                    break
                
                elif response['status'] == 'FAILED':
                    log_message(f"API call failed for chunk {i+1}. Retrying...")
                time.sleep(1)

            if parsed_chapters_chunk:
                if len(parsed_chapters_chunk) != len(chunk_items):
                    log_message(
                        f"Warning: After retry, chunk {i+1} still has a chapter count mismatch. Proceeding with {len(parsed_chapters_chunk)} chapters."
                    )
                for original_item, translated_text in zip(
                    chunk_items, parsed_chapters_chunk
                ):
                    translation_map[original_item.get_name()] = translated_text
                all_extraction_data.extend(chunk_extraction_data)
            else:
                log_message(
                    f"ERROR: Translation failed for chunk {i+1} after all retries. This chunk will be skipped."
                )

            progress = (i + 1) / len(chapter_chunks)
            if dpg.is_dearpygui_running():
                dpg.set_value("progress_bar", progress)

            if stop_processing:
                log_message("Halting further processing as requested.")
                break

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
                "Translation failed for all chunks. No EPUB file will be created."
            )

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
