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

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
PROCESSED_FOLDER = os.path.join(BASE_DIR, "processed")

# Store Tally cached masters in %LOCALAPPDATA%\salesregister\tally_companies
LOCAL_APP_DATA = os.environ.get("LOCALAPPDATA") or os.path.expanduser(os.path.join("~", "AppData", "Local"))
TALLY_CACHE_FOLDER = os.path.join(LOCAL_APP_DATA, "salesregister", "tally_companies")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)
os.makedirs(TALLY_CACHE_FOLDER, exist_ok=True)

# Migrate existing local cache to LOCALAPPDATA if available
import shutil
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
