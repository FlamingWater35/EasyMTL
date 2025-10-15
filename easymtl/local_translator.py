import os
from llama_cpp import Llama
from huggingface_hub import hf_hub_download
from huggingface_hub.utils import GatedRepoError, HfHubHTTPError
from .utils import get_models_dir
from .config import LOCAL_MODEL_CONTEXT_SIZE

_LOCAL_MODEL_INSTANCE = None
_LOADED_MODEL_PATH = None


def download_model_from_hub(repo_id, filename, logger):
    models_dir = get_models_dir()

    try:
        logger(f"Starting download of {filename} from {repo_id}...")

        hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            local_dir=models_dir,
        )

        logger(f"Successfully downloaded {filename}!", level="SUCCESS")
        return True
    except GatedRepoError as e:
        logger(f"Access denied. This is a gated model.", level="ERROR")
        logger(
            "Please visit the model page on Hugging Face, accept the terms, and log in via your terminal using 'huggingface-cli login'.",
            level="ERROR",
        )
        return False
    except HfHubHTTPError as e:
        if "401" in str(e):
            logger(f"Authentication error (401).", level="ERROR")
            logger(
                "Please ensure you are logged in via 'huggingface-cli login' and have accepted the model's terms on the Hugging Face website.",
                level="ERROR",
            )
        else:
            logger(f"An HTTP error occurred during download: {e}", level="ERROR")
        return False
    except Exception as e:
        logger(f"Failed to download model: {e}", level="ERROR")
        return False


def translate_text_with_gemma(text, logger):
    global _LOCAL_MODEL_INSTANCE, _LOADED_MODEL_PATH

    model_filename = os.getenv("GEMINI_MODEL_NAME")
    if not model_filename:
        logger("No local model selected.", level="ERROR")
        return {"status": "FAILED", "text": None}

    model_path = os.path.join(get_models_dir(), model_filename)

    try:
        if _LOADED_MODEL_PATH != model_path:
            logger(f"Loading local model: {model_filename}...")
            _LOCAL_MODEL_INSTANCE = Llama(
                model_path=model_path,
                n_ctx=LOCAL_MODEL_CONTEXT_SIZE,
                n_gpu_layers=-1,
                verbose=False,
            )
            _LOADED_MODEL_PATH = model_path
            logger("Local model loaded successfully.", level="SUCCESS")

        llm = _LOCAL_MODEL_INSTANCE

        prompt = f"""Translate the following novel chapter into English.
If the chapter has a title, enclose the translated title in double asterisks, like this: **Chapter Title**.
If the chapter has a number, preserve it in the title like this: **Chapter 1: The Beginning**.
Preserve any placeholder tags like `[IMAGE_PLACEHOLDER_N]` exactly as they appear.

---
{text}
---
"""
        chat_prompt = (
            f"<start_of_turn>user\n{prompt}<end_of_turn>\n<start_of_turn>model\n"
        )

        logger("Generating translation with local model... (This may be slow)")

        response = llm(
            chat_prompt,
            max_tokens=-1,
            stop=["<end_of_turn>", "user\n"],
            temperature=1.0,
            top_k=64,
            top_p=0.95,
            min_p=0.0,
            repeat_penalty=1.0,
        )
        translated_text = response["choices"][0]["text"]

        logger("Local translation received.", level="SUCCESS")
        return {"status": "SUCCESS", "text": translated_text}

    except Exception as e:
        logger(f"An error occurred during local inference: {e}", level="ERROR")
        _LOCAL_MODEL_INSTANCE, _LOADED_MODEL_PATH = None, None
        return {"status": "FAILED", "text": None}
