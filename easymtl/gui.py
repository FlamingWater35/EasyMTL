import os
import dearpygui.dearpygui as dpg
from ebooklib import epub, ITEM_DOCUMENT

from .utils import resource_path, log_message
from .core import start_translation_thread


def select_file_callback(sender, app_data):
    filepath = app_data["file_path_name"]
    dpg.set_value("epub_path_text", f"Selected: {os.path.basename(filepath)}")
    dpg.set_value("app_state_filepath", filepath)
    try:
        book = epub.read_epub(filepath)
        chapters = list(book.get_items_of_type(ITEM_DOCUMENT))
        dpg.set_value("app_state_total_chapters", len(chapters))
        dpg.set_value("chapter_info_text", f"This book has {len(chapters)} chapters.")
        dpg.configure_item("start_button", enabled=True)
    except Exception as e:
        log_message(f"Error reading EPUB: {e}")
        dpg.set_value("chapter_info_text", "Could not read this EPUB file.")
        dpg.configure_item("start_button", enabled=False)


def build_gui():
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
            callback=start_translation_thread,
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
