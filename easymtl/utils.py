import os
import dearpygui.dearpygui as dpg


def resource_path(relative_path):
    base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def format_time(seconds):
    minutes, sec = divmod(int(seconds), 60)
    return f"{minutes:02d}:{sec:02d}"


def log_message(message, level="INFO"):
    print(f"[{level}] {message}")

    colors = {
        "INFO": (255, 255, 255, 255),  # White
        "SUCCESS": (102, 255, 102, 255),  # Bright Green
        "WARNING": (255, 255, 102, 255),  # Yellow
        "ERROR": (255, 102, 102, 255),  # Red
    }
    log_color = colors.get(level, colors["INFO"])

    if dpg.is_dearpygui_running():
        dpg.add_text(message, parent="log_window_content", color=log_color, wrap=0)
        dpg.set_y_scroll("log_window", -1.0)
