import os

from easymtl.config import DEFAULT_MODEL
from .gui import build_gui


def run_app():
    os.environ.setdefault("GEMINI_MODEL_NAME", DEFAULT_MODEL)
    if not os.getenv("GOOGLE_API_KEY"):
        print(
            "INFO: GOOGLE_API_KEY not found in environment. Please set it using the Settings menu."
        )
    build_gui()


if __name__ == "__main__":
    run_app()
