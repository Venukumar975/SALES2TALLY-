import os
import sys
import subprocess
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

print("=== Sales & Purchase Register App - Standalone Build Script ===")
print("Python Executable:", sys.executable)
print("Base Directory:", BASE_DIR)

# Run PyInstaller via module interface
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm",
    "--onedir",
    "--windowed",
    "--name", "Sales_Register_App",
    "--add-data", f"{os.path.join(BASE_DIR, 'templates')};templates",
    "--add-data", f"{os.path.join(BASE_DIR, 'static')};static",
    "--add-data", f"{os.path.join(BASE_DIR, 'tally_companies')};tally_companies",
    os.path.join(BASE_DIR, "app.py")
]

print("\nBuilding standalone app executable...")
result = subprocess.run(cmd)

if result.returncode != 0:
    print("PyInstaller build failed!")
    sys.exit(result.returncode)

DIST_APP_DIR = os.path.join(BASE_DIR, "dist", "Sales_Register_App")

# Create runtime folders inside dist
for folder in ["uploads", "processed", "tally_companies"]:
    target = os.path.join(DIST_APP_DIR, folder)
    if not os.path.exists(target):
        os.makedirs(target)
        print(f"Created runtime folder: {target}")

# Create RUN_APP.bat inside dist folder for easy double-clicking
bat_path = os.path.join(DIST_APP_DIR, "RUN_APP.bat")
with open(bat_path, "w") as f:
    f.write('@echo off\n')
    f.write('title Sales Register App\n')
    f.write('echo Starting Sales Register App...\n')
    f.write('start "" "%~dp0Sales_Register_App.exe"\n')

print("\n" + "="*70)
print("SUCCESSFULLY BUILT STANDALONE WINDOWS APP!")
print("="*70)
print(f"LOCATION: {DIST_APP_DIR}")
print(f"LAUNCHER: {os.path.join(DIST_APP_DIR, 'Sales_Register_App.exe')}")
print("="*70 + "\n")
