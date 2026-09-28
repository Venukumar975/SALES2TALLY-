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
    "app.py", "config.py", "routes", "services", "utils", "accounting_voucher"
]
result = subprocess.run(pyarmor_cmd, cwd=BASE_DIR)
if result.returncode != 0:
    print("[ERROR] PyArmor obfuscation failed!")
    sys.exit(result.returncode)
print("[SUCCESS] PyArmor Obfuscation Completed Successfully.")

# Step 3: Run PyInstaller Packaging on Obfuscated Source
print("\n[3/4] Packaging Desktop Executable with PyInstaller (--noconsole)...")

# Strictly required production modules used by SALES2TALLY
required_modules = [
    "flask", "werkzeug", "jinja2", "itsdangerous", "click", "blinker",
    "markupsafe", "webview", "clr_loader", "pythonnet", "openpyxl",
    "xlsxwriter", "pandas", "numpy", "requests", "urllib3", "certifi",
    "charset_normalizer"
]

excluded_modules = [
    "sklearn", "scipy", "matplotlib", "tensorflow", "keras", "torch",
    "torchvision", "torchaudio", "IPython", "jupyter", "notebook", "tensorboard",
    "boto3", "botocore", "s3fs", "fsspec", "psycopg2", "psycopg2_binary",
    "sqlalchemy", "tkinter", "_tkinter", "tcl", "tk", "PIL", "Pillow",
    "zmq", "pyzmq", "lxml", "pytest", "unittest", "pandas.tests", "numpy.tests"
]

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
    "--paths", os.path.join(BASE_DIR, "dist_obf"),
]

for mod in required_modules:
    pyinstaller_cmd.extend(["--collect-all", mod])

for ex in excluded_modules:
    pyinstaller_cmd.extend(["--exclude-module", ex])

pyinstaller_cmd.append(os.path.join(BASE_DIR, "run_desktop.py"))

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
