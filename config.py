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
TALLY_CACHE_FOLDER = os.path.join(BASE_DIR, "tally_companies")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)
os.makedirs(TALLY_CACHE_FOLDER, exist_ok=True)

def get_tally_cache_folder():
    """Keep sync data beside the app so the server can always read and write it."""
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
