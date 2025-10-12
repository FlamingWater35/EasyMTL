import os
from .gui import build_gui


def run_app():
    if not os.getenv("GEMINI_API_KEY"):
        print(
            "INFO: Gemini API Key not found in environment. Please set it using the Settings menu in the app."
        )

    build_gui()


if __name__ == "__main__":
    run_app()
