import os
import sys
import threading
import ebooklib
from ebooklib import epub
import google.generativeai as genai
from bs4 import BeautifulSoup
import dearpygui.dearpygui as dpg

GEMINI_API_KEY = "AIzaSyCNntMoZqn7nnhnLhD2IUaATQ-j4zEj-AY"


def resource_path(relative_path):
    base_path = os.path.abspath(".")
    full_path = os.path.join(base_path, relative_path)
    return full_path


def log_message(message):
    print(message)
    dpg.add_text(message, parent="log_window_content")
    dpg.set_y_scroll("log_window", dpg.get_y_scroll_max("log_window"))


def extract_content_from_chapters(chapter_items, logger):
    logger("Extracting content from selected chapters...")
    full_content = ""
    for item in chapter_items:
        soup = BeautifulSoup(item.get_content(), "html.parser")
        chapter_text = soup.get_text(separator="\n", strip=True)
        full_content += chapter_text + "\n---\n"
    logger("Content extracted successfully.")
    return full_content


def translate_text_with_gemini(text, logger):
    genai.configure(api_key=GEMINI_API_KEY)
    prompt = f"""Translate the following novel chapters into English.
If a chapter has a title, enclose the translated title in double asterisks, like this: **Chapter Title**.
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


def create_translated_epub(
    original_path, translated_chapters, chapters_to_replace, logger
):
    logger("Creating new EPUB file...")
    dir_name, file_name = os.path.split(original_path)
    new_file_name = os.path.splitext(file_name)[0] + "_translated.epub"
    new_file_path = os.path.join(dir_name, new_file_name)

    book = epub.read_epub(original_path)

    stylesheet_content = """
    body { font-family: serif; line-height: 1.6; margin: 5px; }
    h1 { text-align: center; font-weight: bold; page-break-before: always; margin-top: 2em; margin-bottom: 2em; }
    p { text-align: justify; text-indent: 1.5em; margin-top: 0; margin-bottom: 0; }
    """
    style_item = epub.EpubItem(
        uid="style_default",
        file_name="style/default.css",
        media_type="text/css",
        content=stylesheet_content,
    )
    book.add_item(style_item)

    if len(translated_chapters) != len(chapters_to_replace):
        logger(
            f"Warning: Mismatch between requested chapters ({len(chapters_to_replace)}) and translated chapters ({len(translated_chapters)})."
        )
        min_len = min(len(translated_chapters), len(chapters_to_replace))
        translated_chapters = translated_chapters[:min_len]
        chapters_to_replace = chapters_to_replace[:min_len]

    for i, item_to_replace in enumerate(chapters_to_replace):
        item_in_new_book = book.get_item_with_href(item_to_replace.get_name())
        if item_in_new_book:
            lines = translated_chapters[i].strip().split("\n")
            title, body_content = f"Chapter {i+1}", ""

            if lines and lines[0].startswith("**") and lines[0].endswith("**"):
                title_text = lines[0].strip("* ").strip()
                body_content += f"<h1>{title_text}</h1>\n"
                paragraphs = lines[1:]
            else:
                title_text = item_in_new_book.title or title
                paragraphs = lines

            body_content += "".join(
                f"<p>{p.strip()}</p>\n" for p in paragraphs if p.strip()
            )
            html_content = f"""<?xml version='1.0' encoding='utf-8'?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{title_text}</title><link rel="stylesheet" type="text/css" href="default.css" /></head>
<body>{body_content}</body></html>"""
            item_in_new_book.set_content(html_content.encode("utf-8"))
            item_in_new_book.add_item(style_item)

    try:
        epub.write_epub(new_file_path, book, {})
        logger(f"SUCCESS: Translated e-book saved as: {new_file_path}")
    except Exception as e:
        logger(f"ERROR: Could not write translated EPUB file: {e}")


def run_translation_process(epub_path, num_chapters):
    try:
        log_message("--- Starting Translation Process ---")
        book = epub.read_epub(epub_path)
        all_chapters = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        chapters_to_translate_items = all_chapters[:num_chapters]
        log_message(
            f"Selected {len(chapters_to_translate_items)} of {len(all_chapters)} chapters."
        )

        extracted_text = extract_content_from_chapters(
            chapters_to_translate_items, log_message
        )
        if not extracted_text:
            log_message("ERROR: Failed to extract text.")
            return

        translated_text = translate_text_with_gemini(extracted_text, log_message)
        if translated_text:
            parsed_chapters = parse_translated_text(translated_text)
            log_message(
                f"Parsed {len(parsed_chapters)} translated chapters from API response."
            )
            create_translated_epub(
                epub_path, parsed_chapters, chapters_to_translate_items, log_message
            )
        else:
            log_message("Translation failed. The process was halted.")

    except Exception as e:
        log_message(f"An unexpected error occurred in the translation thread: {e}")
    finally:
        log_message("--- Process Finished ---")
        dpg.configure_item("start_button", enabled=True)


def select_file_callback(sender, app_data):
    filepath = app_data["file_path_name"]
    dpg.set_value("epub_path_text", f"Selected: {os.path.basename(filepath)}")
    dpg.set_value("app_state_filepath", filepath)
    try:
        book = epub.read_epub(filepath)
        chapters = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        dpg.set_value("app_state_total_chapters", len(chapters))
        dpg.set_value("chapter_info_text", f"This book has {len(chapters)} chapters.")
        dpg.configure_item("start_button", enabled=True)
    except Exception as e:
        log_message(f"Error reading EPUB: {e}")
        dpg.set_value("chapter_info_text", "Could not read this EPUB file.")
        dpg.configure_item("start_button", enabled=False)


def start_translation_callback():
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


def main():
    if not GEMINI_API_KEY or "YOUR_GEMINI_API_KEY" in GEMINI_API_KEY:
        print("ERROR: Please set your GEMINI_API_KEY in the script.")
        sys.exit(1)

    dpg.create_context()

    with dpg.font_registry():
        default_font = dpg.add_font(resource_path("easymtl/assets/font.otf"), 22)

    with dpg.file_dialog(
        directory_selector=False,
        show=False,
        callback=select_file_callback,
        tag="file_dialog_id",
        width=700,
        height=400,
        modal=True,
    ):
        dpg.add_file_extension(".epub", color=(0, 255, 0, 255))

    with dpg.window(tag="Primary Window", label="EasyMTL Translator"):
        dpg.add_text("", tag="app_state_filepath", show=False)
        dpg.add_input_int(tag="app_state_total_chapters", show=False, default_value=0)

        dpg.add_text("1. Select EPUB File")
        with dpg.group(horizontal=True):
            dpg.add_button(
                label="Browse...", callback=lambda: dpg.show_item("file_dialog_id")
            )
            dpg.add_text("No file selected.", tag="epub_path_text")
        dpg.add_text("", tag="chapter_info_text")
        dpg.add_spacer(height=10)

        dpg.add_text("2. Enter Number of Chapters to Translate")
        dpg.add_input_int(
            label="Chapters",
            tag="chapter_count_input",
            default_value=1,
            min_value=1,
            width=120,
        )
        dpg.add_spacer(height=10)

        dpg.add_button(
            label="Start Translation",
            tag="start_button",
            callback=start_translation_callback,
            enabled=False,
        )
        dpg.add_spacer(height=10)

        with dpg.collapsing_header(label="Logs"):
            with dpg.child_window(tag="log_window", height=250, border=True):
                dpg.add_group(tag="log_window_content")

        dpg.bind_font(default_font)

    dpg.create_viewport(
        title="EasyMTL",
        width=800,
        height=600,
        small_icon=resource_path("easymtl/assets/icon.ico"),
        large_icon=resource_path("easymtl/assets/icon.ico"),
    )
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("Primary Window", True)
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    main()
