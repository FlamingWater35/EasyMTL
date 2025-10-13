import sys
import os
import time
import shutil
import subprocess
import psutil

def log(message):
    with open("updater_log.txt", "a") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")

if __name__ == "__main__":
    log("Updater started.")
    
    if len(sys.argv) != 6:
        log(f"Error: Expected 5 arguments, but got {len(sys.argv) - 1}")
        log(f"Arguments: {sys.argv}")
        sys.exit(1)

    old_exe_path = sys.argv[1]
    new_exe_path = sys.argv[2]
    zip_path = sys.argv[3]
    unzip_dir = sys.argv[4]
    parent_pid = int(sys.argv[5])

    log(f"Target PID to wait for: {parent_pid}")
    log(f"Old executable: {old_exe_path}")
    log(f"New executable: {new_exe_path}")

    try:
        log(f"Waiting for process {parent_pid} to terminate...")
        parent_process = psutil.Process(parent_pid)
        parent_process.wait(timeout=10)
    except psutil.NoSuchProcess:
        log("Parent process already terminated.")
    except (psutil.TimeoutExpired, Exception) as e:
        log(f"Warning: Timed out waiting for parent process to close. Error: {e}. Proceeding anyway.")
    
    time.sleep(1)

    try:
        log(f"Replacing '{old_exe_path}' with '{new_exe_path}'...")
        shutil.move(new_exe_path, old_exe_path)
        log("Replacement successful.")
        
        log("Cleaning up temporary files...")
        if os.path.exists(unzip_dir):
            shutil.rmtree(unzip_dir)
        if os.path.exists(zip_path):
            os.remove(zip_path)
        log("Cleanup successful.")
        
    except Exception as e:
        log(f"FATAL ERROR during file operations: {e}")
        sys.exit(1)

    try:
        log(f"Relaunching application at: {old_exe_path}")
        subprocess.Popen([old_exe_path])
    except Exception as e:
        log(f"FATAL ERROR: Could not relaunch the application: {e}")
        sys.exit(1)

    log("Self-destructing updater.")
    updater_path = sys.executable
    subprocess.Popen(f'cmd.exe /c "timeout /t 1 /nobreak > nul & del "{updater_path}""', shell=True)