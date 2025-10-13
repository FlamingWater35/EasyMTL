import ctypes
import os
import dearpygui.dearpygui as dpg
import pywinstyles
from win32 import win32gui
from ebooklib import epub, ITEM_DOCUMENT

from easymtl.config import AVAILABLE_GEMMA_MODELS

from .utils import (
    get_reverse_model_map,
    resource_path,
    log_message,
    scan_for_local_models,
)
from .core import (
    start_cover_creation_thread,
    start_delete_thread,
    start_download_thread,
    start_model_fetch_thread,
    start_translation_thread,
)


def setup_window():
    hwnd = win32gui.FindWindow(None, "EasyMTL")
    if hwnd == 0:
        print("Window not found for pywinstyles")
    else:
        pywinstyles.apply_style(hwnd, "mica")


def setup_themes():
    with dpg.font_registry():
        default_font = dpg.add_font(resource_path("easymtl/assets/font.otf"), 22)
    dpg.bind_font(default_font)

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
            dpg.add_theme_color(dpg.mvThemeCol_Text, (123, 123, 123))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (75, 75, 75))
        with dpg.theme_component(dpg.mvProgressBar):
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4, 4)
            dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 2, 2)
            dpg.add_theme_color(dpg.mvThemeCol_Border, (57, 169, 92))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (93, 64, 55))
            dpg.add_theme_color(dpg.mvThemeCol_PlotHistogram, (42, 128, 69))
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
    dpg.bind_item_theme("api_key_modal_content", window_theme)
    dpg.bind_item_theme("cover_tool_modal_content", window_theme)
    dpg.bind_item_theme("model_select_modal_content", window_theme)
    dpg.bind_item_theme("local_models_modal_content", window_theme)


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
        dpg.configure_item("start_button", enabled=False)


def save_api_key_callback():
    api_key = dpg.get_value("api_key_input")
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
        log_message("API Key has been set for this session.", level="SUCCESS")
        dpg.configure_item("api_key_modal", show=False)
        start_model_fetch_thread()
    else:
        log_message("API Key field cannot be empty.", level="WARNING")


def select_cover_tool_file_callback(sender, app_data):
    filepath = app_data.get("file_path_name")
    if filepath:
        start_cover_creation_thread(filepath)


def open_model_selector_callback():
    if not dpg.get_item_configuration("model_combo")["items"]:
        start_model_fetch_thread()
    dpg.configure_item("model_select_modal", show=True)


def save_model_callback():
    selected_model = dpg.get_value("model_combo")
    os.environ["GEMINI_MODEL_NAME"] = selected_model
    log_message(f"Model for this session set to: {selected_model}", level="SUCCESS")
    dpg.configure_item("model_select_modal", show=False)


def open_local_models_callback():
    local_model_files = scan_for_local_models()
    reverse_map = get_reverse_model_map()
    display_names = [reverse_map.get(f, f) for f in local_model_files]
    dpg.configure_item("local_model_listbox", items=display_names)

    downloadable_models = [
        name
        for name, info in AVAILABLE_GEMMA_MODELS.items()
        if info["file"] not in local_model_files
    ]

    dpg.configure_item("gemma_model_to_download_combo", items=downloadable_models)
    if downloadable_models:
        dpg.set_value("gemma_model_to_download_combo", downloadable_models[0])
    dpg.configure_item("local_models_modal", show=True)


def download_selected_model_callback():
    selected_model_name = dpg.get_value("gemma_model_to_download_combo")
    if selected_model_name:
        model_info = AVAILABLE_GEMMA_MODELS[selected_model_name]
        start_download_thread(model_info["repo"], model_info["file"])


def select_local_model_callback():
    selected_display_name = dpg.get_value("local_model_listbox")
    if not selected_display_name:
        return

    filename_to_use = None
    for name, info in AVAILABLE_GEMMA_MODELS.items():
        if name == selected_display_name:
            filename_to_use = info["file"]
            break

    if filename_to_use is None:
        filename_to_use = selected_display_name

    os.environ["GEMINI_MODEL_NAME"] = filename_to_use
    log_message(
        f"Local model for this session set to: {selected_display_name}", level="SUCCESS"
    )
    dpg.configure_item("local_models_modal", show=False)


def delete_selected_model_callback():
    selected_display_name = dpg.get_value("local_model_listbox")
    if not selected_display_name:
        log_message("No model selected to delete.", level="WARNING")
        return

    filename_to_delete = None
    for name, info in AVAILABLE_GEMMA_MODELS.items():
        if name == selected_display_name:
            filename_to_delete = info["file"]
            break

    if filename_to_delete is None:
        filename_to_delete = selected_display_name

    log_message(
        f"Attempting to delete {selected_display_name} ({filename_to_delete})..."
    )
    start_delete_thread(filename_to_delete)


def build_gui():
    dpg.create_context()

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

    api_modal_width = dpg.get_viewport_width() / 2
    api_modal_height = dpg.get_viewport_height() / 3
    with dpg.window(
        label="API Key Setup",
        modal=True,
        show=False,
        tag="api_key_modal",
        no_close=True,
        width=api_modal_width,
        height=api_modal_height,
        pos=[
            (dpg.get_viewport_width() / 2) - (api_modal_width / 2),
            (dpg.get_viewport_height() / 2) - (api_modal_height / 2),
        ],
    ):
        with dpg.child_window(
            tag="api_key_modal_content",
            autosize_x=True,
            autosize_y=True,
        ):
            dpg.add_text("Please paste your Google Gemini API key below.", wrap=0)
            dpg.add_text(
                "This key will only be stored for the current session.", wrap=0
            )
            dpg.add_spacer(height=10)

            dpg.add_input_text(
                tag="api_key_input", label="API Key", password=True, width=-80
            )
            dpg.add_spacer(height=10)

            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Save Key", width=120, callback=save_api_key_callback
                )
                dpg.add_button(
                    label="Cancel",
                    width=120,
                    callback=lambda: dpg.configure_item("api_key_modal", show=False),
                )

    with dpg.window(
        label="Cover Page Tool",
        show=False,
        no_collapse=True,
        tag="cover_tool_modal",
        width=api_modal_width,
        height=api_modal_height,
        pos=[
            (dpg.get_viewport_width() / 2) - (api_modal_width / 2),
            (dpg.get_viewport_height() / 2) - (api_modal_height / 2),
        ],
    ):
        with dpg.child_window(
            tag="cover_tool_modal_content",
            autosize_x=True,
            autosize_y=True,
        ):
            dpg.add_text(
                "This tool will create a copy of an EPUB file and replace its first page with a proper, centered cover image.",
                wrap=0,
            )
            dpg.add_spacer(height=10)
            dpg.add_text("It finds the cover image from the book's metadata.", wrap=0)
            dpg.add_spacer(height=20)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Select EPUB File",
                    tag="cover_tool_button",
                    width=-1,
                    callback=lambda: dpg.show_item("cover_tool_file_dialog"),
                )

    with dpg.file_dialog(
        directory_selector=False,
        show=False,
        callback=select_cover_tool_file_callback,
        tag="cover_tool_file_dialog",
        width=dpg.get_viewport_width() / 1.3,
        height=dpg.get_viewport_height() / 1.5,
        modal=True,
    ):
        dpg.add_file_extension(".epub", color=(0, 255, 0, 255))

    with dpg.window(
        label="Model Selection",
        modal=True,
        show=False,
        tag="model_select_modal",
        no_close=True,
        width=api_modal_width,
        height=api_modal_height * 1.2,
        pos=[
            (dpg.get_viewport_width() / 2) - (api_modal_width / 2),
            (dpg.get_viewport_height() / 2) - (api_modal_height / 2),
        ],
    ):
        with dpg.child_window(
            tag="model_select_modal_content",
            autosize_x=True,
            autosize_y=True,
        ):
            dpg.add_text("Select the Gemini model to use for translation.", wrap=0)
            dpg.add_text("This setting will only apply to the current session.", wrap=0)
            dpg.add_spacer(height=10)

            dpg.add_combo(tag="model_combo", label="Model", items=[], width=-60)
            dpg.add_spacer(height=20)

            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Set Model", width=120, callback=save_model_callback
                )
                dpg.add_button(
                    label="Cancel",
                    width=120,
                    callback=lambda: dpg.configure_item(
                        "model_select_modal", show=False
                    ),
                )

    local_models_modal_width = dpg.get_viewport_width() / 1.3
    local_models_modal_height = dpg.get_viewport_height() / 1.6
    with dpg.window(
        label="Local Model Manager",
        modal=True,
        show=False,
        tag="local_models_modal",
        width=local_models_modal_width,
        height=local_models_modal_height,
        pos=[
            (dpg.get_viewport_width() / 2) - (local_models_modal_width / 2),
            (dpg.get_viewport_height() / 2) - (local_models_modal_height / 2),
        ],
    ):
        with dpg.child_window(
            tag="local_models_modal_content",
            autosize_x=True,
            autosize_y=True,
        ):
            dpg.add_text("Download and select local Gemma models (GGUF).", wrap=0)
            dpg.add_text(
                "Models are saved to your user data directory.",
                color=(200, 200, 200),
                wrap=0,
            )
            dpg.add_separator()

            dpg.add_text("Download New Model")
            with dpg.group(horizontal=True):
                dpg.add_combo(tag="gemma_model_to_download_combo", items=[], width=-150)
                dpg.add_button(
                    label="Download",
                    tag="download_button",
                    callback=download_selected_model_callback,
                )
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=5)
                dpg.add_loading_indicator(
                    tag="download_loading_indicator",
                    show=False,
                    style=1,
                    radius=3,
                    thickness=1.5,
                    color=(81, 71, 164),
                )
                dpg.add_spacer(width=5)
                with dpg.group():
                    dpg.add_spacer(height=5)
                    dpg.add_text(
                        "Downloading...", tag="loading_indicator_label", show=False
                    )
            dpg.add_spacer(height=5)
            dpg.add_separator()

            dpg.add_text("Manage Downloaded Models", wrap=0)
            dpg.add_listbox(tag="local_model_listbox", items=[], num_items=5)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Use Selected Model", callback=select_local_model_callback
                )
                dpg.add_button(
                    label="Delete Selected Model",
                    tag="delete_model_button",
                    callback=delete_selected_model_callback,
                )

    with dpg.window(tag="primary_window", label="EasyMTL Translator"):
        with dpg.menu_bar():
            with dpg.menu(label="Settings"):
                dpg.add_menu_item(
                    label="Set API Key",
                    callback=lambda: dpg.configure_item("api_key_modal", show=True),
                )
            with dpg.menu(label="Models"):
                dpg.add_menu_item(
                    label="Select Cloud Model", callback=open_model_selector_callback
                )
                dpg.add_separator()
                dpg.add_menu_item(
                    label="Manage Local Models", callback=open_local_models_callback
                )
            with dpg.menu(label="Tools"):
                dpg.add_menu_item(
                    label="Create Cover Page",
                    callback=lambda: dpg.configure_item("cover_tool_modal", show=True),
                )

        with dpg.child_window(
            tag="main_window",
            autosize_x=True,
            auto_resize_y=True,
        ):
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
            with dpg.group():
                dpg.add_input_int(
                    label="Start",
                    tag="start_chapter_input",
                    default_value=1,
                    min_value=1,
                    width=150,
                    enabled=False,
                )
                dpg.add_input_int(
                    label="End",
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
            with dpg.group(horizontal=True):
                with dpg.group():
                    dpg.add_spacer(height=5)
                    dpg.add_progress_bar(
                        tag="progress_bar",
                        default_value=0.0,
                        width=-170,
                        height=35,
                        overlay="",
                    )
                with dpg.group():
                    dpg.add_text("", tag="elapsed_time_text")
                    dpg.add_text("", tag="eta_time_text")
            dpg.add_spacer(height=5)

            with dpg.collapsing_header(label="Logs", default_open=True):
                with dpg.child_window(
                    tag="log_window",
                    height=250,
                    border=True,
                    autosize_x=True,
                    auto_resize_y=True,
                ):
                    dpg.add_group(tag="log_window_content")

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
