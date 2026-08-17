import os
import sys
import subprocess
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_EXE = sys.executable

print("=" * 70)
print("   SALES2TALLY - OBFUSCATED DESKTOP APP BUILDER")
print("=" * 70)
print(f"Python Executable : {PYTHON_EXE}")
print(f"Base Directory    : {BASE_DIR}\n")

# Step 1: Clean previous build folders
print("[1/4] Cleaning previous build folders...")
for folder in ["build", "dist", "dist_obf"]:
    fpath = os.path.join(BASE_DIR, folder)
    if os.path.exists(fpath):
        try:
            shutil.rmtree(fpath)
            print(f"  Cleaned: {folder}")
        except Exception as e:
            print(f"  Warning: could not delete {folder}: {e}")

# Step 2: Run PyArmor Obfuscation
print("\n[2/4] Running PyArmor Source Code Obfuscation...")
pyarmor_cmd = [
    PYTHON_EXE, "-m", "pyarmor.cli", "gen",
    "-O", "dist_obf",
    "-r",
    "app.py", "config.py", "routes", "services", "utils"
]
result = subprocess.run(pyarmor_cmd, cwd=BASE_DIR)
if result.returncode != 0:
    print("[ERROR] PyArmor obfuscation failed!")
    sys.exit(result.returncode)
print("[SUCCESS] PyArmor Obfuscation Completed Successfully.")

# Step 3: Run PyInstaller Packaging on Obfuscated Source
print("\n[3/4] Packaging Desktop Executable with PyInstaller (--noconsole)...")

# PyInstaller command with complete module collection
pyinstaller_cmd = [
    PYTHON_EXE, "-m", "PyInstaller",
    "--noconfirm",
    "--onedir",
    "--windowed",
    "--name", "SALES2TALLY",
    "--icon", os.path.join(BASE_DIR, "app_icon.ico"),
    "--add-data", f"{os.path.join(BASE_DIR, 'templates')};templates",
    "--add-data", f"{os.path.join(BASE_DIR, 'static')};static",
    "--add-data", f"{os.path.join(BASE_DIR, 'dist_obf')};.",
    # Include search paths for PyArmor runtime and obfuscated modules
    "--paths", os.path.join(BASE_DIR, "dist_obf"),
    # Collect all dependencies, binaries, data, and submodules
    "--collect-all", "flask",
    "--collect-all", "werkzeug",
    "--collect-all", "jinja2",
    "--collect-all", "itsdangerous",
    "--collect-all", "click",
    "--collect-all", "blinker",
    "--collect-all", "markupsafe",
    "--collect-all", "webview",
    "--collect-all", "clr_loader",
    "--collect-all", "pythonnet",
    "--collect-all", "openpyxl",
    "--collect-all", "xlsxwriter",
    "--collect-all", "pandas",
    "--collect-all", "numpy",
    "--collect-all", "requests",
    "--collect-all", "urllib3",
    "--collect-all", "certifi",
    "--collect-all", "charset_normalizer",
    os.path.join(BASE_DIR, "run_desktop.py")
]

result = subprocess.run(pyinstaller_cmd, cwd=BASE_DIR)
if result.returncode != 0:
    print("[ERROR] PyInstaller build failed!")
    sys.exit(result.returncode)

DIST_APP_DIR = os.path.join(BASE_DIR, "dist", "SALES2TALLY")

# Step 4: Verification
print("\n[4/4] Verifying Build Output...")
exe_path = os.path.join(DIST_APP_DIR, "SALES2TALLY.exe")
if os.path.exists(exe_path):
    print("[SUCCESS] Desktop Executable verified:", exe_path)
else:
    print("[ERROR] Executable missing!")
    sys.exit(1)

print("\n" + "=" * 70)
print("  SUCCESSFULLY COMPILED OBFUSCATED DESKTOP APPLICATION!")
print("=" * 70)
print(f"App Directory : {DIST_APP_DIR}")
print(f"Executable    : {exe_path}")
print("=" * 70 + "\n")
