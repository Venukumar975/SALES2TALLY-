import os
import sys
import subprocess
import shutil

# Reconfigure stdout/stderr to utf-8 if supported
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_EXE = sys.executable

print("=" * 75)
print("   SALES2TALLY - COMPLETE BUILD & INNO SETUP INSTALLER PIPELINE")
print("=" * 75)
print(f"Python Executable : {PYTHON_EXE}")
print(f"Base Directory    : {BASE_DIR}\n")

# STEP 1: CLEAN PREVIOUS BUILD ARTIFACTS
print("[1/4] Cleaning previous build directories...")
for folder in ["build", "dist", "dist_obf", "dist_installer"]:
    fpath = os.path.join(BASE_DIR, folder)
    if os.path.exists(fpath):
        try:
            shutil.rmtree(fpath)
            print(f"  [OK] Cleaned: {folder}")
        except Exception as e:
            print(f"  [WARN] Could not delete {folder}: {e}")

# STEP 2: RUN PYARMOR SOURCE CODE OBFUSCATION
print("\n[2/4] Running PyArmor Source Code Obfuscation (Including Accounting Invoice Layer)...")
pyarmor_targets = [
    "app.py",
    "config.py",
    "routes",
    "services",
    "utils",
    "accounting_voucher"  # Accounting invoice processing & routes layer
]
pyarmor_cmd = [
    PYTHON_EXE, "-m", "pyarmor.cli", "gen",
    "-O", "dist_obf",
    "-r",
] + pyarmor_targets

print(f"  Executing PyArmor command: {' '.join(pyarmor_cmd)}")
result = subprocess.run(pyarmor_cmd, cwd=BASE_DIR)
if result.returncode != 0:
    print("\n[ERROR] PyArmor obfuscation failed!")
    sys.exit(result.returncode)
print("[SUCCESS] PyArmor Obfuscation Completed Successfully.")

# STEP 3: RUN PYINSTALLER PACKAGING ON OBFUSCATED SOURCE
print("\n[3/4] Packaging Desktop Executable with PyInstaller (--noconsole, --onedir)...")

# Strictly required production modules used by SALES2TALLY
required_modules = [
    "flask",
    "werkzeug",
    "jinja2",
    "itsdangerous",
    "click",
    "blinker",
    "markupsafe",
    "webview",
    "clr_loader",
    "pythonnet",
    "openpyxl",
    "xlsxwriter",
    "pandas",
    "pytz",
    "numpy",
    "requests",
    "urllib3",
    "certifi",
    "charset_normalizer"
]

# Explicitly exclude unnecessary and bulky ML, cloud, GUI, and database packages
excluded_modules = [
    # Machine learning / AI / scientific packages
    "sklearn",
    "scipy",
    "matplotlib",
    "tensorflow",
    "keras",
    "torch",
    "torchvision",
    "torchaudio",
    "IPython",
    "jupyter",
    "notebook",
    "tensorboard",

    # Cloud storage & AWS SDKs
    "boto3",
    "botocore",
    "s3fs",
    "fsspec",

    # Database drivers & ORMs
    "psycopg2",
    "psycopg2_binary",
    "sqlalchemy",

    # GUI toolkits (pywebview uses native Windows WebView2 Edge Chromium)
    "tkinter",
    "_tkinter",
    "tcl",
    "tk",
    "PIL",
    "Pillow",

    # Unneeded parsers, networking & test suites
    "zmq",
    "pyzmq",
    "lxml",
    "pytest",
    "unittest",
    "pandas.tests",
    "numpy.tests"
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

print("  Executing PyInstaller...")
result = subprocess.run(pyinstaller_cmd, cwd=BASE_DIR)
if result.returncode != 0:
    print("\n[ERROR] PyInstaller packaging failed!")
    sys.exit(result.returncode)

DIST_APP_DIR = os.path.join(BASE_DIR, "dist", "SALES2TALLY")
exe_path = os.path.join(DIST_APP_DIR, "SALES2TALLY.exe")

if not os.path.exists(exe_path):
    print(f"\n[ERROR] Expected executable missing: {exe_path}")
    sys.exit(1)
print(f"[SUCCESS] Desktop Executable generated: {exe_path} ({os.path.getsize(exe_path):,} bytes)")

# STEP 4: COMPILE INNO SETUP INSTALLER
print("\n[4/4] Compiling Windows Installer with Inno Setup (ISCC)...")

def find_iscc():
    candidates = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
        r"C:\Program Files\Inno Setup 5\ISCC.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    # Try PATH
    iscc_path = shutil.which("ISCC.exe") or shutil.which("iscc")
    if iscc_path:
        return iscc_path
    return None

iscc_exe = find_iscc()
if not iscc_exe:
    print("[ERROR] Inno Setup Compiler (ISCC.exe) not found on system!")
    sys.exit(1)

print(f"  Found ISCC Compiler : {iscc_exe}")
iss_file = os.path.join(BASE_DIR, "installer_setup.iss")
iscc_cmd = [iscc_exe, iss_file]

print(f"  Running Inno Setup compilation on {iss_file}...")
result = subprocess.run(iscc_cmd, cwd=BASE_DIR)
if result.returncode != 0:
    print("\n[ERROR] Inno Setup compilation failed!")
    sys.exit(result.returncode)

installer_path = os.path.join(BASE_DIR, "dist", "SALES2TALLY_Setup_v1.0.exe")
if not os.path.exists(installer_path):
    print(f"\n[ERROR] Installer output not found: {installer_path}")
    sys.exit(1)

print("\n" + "=" * 75)
print("   BUILD PIPELINE COMPLETED SUCCESSFULLY! ")
print("=" * 75)
print(f"Standalone App Directory : {DIST_APP_DIR}")
print(f"Main Executable          : {exe_path} ({os.path.getsize(exe_path):,} bytes)")
print(f"Setup Installer Executable: {installer_path} ({os.path.getsize(installer_path):,} bytes)")
print("=" * 75 + "\n")
