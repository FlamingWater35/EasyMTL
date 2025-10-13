TOKEN_SAFETY_MARGIN = 2000
LOCAL_MODEL_CONTEXT_SIZE = 8192
DEFAULT_MODEL = "models/gemini-2.5-flash"
AVAILABLE_GEMMA_MODELS = {
    "Gemma 2 - 2B (bartowski)": {
        "repo": "bartowski/gemma-2-2b-it-GGUF",
        "file": "gemma-2-2b-it-Q4_K_M.gguf",
    },
    "Gemma 3 - 4B (unsloth)": {
        "repo": "unsloth/gemma-3-4b-it-GGUF",
        "file": "gemma-3-4b-it-Q4_K_M.gguf",
    },
    "Gemma 3 - 12B (unsloth)": {
        "repo": "unsloth/gemma-3-12b-it-GGUF",
        "file": "gemma-3-12b-it-Q4_K_M.gguf",
    },
}
