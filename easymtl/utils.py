import os
import dearpygui.dearpygui as dpg
from platformdirs import user_data_dir

from easymtl.config import AVAILABLE_GEMMA_MODELS


APP_NAME = "EasyMTL"
APP_AUTHOR = "FlamingWater"
MODELS_DIR = os.path.join(user_data_dir(APP_NAME, APP_AUTHOR), "models")
_REVERSE_MODEL_MAP = None


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


def delete_local_model(filename, logger):
    models_dir = get_models_dir()
    file_path = os.path.join(models_dir, filename)

    if not os.path.abspath(file_path).startswith(os.path.abspath(models_dir)):
        logger(f"Deletion failed: Invalid path '{filename}'.", level="ERROR")
        return False

    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger(f"Successfully deleted model: {filename}", level="SUCCESS")
            return True
        except OSError as e:
            logger(f"Failed to delete model: {e}", level="ERROR")
            return False
    else:
        logger(f"Deletion failed: Model not found at '{filename}'.", level="WARNING")
        return False


def get_reverse_model_map():
    global _REVERSE_MODEL_MAP
    if _REVERSE_MODEL_MAP is None:
        _REVERSE_MODEL_MAP = {
            info["file"]: name for name, info in AVAILABLE_GEMMA_MODELS.items()
        }
    return _REVERSE_MODEL_MAP


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
