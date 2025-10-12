import ctypes
import os
import dearpygui.dearpygui as dpg
import pywinstyles
from win32 import win32gui
from ebooklib import epub, ITEM_DOCUMENT

from .utils import resource_path, log_message
from .core import start_translation_thread


def setup_window():
    hwnd = win32gui.FindWindow(None, "EasyMTL")
    if hwnd == 0:
        print("Window not found for pywinstyles")
    else:
        pywinstyles.apply_style(hwnd, "mica")


def setup_themes():
    with dpg.theme() as window_theme:
        with dpg.theme_component(dpg.mvChildWindow):
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 15, 10)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 3, 3)
            dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 4, 4)
            dpg.add_theme_color(dpg.mvThemeCol_Border, (93, 64, 55))
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 5)
            dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 2, 2)
            dpg.add_theme_color(dpg.mvThemeCol_Border, (81, 71, 164))
        with dpg.theme_component(dpg.mvButton, enabled_state=False):
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 5)
            dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 2, 2)
            dpg.add_theme_color(dpg.mvThemeCol_Border, (148, 147, 150))
        with dpg.theme_component(dpg.mvInputInt):
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 5, 2.5)
            dpg.add_theme_color(dpg.mvThemeCol_Border, (191, 54, 12))
        with dpg.theme_component(dpg.mvCollapsingHeader):
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 5, 5)
            dpg.add_theme_color(dpg.mvThemeCol_Border, (0, 96, 100))
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4)
            dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 2, 2)
    dpg.bind_item_theme("main_window", window_theme)


def select_file_callback(sender, app_data):
    filepath = app_data["file_path_name"]
    dpg.set_value("epub_path_text", f"Selected: {os.path.basename(filepath)}")
    dpg.set_value("app_state_filepath", filepath)
    try:
        book = epub.read_epub(filepath)
        chapters = list(book.get_items_of_type(ITEM_DOCUMENT))
        total_chapters = len(chapters)

        dpg.set_value("app_state_total_chapters", total_chapters)
        dpg.set_value("chapter_info_text", f"This book has {total_chapters} chapters.")
        dpg.configure_item(
            "start_chapter_input",
            enabled=True,
            max_value=total_chapters,
            default_value=1,
        )
        dpg.configure_item(
            "end_chapter_input",
            enabled=True,
            max_value=total_chapters,
            default_value=total_chapters,
        )
        dpg.configure_item("start_button", enabled=True)
    except Exception as e:
        log_message(f"Error reading EPUB: {e}", level="ERROR")
        dpg.set_value("chapter_info_text", "Could not read this EPUB file.")
        dpg.configure_item("start_chapter_input", enabled=False)
        dpg.configure_item("end_chapter_input", enabled=False)


def save_api_key_callback():
    api_key = dpg.get_value("api_key_input")
    if api_key:
        os.environ["GEMINI_API_KEY"] = api_key
        log_message("API Key has been set for this session.", level="SUCCESS")
        dpg.configure_item("api_key_modal", show=False)
    else:
        log_message("API Key field cannot be empty.", level="WARNING")


def build_gui():
    dpg.create_context()
    with dpg.font_registry():
        default_font = dpg.add_font(resource_path("easymtl/assets/font.otf"), 22)

    with dpg.window(
        label="API Key Setup",
        modal=True,
        show=False,
        tag="api_key_modal",
        no_close=True,
        width=450,
    ):
        dpg.add_text("Please paste your Google Gemini API key below.")
        dpg.add_text("This key will only be stored for the current session.", wrap=440)
        dpg.add_spacer(height=10)

        dpg.add_input_text(
            tag="api_key_input", label="API Key", password=True, width=-1
        )
        dpg.add_spacer(height=10)

        with dpg.group(horizontal=True):
            dpg.add_button(label="Save Key", width=120, callback=save_api_key_callback)
            dpg.add_button(
                label="Cancel",
                width=120,
                callback=lambda: dpg.configure_item("api_key_modal", show=False),
            )

    with dpg.window(tag="primary_window", label="EasyMTL Translator"):
        with dpg.menu_bar():
            with dpg.menu(label="Settings"):
                dpg.add_menu_item(
                    label="Set API Key",
                    callback=lambda: dpg.configure_item("api_key_modal", show=True),
                )

        with dpg.child_window(tag="main_window"):
            dpg.add_text("", tag="app_state_filepath", show=False)
            dpg.add_input_int(
                tag="app_state_total_chapters", show=False, default_value=0
            )
            dpg.add_text("1. Select EPUB File")
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Browse...", callback=lambda: dpg.show_item("file_dialog_id")
                )
                dpg.add_text("No file selected.", tag="epub_path_text")
            dpg.add_text("", tag="chapter_info_text")
            dpg.add_spacer(height=5)
            dpg.add_text("2. Select Chapter Range to Translate")
            with dpg.group(horizontal=True):
                dpg.add_input_int(
                    label="Start Chapter",
                    tag="start_chapter_input",
                    default_value=1,
                    min_value=1,
                    width=150,
                    enabled=False,
                )
                dpg.add_input_int(
                    label="End Chapter",
                    tag="end_chapter_input",
                    default_value=1,
                    min_value=1,
                    width=150,
                    enabled=False,
                )
            dpg.add_spacer(height=10)
            dpg.add_button(
                label="Start Translation",
                tag="start_button",
                callback=start_translation_thread,
                enabled=False,
            )
            dpg.add_spacer(height=15)
            dpg.add_text("Progress:")
            dpg.add_progress_bar(tag="progress_bar", default_value=0.0, width=-1)
            dpg.add_spacer(height=5)

            with dpg.collapsing_header(label="Logs"):
                with dpg.child_window(tag="log_window", height=250, border=True):
                    dpg.add_group(tag="log_window_content")

    user32 = ctypes.windll.user32
    screen_width, screen_height = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    dpg.create_viewport(
        title="EasyMTL",
        width=1000,
        height=800,
        small_icon=resource_path("easymtl/assets/icon.ico"),
        large_icon=resource_path("easymtl/assets/icon.ico"),
    )
    dpg.set_viewport_pos(
        [
            (screen_width / 2) - (dpg.get_viewport_width() / 2),
            (screen_height / 2) - (dpg.get_viewport_height() / 2),
        ]
    )
    dpg.bind_font(default_font)
    with dpg.file_dialog(
        directory_selector=False,
        show=False,
        callback=select_file_callback,
        tag="file_dialog_id",
        width=dpg.get_viewport_width() / 1.3,
        height=dpg.get_viewport_height() / 1.5,
        modal=True,
    ):
        dpg.add_file_extension(".epub", color=(0, 255, 0, 255))
    setup_themes()
    dpg.setup_dearpygui()
    dpg.show_viewport()
    setup_window()
    dpg.set_primary_window("primary_window", True)
    dpg.start_dearpygui()
    dpg.destroy_context()
