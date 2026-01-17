APP_VERSION = "1.0.8"
GITHUB_REPO = "FlamingWater35/EasyMTL"
TOKEN_LIMIT_PERCENTAGE = 0.60
MAX_CHAPTERS_PER_CHUNK = 20
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
    "Mistral - 7B Instruct (MaziyarPanahi)": {
        "repo": "MaziyarPanahi/Mistral-7B-Instruct-v0.3-GGUF",
        "file": "Mistral-7B-Instruct-v0.3.Q4_K_M.gguf",
    },
    "Qwen 3 - 8B (MaziyarPanahi)": {
        "repo": "MaziyarPanahi/Qwen3-8B-GGUF",
        "file": "Qwen3-8B.Q4_K_M.gguf",
    },
}
