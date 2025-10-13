import sys
import os
import time
import shutil
import subprocess
import psutil

def log(message):
    log_path = os.path.join(os.environ.get("TEMP", "."), "updater_log.txt")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")

if __name__ == "__main__":
    log("EasyMTL updater started.")
    
    if len(sys.argv) != 6:
        log(f"Error: Expected 5 arguments, but got {len(sys.argv) - 1}. Args: {sys.argv}")
        sys.exit(1)

    old_exe_path = sys.argv[1]
    new_exe_path = sys.argv[2]
    zip_path = sys.argv[3]
    unzip_dir = sys.argv[4]
    parent_pid = int(sys.argv[5])

    log(f"Target PID: {parent_pid}")
    log(f"Old exe: {old_exe_path}")
    log(f"New exe: {new_exe_path}")

    try:
        if psutil.pid_exists(parent_pid):
            log(f"Waiting for process {parent_pid} to terminate...")
            parent_process = psutil.Process(parent_pid)
            parent_process.wait(timeout=10)
    except psutil.NoSuchProcess:
        log("Parent process already terminated.")
    except (psutil.TimeoutExpired, Exception) as e:
        log(f"Warning: Timed out waiting for parent process. Error: {e}. Proceeding anyway.")
    
    time.sleep(1)

    old_exe_bak_path = old_exe_path + ".bak"
    try:
        log(f"Renaming '{old_exe_path}' to '{old_exe_bak_path}'...")
        os.rename(old_exe_path, old_exe_bak_path)
        log("Rename successful.")

        log(f"Moving '{new_exe_path}' to '{old_exe_path}'...")
        shutil.move(new_exe_path, old_exe_path)
        log("Move successful.")

    except Exception as e:
        log(f"FATAL ERROR during file replacement: {e}")
        if os.path.exists(old_exe_bak_path) and not os.path.exists(old_exe_path):
            os.rename(old_exe_bak_path, old_exe_path)
        sys.exit(1)

    try:
        log("Cleaning up temporary download files...")
        if os.path.exists(unzip_dir):
            shutil.rmtree(unzip_dir, ignore_errors=True)
        if os.path.exists(zip_path):
            os.remove(zip_path)
        log("Cleanup successful.")
    except Exception as e:
        log(f"Warning: Could not clean up temp files: {e}")

    try:
        log(f"Relaunching application: {old_exe_path}")
        subprocess.Popen([old_exe_path])
    except Exception as e:
        log(f"FATAL ERROR: Could not relaunch the application: {e}")
        sys.exit(1)

    log("Scheduling self-destruction...")
    updater_path = sys.executable
    cleanup_command = (
        f'cmd.exe /c "timeout /t 5 /nobreak > nul & del "{old_exe_bak_path}" & del "{updater_path}""'
    )
    subprocess.Popen(cleanup_command, shell=True)
    
    log("Updater finished its job and is now exiting.")
    sys.exit(0)