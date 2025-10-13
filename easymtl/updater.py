import os
import subprocess
import sys
import tempfile
import threading
import zipfile
import requests
from easymtl.config import APP_VERSION, GITHUB_REPO
from easymtl.utils import log_message
import dearpygui.dearpygui as dpg


def run_update_check_process():
    if not GITHUB_REPO or "YourUsername" in GITHUB_REPO:
        log_message(
            "GitHub repository is not configured. Cannot check for updates.",
            level="ERROR",
        )
        if dpg.is_dearpygui_running():
            dpg.set_value("update_status_text", "Update check is not configured.")
        return

    try:
        log_message("Checking for updates...")
        if dpg.is_dearpygui_running():
            dpg.configure_item("check_for_updates_button", enabled=False)
            dpg.set_value("update_status_text", "Checking for new versions...")

        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()

        latest_release = response.json()
        latest_version = latest_release.get("tag_name", "0.0.0").lstrip("v")

        log_message(f"Current version: {APP_VERSION}, Latest version: {latest_version}")

        if latest_version > APP_VERSION:
            log_message(f"Update available: Version {latest_version}", level="SUCCESS")
            asset_url = None
            for asset in latest_release.get("assets", []):
                if asset["name"].endswith(".zip"):
                    asset_url = asset["browser_download_url"]
                    break

            if asset_url and dpg.is_dearpygui_running():
                dpg.set_value(
                    "update_status_text", f"New version {latest_version} is available!"
                )
                dpg.set_value("update_url_storage", asset_url)
                dpg.configure_item("download_update_button", show=True)
            elif dpg.is_dearpygui_running():
                dpg.set_value(
                    "update_status_text",
                    f"Version {latest_version} found, but no .zip asset was found.",
                )
        else:
            log_message("You are running the latest version.", level="SUCCESS")
            if dpg.is_dearpygui_running():
                dpg.set_value(
                    "update_status_text", "You are already on the latest version."
                )

    except requests.exceptions.RequestException as e:
        log_message(f"Could not check for updates: {e}", level="ERROR")
        if dpg.is_dearpygui_running():
            dpg.set_value("update_status_text", "Failed to connect to GitHub.")
    except Exception as e:
        log_message(f"An error occurred while checking for updates: {e}", level="ERROR")
        if dpg.is_dearpygui_running():
            dpg.set_value("update_status_text", "An unexpected error occurred.")
    finally:
        if dpg.is_dearpygui_running():
            dpg.configure_item("check_for_updates_button", enabled=True)


def run_download_and_update_process(url):
    try:
        if dpg.is_dearpygui_running():
            dpg.configure_item("download_update_button", enabled=False)
            dpg.configure_item("update_loading_indicator", show=True)
            dpg.set_value("update_status_text", "Downloading update...")

        temp_dir = tempfile.gettempdir()
        download_path = os.path.join(temp_dir, "update.zip")

        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(download_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        log_message("Download complete. Preparing to update...", level="SUCCESS")
        if dpg.is_dearpygui_running():
            dpg.set_value("update_status_text", "Download complete. Unpacking...")

        unzip_dir = os.path.join(temp_dir, "update_unzipped")
        with zipfile.ZipFile(download_path, "r") as zip_ref:
            zip_ref.extractall(unzip_dir)

        new_exe_path = os.path.join(unzip_dir, f"{os.path.basename(sys.executable)}")
        if not os.path.exists(new_exe_path):
            log_message(
                "Update failed: New executable not found in the downloaded zip file.",
                level="ERROR",
            )
            if dpg.is_dearpygui_running():
                dpg.set_value("update_status_text", "Update failed: Invalid zip file.")
            return

        current_exe_path = sys.executable
        updater_path = os.path.join(temp_dir, "updater.bat")

        updater_script = f"""
@echo off
echo [Updater] Waiting for EasyMTL to close...
timeout /t 3 /nobreak > nul
echo [Updater] Replacing application file...
move /Y "{new_exe_path}" "{current_exe_path}"
echo [Updater] Cleaning up downloaded files...
rd /s /q "{unzip_dir}"
del "{download_path}"
echo [Updater] Relaunching application...
start "" "{current_exe_path}"
echo [Updater] Self-destructing...
(goto) 2>nul & del "%~f0"
"""
        with open(updater_path, "w") as f:
            f.write(updater_script)

        log_message(
            "Updater created. The application will now close and update.",
            level="WARNING",
        )
        if dpg.is_dearpygui_running():
            dpg.set_value("update_status_text", "Restarting to apply update...")

        subprocess.Popen([updater_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
        sys.exit(0)

    except Exception as e:
        log_message(f"Update failed: {e}", level="ERROR")
        if dpg.is_dearpygui_running():
            dpg.set_value("update_status_text", "Update failed. See logs for details.")
            dpg.configure_item("update_loading_indicator", show=False)
            dpg.configure_item("download_update_button", enabled=True)


def start_update_check_thread():
    thread = threading.Thread(target=run_update_check_process)
    thread.start()


def start_download_and_update_thread(url):
    thread = threading.Thread(target=run_download_and_update_process, args=(url,))
    thread.start()
