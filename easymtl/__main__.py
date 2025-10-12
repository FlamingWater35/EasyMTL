import sys
from .config import GEMINI_API_KEY
from .gui import build_gui
from .utils import log_message


def run_app():
    if not GEMINI_API_KEY or "YOUR_GEMINI_API_KEY" in GEMINI_API_KEY:
        log_message("Gemini API key is not set. Please edit easymtl/config.py", level="ERROR")
        sys.exit(1)

    build_gui()


if __name__ == "__main__":
    run_app()
