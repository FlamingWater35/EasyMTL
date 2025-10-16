# 📖 EasyMTL: AI-Powered EPUB Translator

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub release (latest by date)](https://img.shields.io/github/v/release/FlamingWater35/EasyMTL)](https://github.com/FlamingWater35/EasyMTL/releases)

Translate your e-books effortlessly using powerful cloud and local AI models.

EasyMTL is a tool designed to quickly and accurately translate EPUB files. It preserves the book's structure, including images.

> **Important**: As AI can make mistakes (and Gemini models are prone to censorship), the app features a proofreading tool that is recommended to run in order to maintain high-quality translations. Slight manual editing might be needed. The proofreading tool is optimized to specially target languages using non-English characters. Translating from other languages is not recommended because Gemini typically leaves censored phrases untranslated without any notice, which is complex to detect.

## ✨ Features

- **Dual Translation Engines**:
  - **Cloud**: Utilizes powerful Gemini models (for example, Gemini 2.5 Pro) via API for high-quality translations.
  - **Local**: Can also run translations completely offline using models like Gemma 3 and Mistral on your own hardware.

- **Built-in EPUB Tools**:
  - **Cover Page Generator**: A one-click tool to create a properly formatted, full-page cover for your EPUBs using the image from the book's metadata.
  - **Proofreading Tool**: A quick tool to find all non-English characters and missing end marks, which then opens a file with detected issues and their locations for easy manual editing.

- **User-Friendly GUI**:
  - **Intuitive Interface**: A clean and simple interface built with DearPyGUI.
  - **Real-Time Feedback**: A detailed log, progress bar, elapsed time, and ETA throughout the translation process.
  - **Self-Updating Mechanism**: The application can check for new versions on GitHub and automatically download and install updates.

- **And some more technical features, including:**
  - **Intelligent Processing**:
    - **Token-Aware Batching**: Automatically groups chapters into optimal chunks to maximize speed and avoid cloud API token limits.
    - **Adaptive Chunking**: If a model's output is truncated, the app automatically splits the failed chunk and retries, ensuring no content is lost.
    - **Robust Error Handling**: Automatically retries failed API calls and gracefully handles model inconsistencies.

  - **Local Model Management**:
    - **Downloader**: Browse and download optimized GGUF-format models directly from Hugging Face within the app.
    - **Manager**: Easily switch between different downloaded local models or delete them to save space.

  - **EPUB Integrity**:
    - **Structure Preservation**: The original EPUB structure, including images, is fully preserved in the translated output.
    - **Formatted Output**: Translated chapters are generated with clean HTML and a consistent stylesheet for a pleasant reading experience.

## 📸 Screenshots

<table width="100%">
  <tr>
    <td align="center">
      <p><b>Main Interface</b></p>
      <img src="screenshots\Screenshot 2025-10-13 221645.png" alt="Main application interface" width="400">
    </td>
    <td align="center">
      <p><b>Local Model Manager</b></p>
      <img src="screenshots\Screenshot 2025-10-13 222039.png" alt="Local model management window" width="400">
    </td>
  </tr>
  <tr>
    <td align="center">
      <p><b>Cloud Model Selection</b></p>
      <img src="screenshots\Screenshot 2025-10-13 222242.png" alt="Cloud model selection window" width="400">
    </td>
    <td align="center">
      <p><b>Cover Creation Tool</b></p>
      <img src="screenshots\Screenshot 2025-10-13 231314.png" alt="Cover creation tool" width="400">
    </td>
  </tr>
</table>

## 🚀 Installation From Source

Follow these steps to get the application running from source. (Note that Linux isn't yet supported despite the mentions)

### 1. Prerequisites

- Python 3.9 or newer.
- Git for cloning the repository.
- (Optional but Recommended) C++ build tools for `llama-cpp-python` GPU support (for example, Visual Studio Build Tools on Windows, `build-essential` on Linux).

#### 2. Clone the Repository

```bash
git clone https://github.com/FlamingWater35/EasyMTL.git
cd EasyMTL
```

#### 3. Set Up a Virtual Environment (Recommended)

```bash
# Create a virtual environment
python -m venv venv

# Activate it
# On Windows:
.\venv\Scripts\activate
# On Linux:
source venv/bin/activate
```

#### 4. Install Dependencies

Install all the required Python packages.

```bash
pip install -r requirements.txt
```

> **Note:** The `llama-cpp-python` installation can be slow as it may need to compile C++ code.

#### 5. Configuration

- **For Cloud Models (Gemini)**:
    1. Run the application.
    2. Go to `Settings > Set API Key`.
    3. Paste your Google AI Studio API key and click "Save".

- **For Local Models**:
  - **Note that these steps may not be necessary:**
    1. Make sure you have a [Hugging Face](https://huggingface.co/) account.
    2. Visit the page of a gated model you wish to download (e.g., [Gemma 2 on Hugging Face](https://huggingface.co/bartowski/gemma-2-2b-it-GGUF/)) and accept the terms.
    3. Log in via your terminal. This is a one-time setup:

        ```bash
        huggingface-cli login
        ```

        Paste your Hugging Face access token when prompted.

## 💻 Usage

1. Run the application:

    ```bash
    python main.py
    ```

2. **Select a Model**:
    - For **cloud translation**, go to `Settings > Select Model` to choose a Gemini model.
    - For **local translation**, go to `Local Models > Manage Models` to download or select a model for local use.
3. **Select EPUB**: Click "Browse..." to choose the EPUB file you want to translate.
4. **Choose Chapters**: Set the start and end chapters for the translation.
5. **Start**: Click "Start Translation" and enjoy some tea while the operation is running.

The translated EPUB file will be saved in the same directory as the original, with `_translated` appended to its name.

## 🛠️ Building from Source

A fully ready build script is provided in the `/scripts` folder to build the app into an executable and .zip archive.

1. Navigate to the project root.
2. Run the build script:

    ```bash
    python scripts/build.py
    ```

3. Choose "Build Application" from the menu by inputting `2`

## 📄 License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## 🙏 Acknowledgments

Thanks to these open-source libraries, my life is so much easier:

- [DearPyGUI](https://github.com/hoffstadt/DearPyGUI)
- [ebooklib](https://github.com/aerkalov/ebooklib)
- [google-genai](https://github.com/googleapis/python-genai)
- [llama-cpp-python](https://github.com/abetlen/llama-cpp-python)
- [Hugging Face Hub](https://github.com/huggingface/huggingface_hub)
