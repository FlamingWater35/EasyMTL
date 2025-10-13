import os
import subprocess
import shutil
import sys


def create_executable():
    main_script_path = "main.py"
    executable_name = "EasyMTL"

    output_dir = "outputs"
    build_dir = ".build_temp"

    print("--- Starting Executable Build Process ---")

    if not os.path.exists(main_script_path):
        print(f"Error: Main script not found at '{main_script_path}'.")
        sys.exit(1)

    if not os.path.exists(output_dir):
        print(f"Creating output directory at: {os.path.abspath(output_dir)}")
        os.makedirs(output_dir)

    command = [
        "pyinstaller",
        "--onefile",
        "--name",
        executable_name,
        "--distpath",
        output_dir,
        "--workpath",
        build_dir,
        "--paths",
        "src",
        main_script_path,
    ]

    print(f"\nExecuting command: {' '.join(command)}\n")

    try:
        process = subprocess.run(command, check=True, capture_output=True, text=True)
        print(process.stdout)
        print("\n--- Build Successful! ---")
        final_path = os.path.abspath(os.path.join(output_dir, f"{executable_name}.exe"))
        print(f"Executable is located at: {final_path}")

    except FileNotFoundError:
        print("\n--- Build Failed ---")
        print("Error: 'pyinstaller' command not found.")
        sys.exit(1)

    except subprocess.CalledProcessError as e:
        print("\n--- Build Failed ---")
        print("PyInstaller encountered an error during the build process.")
        print("Error details:")
        print(e.stderr)
        sys.exit(1)

    finally:
        print("\nCleaning up temporary build files...")
        if os.path.isdir(build_dir):
            shutil.rmtree(build_dir)
            print(f"Removed temporary directory: {build_dir}")

        spec_file = f"{executable_name}.spec"
        if os.path.exists(spec_file):
            os.remove(spec_file)
            print(f"Removed spec file: {spec_file}")

        print("\n--- Cleanup Complete ---")


if __name__ == "__main__":
    create_executable()
