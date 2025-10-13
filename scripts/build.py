import re
import subprocess
import os
import platform
import sys
import threading
import zipfile
from colorama import Fore, Style, init as colorama_init
import llama_cpp

colorama_init(autoreset=True)

APP_NAME = "EasyMTL"
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
EASYMTL_DIR = os.path.join(PROJECT_ROOT, "easymtl")
MAIN_SCRIPT_PATH = os.path.join(PROJECT_ROOT, "main.py")
ASSETS_DIR = os.path.join(EASYMTL_DIR, "assets")
ICON_PATH = os.path.join(ASSETS_DIR, "icon.ico")
CONFIG_PATH = os.path.join(EASYMTL_DIR, "config.py")
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")


def stream_pipe(pipe):
    try:
        for line_bytes in iter(pipe.readline, b""):
            if not line_bytes:
                break
            try:
                line = line_bytes.decode(errors="ignore").rstrip()
                if not line:
                    continue

                line_lower = line.lower()
                if 'error' in line_lower or 'failed' in line_lower:
                    prefix, color = "[ERROR] ", Fore.RED
                elif 'warn' in line_lower or 'warning' in line_lower:
                    prefix, color = "[WARN]  ", Fore.YELLOW
                else:
                    prefix, color = "[INFO]  ", Fore.GREEN
                
                print(color + prefix + line)
                sys.stdout.flush()

            except UnicodeDecodeError:
                print(Fore.RED + f"[RAW BYTES (decode error)]: {line_bytes!r}")
                sys.stdout.flush()
    except Exception:
        pass
    finally:
        if hasattr(pipe, "close") and not pipe.closed:
            pipe.close()


def run_command_realtime_colored(command_parts, step_name, cwd=PROJECT_ROOT):
    print(Style.BRIGHT + Fore.CYAN + "-" * 60)
    print(Style.BRIGHT + Fore.CYAN + f"Starting: {step_name}")
    command_str = " ".join(command_parts)
    print(Style.BRIGHT + Fore.CYAN + f"Executing: {command_str} (in {cwd})")
    print(Style.BRIGHT + Fore.CYAN + "-" * 60)

    use_shell = platform.system() == "Windows"

    try:
        process = subprocess.Popen(
            command_parts,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=use_shell,
        )

        output_thread = threading.Thread(target=stream_pipe, args=(process.stdout,))
        output_thread.start()
        output_thread.join()

        return_code = process.wait()

        if return_code != 0:
            print(Fore.RED + Style.BRIGHT + f"\nERROR: {step_name} exited with code {return_code}.")
            return False

        print(Fore.GREEN + Style.BRIGHT + f"\nCompleted: {step_name} successfully.")
        return True

    except FileNotFoundError:
        print(Fore.RED + Style.BRIGHT + f"ERROR: Command '{command_parts[0]}' not found. Make sure it's in your system's PATH.")
        return False
    except Exception as e:
        print(Fore.RED + Style.BRIGHT + f"ERROR: An unexpected error occurred during {step_name}: {e}")
        return False


def get_app_version():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            content = f.read()
            match = re.search(r"^APP_VERSION\s*=\s*['\"]([^'\"]*)['\"]", content, re.MULTILINE)
            if match:
                version = match.group(1)
                print(Style.BRIGHT + Fore.MAGENTA + f"Found App Version: {version}")
                return version
    except Exception as e:
        print(Fore.RED + f"Could not read version from config.py: {e}")
    
    print(Fore.RED + "Warning: Could not determine app version. Using '0.0.0'.")
    return "0.0.0"


def format_code():
    print(Style.BRIGHT + Fore.MAGENTA + "\n>>> Running Code Formatter...")
    if not run_command_realtime_colored(["black", EASYMTL_DIR], "Formatting with Black"):
        print(Fore.RED + "Formatting failed.")
    print(Style.BRIGHT + Fore.MAGENTA + ">>> Formatting finished.\n")


def build_application():
    app_version = get_app_version()
    print(Style.BRIGHT + Fore.MAGENTA + f"\n>>> Starting Application Build for v{app_version}...")

    llama_cpp_path = llama_cpp.__path__[0]
    llama_lib_path = os.path.join(llama_cpp_path, "lib")
    add_binary_arg = f"{llama_lib_path}{os.pathsep}llama_cpp/lib"
    log_message_text = f"Found llama_cpp binaries at: {llama_lib_path}"
    print(Style.BRIGHT + Fore.YELLOW + log_message_text)
    assets_path_arg = f"{ASSETS_DIR}{os.pathsep}easymtl/assets"

    pyinstaller_command = [
        "pyinstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--clean",
        f"--name={APP_NAME}",
        f"--icon={ICON_PATH}",
        f"--add-binary={add_binary_arg}",
        f"--add-data={assets_path_arg}",
        MAIN_SCRIPT_PATH
    ]

    if not run_command_realtime_colored(pyinstaller_command, "Building with PyInstaller"):
        print(Fore.RED + "Build failed. Check the logs above for errors.")
        return
        
    print(Style.BRIGHT + Fore.GREEN + "\nPyInstaller build completed successfully.")

    print(Style.BRIGHT + Fore.CYAN + "\n" + "-" * 60)
    print(Style.BRIGHT + Fore.CYAN + "Creating release .zip archive for updater...")
    
    exe_name = f"{APP_NAME}.exe"
    exe_path = os.path.join(DIST_DIR, exe_name)
    zip_name = f"{APP_NAME}-v{app_version}-windows.zip"
    zip_path = os.path.join(DIST_DIR, zip_name)

    if not os.path.exists(exe_path):
        print(Fore.RED + f"ERROR: {exe_name} not found in '{DIST_DIR}' after build. Cannot create zip file.")
        return

    try:
        print(Style.BRIGHT + Fore.CYAN + f"Archiving '{exe_name}' into '{zip_name}'...")
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(exe_path, arcname=exe_name)
        
        print(Fore.GREEN + "Release .zip archive created successfully.")
    except Exception as e:
        print(Fore.RED + f"ERROR: Failed to create zip file: {e}")
        return

    print(Style.BRIGHT + Fore.MAGENTA + "\n>>> Build process finished.")
    print(Style.BRIGHT + Fore.MAGENTA + f"--> The executable and release zip can be found in the '{DIST_DIR}' folder.")


def main():
    while True:
        print(Style.BRIGHT + Fore.WHITE + "\n" + "=" * 30)
        print(Style.BRIGHT + Fore.WHITE + f"    {APP_NAME} Build Script")
        print(Style.BRIGHT + Fore.WHITE + "=" * 30)
        print(Fore.CYAN + "1. Format Code (Black)")
        print(Fore.CYAN + "2. Build Application (PyInstaller)")
        print(Fore.CYAN + "3. Quit")
        print("-" * 30)

        choice = input(Fore.WHITE + "Enter your choice (1-3): ")

        if choice == "1":
            format_code()
        elif choice == "2":
            build_application()
        elif choice == "3":
            print(Fore.YELLOW + "Exiting script. Goodbye!")
            break
        else:
            print(Fore.RED + "Invalid choice. Please enter a number between 1 and 3.")


if __name__ == "__main__":
    main()