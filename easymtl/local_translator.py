import os
import re
import io
from tqdm import tqdm
from llama_cpp import Llama
from huggingface_hub import hf_hub_download
from huggingface_hub.utils import GatedRepoError, HfHubHTTPError
import dearpygui.dearpygui as dpg
from .utils import get_models_dir
from .config import LOCAL_MODEL_CONTEXT_SIZE

_LOCAL_MODEL_INSTANCE = None
_LOADED_MODEL_PATH = None


class TqdmProgressUpdater(io.StringIO):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.progress = 0

    def write(self, s):
        match = re.search(r"(\d+)%", s)
        if match:
            new_progress = int(match.group(1))
            if new_progress > self.progress:
                self.progress = new_progress
                if dpg.is_dearpygui_running():
                    dpg.set_value("download_progress_bar", self.progress / 100.0)


def download_model_from_hub(repo_id, filename, logger):
    models_dir = get_models_dir()

    try:
        logger(f"Starting download of {filename} from {repo_id}...")

        with tqdm(
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            miniters=1,
            file=TqdmProgressUpdater(),
        ) as t:
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=models_dir,
                local_dir_use_symlinks=False,
                resume_download=True,
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
                n_gpu_layers=0, # Set > 0 to use GPU
                verbose=False
            )
            _LOADED_MODEL_PATH = model_path
            logger("Local model loaded successfully.", level="SUCCESS")
        
        llm = _LOCAL_MODEL_INSTANCE
        prompt = f"<start_of_turn>user\n{text}<end_of_turn>\n<start_of_turn>model\n"
        
        logger("Generating translation with local model... (This may be slow)")
        response = llm(
            prompt, 
            max_tokens=-1,
            stop=["<end_of_turn>"],
            temperature=1.0,
            top_k=64,
            top_p=0.95,
            min_p=0.0,
            repeat_penalty=1.0
        )
        translated_text = response['choices'][0]['text']

        logger("Local translation received.", level="SUCCESS")
        return {"status": "SUCCESS", "text": translated_text}

    except Exception as e:
        logger(f"An error occurred during local inference: {e}", level="ERROR")
        _LOCAL_MODEL_INSTANCE, _LOADED_MODEL_PATH = None, None
        return {"status": "FAILED", "text": None}


def count_tokens_locally(text):
    if not _LOCAL_MODEL_INSTANCE:
        return len(text) // 3
    try:
        return len(_LOCAL_MODEL_INSTANCE.tokenize(text.encode("utf-8")))
    except Exception:
        return len(text) // 3
