import os
import dearpygui.dearpygui as dpg
from platformdirs import user_data_dir


APP_NAME = "EasyMTL"
APP_AUTHOR = "FlamingWater"
MODELS_DIR = os.path.join(user_data_dir(APP_NAME, APP_AUTHOR), "models")


def get_models_dir():
    os.makedirs(MODELS_DIR, exist_ok=True)
    return MODELS_DIR


def scan_for_local_models():
    models_dir = get_models_dir()
    found_models = []
    if os.path.exists(models_dir):
        for file in os.listdir(models_dir):
            if file.endswith(".gguf"):
                found_models.append(file)
    return found_models


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
