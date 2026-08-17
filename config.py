import os
import sys

# Configure dynamic directories for standalone PyInstaller EXE or local Python
if getattr(sys, 'frozen', False):
    # Running as compiled PyInstaller executable
    EXE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, '_MEIPASS', EXE_DIR)
    BASE_DIR = EXE_DIR
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = BUNDLE_DIR

TEMPLATE_FOLDER = os.path.join(BUNDLE_DIR, "templates")
STATIC_FOLDER = os.path.join(BUNDLE_DIR, "static")

LOCAL_APP_DATA = os.environ.get("LOCALAPPDATA") or os.path.expanduser(os.path.join("~", "AppData", "Local"))
APP_DATA_DIR = os.path.join(LOCAL_APP_DATA, "SALES2TALLY")
TALLY_CACHE_FOLDER = os.path.join(APP_DATA_DIR, "tally_companies")

# Temporary ephemeral directories in LocalAppData (flushed automatically)
TEMP_FOLDER = os.path.join(APP_DATA_DIR, "temp")
UPLOAD_FOLDER = os.path.join(TEMP_FOLDER, "uploads")
PROCESSED_FOLDER = os.path.join(TEMP_FOLDER, "processed")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)
os.makedirs(TALLY_CACHE_FOLDER, exist_ok=True)

import shutil

# Migrate from previous salesregister folder if present
_legacy_salesregister = os.path.join(LOCAL_APP_DATA, "salesregister")
if os.path.exists(_legacy_salesregister):
    for _sub in ["tally_companies", "license.lic"]:
        _src = os.path.join(_legacy_salesregister, _sub)
        _dst = os.path.join(APP_DATA_DIR, _sub)
        if os.path.exists(_src) and not os.path.exists(_dst):
            try:
                if os.path.isdir(_src):
                    shutil.copytree(_src, _dst)
                else:
                    shutil.copy2(_src, _dst)
            except Exception:
                pass

def cleanup_temp_files():
    """Flush out all temporary uploaded and processed files."""
    for folder in (UPLOAD_FOLDER, PROCESSED_FOLDER):
        if os.path.exists(folder):
            for fname in os.listdir(folder):
                fpath = os.path.join(folder, fname)
                try:
                    if os.path.isfile(fpath):
                        os.remove(fpath)
                    elif os.path.isdir(fpath):
                        shutil.rmtree(fpath)
                except Exception:
                    pass

# One-time cleanup of legacy project root uploads/processed folders if present
for _legacy in (os.path.join(BASE_DIR, "uploads"), os.path.join(BASE_DIR, "processed")):
    if os.path.exists(_legacy) and os.path.isdir(_legacy):
        try:
            shutil.rmtree(_legacy)
        except Exception:
            pass

# Migrate existing local cache to LOCALAPPDATA if available
_old_cache_folder = os.path.join(BASE_DIR, "tally_companies")
if os.path.exists(_old_cache_folder):
    for _item in os.listdir(_old_cache_folder):
        _src = os.path.join(_old_cache_folder, _item)
        _dst = os.path.join(TALLY_CACHE_FOLDER, _item)
        if os.path.isdir(_src) and not os.path.exists(_dst):
            try:
                shutil.copytree(_src, _dst)
            except Exception:
                pass

def get_tally_cache_folder():
    """Returns the persistent Tally company cache directory in LocalAppData."""
    os.makedirs(TALLY_CACHE_FOLDER, exist_ok=True)
    return TALLY_CACHE_FOLDER

# Standardized 14 target columns
TARGET_COLUMNS = [
    "Invoice Date",
    "Invoice No",
    "Party Name",
    "GST no",
    "State Name",
    "Product",
    "HSN Code",
    "Qty",
    "Taxable Amount",
    "CGST Amount",
    "SGST Amount",
    "IGST Amount",
    "Total Amount",
    "UOM"
]

TALLY_URL = "http://localhost:9000"
