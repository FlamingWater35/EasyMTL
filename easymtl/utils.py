import os
import dearpygui.dearpygui as dpg


def resource_path(relative_path):
    base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def log_message(message):
    print(message)
    if dpg.is_dearpygui_running():
        dpg.add_text(message, parent="log_window_content", wrap=0)
        dpg.set_y_scroll("log_window", dpg.get_y_scroll_max("log_window"))
