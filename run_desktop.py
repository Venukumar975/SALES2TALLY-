# Bootstrap launcher for SALES2TALLY
# Registers all dependencies and logs startup lifecycle to %LOCALAPPDATA%\SALES2TALLY\app.log

import os
import sys
import traceback
from datetime import datetime

# Setup persistent LocalAppData log path
LOCAL_APP_DATA = os.environ.get("LOCALAPPDATA") or os.path.expanduser(os.path.join("~", "AppData", "Local"))
LOG_DIR = os.path.join(LOCAL_APP_DATA, "SALES2TALLY")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

try:
    os.makedirs(LOG_DIR, exist_ok=True)
    # Clear previous logs on startup so each session starts fresh
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")
except Exception:
    pass

def log_event(message: str, level: str = "INFO"):
    """Write timestamped log event to %LOCALAPPDATA%\\SALES2TALLY\\app.log"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] [{level.upper()}] {message}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted)
    except Exception:
        pass

log_event("=" * 60)
log_event("SALES2TALLY Launcher Initialized")
log_event(f"Executable Path: {sys.executable}")
log_event(f"Frozen Mode: {getattr(sys, 'frozen', False)}")

# Core Web & UI frameworks
log_event("Pre-loading third-party runtime frameworks...")
try:
    import flask
    import werkzeug
    import jinja2
    import itsdangerous
    import click
    import blinker
    import markupsafe
    import webview
    import clr_loader
    import pythonnet

    # Data & Excel engines
    try:
        import pytz
        if not hasattr(pytz, "__version__") or not pytz.__version__:
            pytz.__version__ = "2026.4"
    except Exception:
        pass
    import pandas
    import numpy
    import openpyxl
    import xlsxwriter
    import requests
    import urllib3
    import certifi
    import charset_normalizer
    import winreg
    log_event("All framework dependencies verified successfully.")
except Exception as e:
    log_event(f"Failed to import dependencies: {e}\n{traceback.format_exc()}", level="FATAL")

import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        log_event("Importing obfuscated application core (app.py)...")
        import app
        log_event("Invoking app.main() to start background Flask and WebView...")
        app.main()
        log_event("SALES2TALLY application closed normally.")
    except Exception as e:
        log_event(f"Unhandled startup/runtime exception: {e}\n{traceback.format_exc()}", level="FATAL")
        with open(os.path.join(LOG_DIR, "crash.log"), "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
