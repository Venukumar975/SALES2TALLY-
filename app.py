import sys
import os
import re
import uuid
import math
import requests
import json
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as xml_escape
from datetime import datetime
import pandas as pd
from flask import Flask, request, jsonify, render_template, send_from_directory

app = Flask(__name__, template_folder="templates")

# Configure directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
PROCESSED_FOLDER = os.path.join(BASE_DIR, "processed")
TALLY_CACHE_FOLDER = os.path.join(BASE_DIR, "tally_companies")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

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

def find_headers_and_df(file_path, sheet_name, header_row=None):
    """
    Parses headers from the Excel sheet starting at the exact user-specified header_row (1-based index).
    Defaults to 1 if not specified.
    """
    if header_row is None:
        header_row = 1
        
    df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
    if df_raw.empty:
        return [], df_raw
        
    try:
        best_row_idx = int(header_row) - 1
        if best_row_idx < 0:
            best_row_idx = 0
    except (ValueError, TypeError):
        best_row_idx = 0
        
    if best_row_idx >= len(df_raw):
        best_row_idx = len(df_raw) - 1
            
    # Extract headers
    headers = [str(x).strip() for x in df_raw.iloc[best_row_idx].tolist()]
    
    # Clean and resolve duplicate/empty headers
    cleaned_headers = []
    seen = {}
    for idx, h in enumerate(headers):
        if not h or h.lower() == 'nan':
            h_clean = f"Unnamed_Col_{idx}"
        else:
            h_clean = h
            
        if h_clean in seen:
            seen[h_clean] += 1
            h_clean = f"{h_clean}_{seen[h_clean]}"
        else:
            seen[h_clean] = 0
            
        cleaned_headers.append(h_clean)
        
    # Re-slice DataFrame starting from rows below the header
    df_data = df_raw.iloc[best_row_idx + 1:].copy()
    df_data.columns = cleaned_headers
    df_data = df_data.reset_index(drop=True)
    
    return cleaned_headers, df_data

def clean_gst_cell(v):
    if pd.isna(v):
        return None
    s = str(v).strip()
    if s.lower() in ('nan', 'none', 'null', '0', '0.0', ''):
        return None
    return s

def clean_date_cell(v):
    if pd.isna(v):
        return None
    if isinstance(v, (datetime, pd.Timestamp)):
        return v.strftime('%d-%m-%Y')
    
    s = str(v).strip()
    if s.lower() in ('nan', 'none', 'null', ''):
        return None
    
    # Try common formats
    for fmt in ('%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d', '%d-%b-%y', '%d-%b-%Y'):
        try:
            return pd.to_datetime(s, dayfirst=True).strftime('%d-%m-%Y')
        except:
            continue
    return s

def parse_date_to_comparable(v):
    if pd.isna(v):
        return None
    if isinstance(v, (datetime, pd.Timestamp)):
        return v.date()
    s = str(v).strip()
    if s.lower() in ('nan', 'none', 'null', ''):
        return None
    # Try parsing with specific formats first to avoid dayfirst ambiguity
    for fmt in ('%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d', '%d-%b-%y', '%d-%b-%Y'):
        try:
            dt = pd.to_datetime(s, format=fmt, errors='raise')
            return dt.date()
        except:
            continue
    try:
        dt = pd.to_datetime(s, dayfirst=True, errors='raise')
        if pd.isna(dt):
            return None
        return dt.date()
    except:
        return None

def filter_df_by_date_range(df_data, mappings, from_date_str, to_date_str):
    if df_data.empty:
        return df_data
    src_date_col = mappings.get("Invoice Date")
    if not src_date_col or src_date_col not in df_data.columns:
        return df_data
    
    from_dt = None
    to_dt = None
    if from_date_str:
        try:
            from_dt = datetime.strptime(from_date_str, "%Y-%m-%d").date()
        except Exception as e:
            print(f"Error parsing from_date: {e}")
    if to_date_str:
        try:
            to_dt = datetime.strptime(to_date_str, "%Y-%m-%d").date()
        except Exception as e:
            print(f"Error parsing to_date: {e}")
            
    if not from_dt and not to_dt:
        return df_data
        
    def is_in_range(val):
        d = parse_date_to_comparable(val)
        if d is None:
            return False
        if from_dt and d < from_dt:
            return False
        if to_dt and d > to_dt:
            return False
        return True
        
    return df_data[df_data[src_date_col].apply(is_in_range)].copy()


def clean_numeric_cell(v):
    if pd.isna(v):
        return None
    s = str(v).replace(',', '').strip()
    if s.lower() in ('nan', 'none', 'null', ''):
        return None
    try:
        val = float(s)
        if val.is_integer():
            return int(val)
        return val
    except ValueError:
        return v

def clean_text_cell(v):
    if pd.isna(v):
        return None
    s = str(v).strip()
    if s.lower() in ('nan', 'none', 'null', ''):
        return None
    # Fix pandas reading integers as float (e.g. HSN Code 96190010.0 -> 96190010)
    if s.endswith('.0') and s[:-2].replace('-', '').isdigit():
        return s[:-2]
    return s

def escape_xml_value(value):
    """Return text safe for interpolation into Tally XML elements and attributes."""
    if value is None:
        return ""
    return xml_escape(str(value), {'"': '&quot;', "'": '&apos;'})

def normalize_party_name(value):
    """Create a Tally-friendly party name from an Excel party name."""
    if value is None:
        return ""

    name = str(value).strip()
    replacements = {
        "&": " and ",
        "+": " plus ",
        "@": " at ",
    }
    for symbol, word in replacements.items():
        name = name.replace(symbol, word)

    # Keep letters, numbers and spaces only. This prevents punctuation from
    # producing invalid or inconsistently named Tally ledgers.
    name = re.sub(r"[^A-Za-z0-9\s]", " ", name)
    return re.sub(r"\s+", " ", name).strip()

def clean_and_tokenize(name):
    if not name:
        return []
    name = str(name).lower()
    # Replace non-alphanumeric characters with space
    name = re.sub(r'[^a-z0-9\s]', ' ', name)
    # Strip common business suffixes
    suffixes = ['pvt', 'ltd', 'private', 'limited', 'llp', 'co', 'company', 'and']
    for suffix in suffixes:
        name = re.sub(rf'\b{suffix}\b', ' ', name)
    return [w.strip() for w in name.split() if w.strip()]

def get_word_match_score(name1, name2):
    w1 = set(clean_and_tokenize(name1))
    w2 = set(clean_and_tokenize(name2))
    if not w1 or not w2:
        return 0.0
    intersection = w1.intersection(w2)
    union = w1.union(w2)
    return len(intersection) / len(union)

def compact_party_name(name):
    """Compare names without spacing or punctuation-only differences."""
    if not name:
        return ""
    return re.sub(r'[^a-z0-9]', '', str(name).lower())

@app.route("/api/tally/sync", methods=["POST"])
def api_tally_sync():
    data = request.json or {}
    company_name = data.get("company_name", "").strip()
    if not company_name:
        return jsonify({"success": False, "error": "Company Name is required"}), 400
        
    tally_url = "http://localhost:9000"
    ledger_xml = """<ENVELOPE>
        <HEADER>
            <VERSION>1</VERSION>
            <TALLYREQUEST>Export Data</TALLYREQUEST>
            <TYPE>Collection</TYPE>
            <ID>Ledger</ID>
        </HEADER>
        <BODY>
            <DESC>
                <STATICVARIABLES>
                    <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                </STATICVARIABLES>
            </DESC>
        </BODY>
    </ENVELOPE>"""
    
    def clean_tally_xml(content_bytes):
        text = content_bytes.decode("utf-8", errors="ignore")
        def repl(match):
            ent = match.group(0)
            try:
                if ent.startswith("&#x"):
                    v = int(ent[3:-1], 16)
                else:
                    v = int(ent[2:-1])
                if v < 32 and v not in (9, 10, 13):
                    return ""
            except:
                pass
            return ent
        cleaned = re.sub(r'&#x?[0-9a-fA-F]+;', repl, text)
        return cleaned.encode("utf-8", errors="ignore")

    try:
        # 20 minutes timeout
        r = requests.post(tally_url, data=ledger_xml, timeout=1200)
        if r.status_code != 200:
            return jsonify({"success": False, "error": f"Tally server responded with status {r.status_code}"}), 400
            
        root = ET.fromstring(clean_tally_xml(r.content))
        ledgers = []
        for ledger_el in root.findall(".//LEDGER"):
            name = ledger_el.get("NAME") or ledger_el.findtext("NAME")
            if name:
                ledgers.append(name.strip())
                
        if not ledgers:
            for name_el in root.findall(".//NAME"):
                if name_el.text:
                    ledgers.append(name_el.text.strip())
                    
        ledgers = sorted(list(set(ledgers)))
        if not ledgers:
            return jsonify({"success": False, "error": "No ledgers were retrieved. Verify that a company is open in Tally Prime."}), 400
            
        cache_dir = get_tally_cache_folder()
        
        safe_company_name = re.sub(r'[\\/*?:"<>|]', "", company_name).strip()
        company_folder = os.path.join(cache_dir, safe_company_name)
        os.makedirs(company_folder, exist_ok=True)
        
        cache_path = os.path.join(company_folder, "tally_ledger_cache.json")
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({
                "company_name": company_name,
                "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ledgers": ledgers
            }, f, indent=4)
            
        return jsonify({
            "success": True,
            "count": len(ledgers),
            "company_name": company_name
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to sync with Tally: {e}"}), 500

@app.route("/api/tally/companies", methods=["GET"])
def api_tally_companies():
    try:
        cache_dir = get_tally_cache_folder()
        if not os.path.exists(cache_dir):
            return jsonify({"success": True, "companies": []})
            
        companies_map = {}
        for item in os.listdir(cache_dir):
            item_path = os.path.join(cache_dir, item)
            if os.path.isdir(item_path):
                display_name = item
                ledger_last_sync = ""
                stock_last_sync = ""
                has_ledgers = False
                has_stock = False
                ledger_count = 0
                stock_count = 0
                
                ledger_cache = os.path.join(item_path, "tally_ledger_cache.json")
                if os.path.exists(ledger_cache):
                    try:
                        with open(ledger_cache, "r", encoding="utf-8") as f:
                            c_data = json.load(f)
                            display_name = c_data.get("company_name", display_name)
                            ledger_last_sync = c_data.get("last_sync", "")
                            ledger_count = len(c_data.get("ledgers", []))
                            has_ledgers = True
                    except:
                        pass
                        
                stock_cache = os.path.join(item_path, "tally_stock_cache.json")
                if os.path.exists(stock_cache):
                    try:
                        with open(stock_cache, "r", encoding="utf-8") as f:
                            c_data = json.load(f)
                            display_name = c_data.get("company_name", display_name)
                            stock_last_sync = c_data.get("last_sync", "")
                            stock_count = len(c_data.get("items", []))
                            has_stock = True
                    except:
                        pass
                        
                if has_ledgers or has_stock:
                    companies_map[item] = {
                        "safe_name": item,
                        "display_name": display_name,
                        "ledger_last_sync": ledger_last_sync,
                        "stock_last_sync": stock_last_sync,
                        "has_ledgers": has_ledgers,
                        "has_stock": has_stock,
                        "ledger_count": ledger_count,
                        "stock_count": stock_count
                    }
                    
        return jsonify({"success": True, "companies": list(companies_map.values())})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/tally/ledgers", methods=["POST"])
def get_tally_ledgers():
    data = request.json or {}
    company_name = data.get("company_name", "").strip()
    if not company_name:
        return jsonify({"success": False, "error": "Company name is required"}), 400
        
    safe_co = re.sub(r'[\\/*?:"<>|]', "", company_name).strip()
    cache_path = os.path.join(get_tally_cache_folder(), safe_co, "tally_ledger_cache.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                return jsonify({"success": True, "ledgers": cache_data.get("ledgers", [])})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
            
    return jsonify({"success": True, "ledgers": []})

@app.route("/api/tally/sync-stock", methods=["POST"])
def api_tally_sync_stock():
    data = request.json or {}
    company_name = data.get("company_name", "").strip()
    if not company_name:
        return jsonify({"success": False, "error": "Company Name is required"}), 400
        
    tally_url = "http://localhost:9000"
    stock_xml = """<ENVELOPE>
        <HEADER>
            <VERSION>1</VERSION>
            <TALLYREQUEST>Export Data</TALLYREQUEST>
            <TYPE>Collection</TYPE>
            <ID>StockItem</ID>
        </HEADER>
        <BODY>
            <DESC>
                <STATICVARIABLES>
                    <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                </STATICVARIABLES>
            </DESC>
        </BODY>
    </ENVELOPE>"""
    
    def clean_tally_xml(content_bytes):
        text = content_bytes.decode("utf-8", errors="ignore")
        def repl(match):
            ent = match.group(0)
            try:
                if ent.startswith("&#x"):
                    v = int(ent[3:-1], 16)
                else:
                    v = int(ent[2:-1])
                if v < 32 and v not in (9, 10, 13):
                    return ""
            except:
                pass
            return ent
        cleaned = re.sub(r'&#x?[0-9a-fA-F]+;', repl, text)
        return cleaned.encode("utf-8", errors="ignore")

    try:
        # 20 minutes timeout
        r = requests.post(tally_url, data=stock_xml, timeout=1200)
        if r.status_code != 200:
            return jsonify({"success": False, "error": f"Tally server responded with status {r.status_code}"}), 400
            
        root = ET.fromstring(clean_tally_xml(r.content))
        items = []
        for item_el in root.findall(".//STOCKITEM"):
            name = item_el.get("NAME") or item_el.findtext("NAME")
            if name:
                items.append(name.strip())
                
        if not items:
            for name_el in root.findall(".//NAME"):
                if name_el.text:
                    items.append(name_el.text.strip())
                    
        items = sorted(list(set(items)))
        if not items:
            return jsonify({"success": False, "error": "No stock items were retrieved. Verify that a company is open in Tally Prime."}), 400
            
        cache_dir = get_tally_cache_folder()
        
        safe_company_name = re.sub(r'[\\/*?:"<>|]', "", company_name).strip()
        company_folder = os.path.join(cache_dir, safe_company_name)
        os.makedirs(company_folder, exist_ok=True)
        
        cache_path = os.path.join(company_folder, "tally_stock_cache.json")
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({
                "company_name": company_name,
                "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "items": items
            }, f, indent=4)
            
        return jsonify({
            "success": True,
            "count": len(items),
            "company_name": company_name
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to sync with Tally: {e}"}), 500

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("excel_file")
    if not file:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
        
    try:
        file_id = str(uuid.uuid4())
        ext = os.path.splitext(file.filename)[1]
        if ext.lower() not in ('.xlsx', '.xls'):
            return jsonify({"success": False, "error": "Invalid file format. Please upload .xlsx or .xls"}), 400
            
        file_path = os.path.join(UPLOAD_FOLDER, f"{file_id}{ext}")
        file.save(file_path)
        
        # Read sheet names
        xl = pd.ExcelFile(file_path)
        sheets = xl.sheet_names
        
        return jsonify({
            "success": True,
            "file_id": file_id,
            "sheets": sheets
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/get-headers", methods=["POST"])
def get_headers():
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name")
    header_row = data.get("header_row")
    
    if not file_id or not sheet_name:
        return jsonify({"success": False, "error": "Missing parameters"}), 400
        
    # Find matching uploaded file
    file_path = None
    for ext in ('.xlsx', '.xls'):
        p = os.path.join(UPLOAD_FOLDER, f"{file_id}{ext}")
        if os.path.exists(p):
            file_path = p
            break
            
    if not file_path:
        return jsonify({"success": False, "error": "Session expired or file not found"}), 404
        
    try:
        headers, _ = find_headers_and_df(file_path, sheet_name, header_row=header_row)
        return jsonify({
            "success": True,
            "headers": headers
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get-date-range", methods=["POST"])
def get_date_range():
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name")
    date_col = data.get("date_col")
    header_row = data.get("header_row")
    
    if not file_id or not sheet_name or not date_col:
        return jsonify({"success": False, "error": "Missing parameters"}), 400
        
    file_path = None
    for ext in ('.xlsx', '.xls'):
        p = os.path.join(UPLOAD_FOLDER, f"{file_id}{ext}")
        if os.path.exists(p):
            file_path = p
            break
            
    if not file_path:
        return jsonify({"success": False, "error": "File not found"}), 404
        
    try:
        headers, df_data = find_headers_and_df(file_path, sheet_name, header_row=header_row)
        if date_col not in df_data.columns:
            return jsonify({"success": False, "error": f"Date column '{date_col}' not found in sheet"}), 400
            
        # Parse dates
        dates = df_data[date_col].dropna().apply(parse_date_to_comparable).dropna()
        if dates.empty:
            return jsonify({"success": True, "min_date": None, "max_date": None})
            
        min_date = min(dates).strftime("%Y-%m-%d")
        max_date = max(dates).strftime("%Y-%m-%d")
        
        return jsonify({
            "success": True,
            "min_date": min_date,
            "max_date": max_date
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/detect-tax-rates", methods=["POST"])
def detect_tax_rates():
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name")
    mappings = data.get("mappings", {})
    header_row = data.get("header_row")
    
    if not file_id or not sheet_name or not mappings:
        return jsonify({"success": False, "error": "Missing parameters"}), 400
        
    file_path = None
    for ext in ('.xlsx', '.xls'):
        p = os.path.join(UPLOAD_FOLDER, f"{file_id}{ext}")
        if os.path.exists(p):
            file_path = p
            break
            
    if not file_path:
        return jsonify({"success": False, "error": "File not found"}), 404
        
    try:
        headers, df_data = find_headers_and_df(file_path, sheet_name, header_row=header_row)
        
        # Extract mapping column names
        taxable_col = mappings.get("Taxable Amount")
        cgst_col = mappings.get("CGST Amount")
        sgst_col = mappings.get("SGST Amount")
        igst_col = mappings.get("IGST Amount")
        
        detected_keys = set()
        
        def to_float(val):
            if not val:
                return 0.0
            try:
                return float(str(val).replace(",", "").strip())
            except:
                return 0.0

        for idx, row in df_data.iterrows():
            taxable = to_float(row.get(taxable_col, 0)) if taxable_col in df_data.columns else 0.0
            if taxable <= 0:
                continue
                
            if cgst_col in df_data.columns:
                cgst = to_float(row.get(cgst_col, 0))
                if cgst > 0:
                    rate = int(round((cgst / taxable) * 100))
                    detected_keys.add(f"CGST Output {rate}%")
                    
            if sgst_col in df_data.columns:
                sgst = to_float(row.get(sgst_col, 0))
                if sgst > 0:
                    rate = int(round((sgst / taxable) * 100))
                    detected_keys.add(f"SGST Output {rate}%")
                    
            if igst_col in df_data.columns:
                igst = to_float(row.get(igst_col, 0))
                if igst > 0:
                    rate = int(round((igst / taxable) * 100))
                    detected_keys.add(f"IGST Output {rate}%")
                    
        return jsonify({
            "success": True,
            "tax_keys": sorted(list(detected_keys))
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def find_matching_ledger(excel_party, tally_ledgers):
    if not excel_party or not tally_ledgers:
        return excel_party
        
    excel_party_str = str(excel_party).strip()
    excel_party_clean = excel_party_str.lower()
    
    # 1. Exact Match
    for ledger in tally_ledgers:
        if ledger.strip().lower() == excel_party_clean:
            return ledger

    # Treat "YG General Store" and "Y G General Store" as the same party.
    excel_compact = compact_party_name(excel_party_str)
    if excel_compact:
        for ledger in tally_ledgers:
            if compact_party_name(ledger) == excel_compact:
                return ledger
            
    # 3. Suffix-cleaned exact match
    excel_tokens = clean_and_tokenize(excel_party_str)
    excel_root = " ".join(excel_tokens)
    if not excel_root:
        return excel_party
        
    for ledger in tally_ledgers:
        ledger_tokens = clean_and_tokenize(ledger)
        ledger_root = " ".join(ledger_tokens)
        if ledger_root == excel_root:
            return ledger
            
    # 3. Word-token Jaccard similarity (threshold 0.60)
    best_ledger = None
    best_score = 0.0
    
    for ledger in tally_ledgers:
        score = get_word_match_score(excel_party_str, ledger)
        if score >= 0.60 and score > best_score:
            best_score = score
            best_ledger = ledger
            
    if best_ledger:
        return best_ledger
        
    return excel_party

@app.route("/api/check-parties", methods=["POST"])
def check_parties():
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name")
    mappings = data.get("mappings", {})
    ledger_company = data.get("ledger_company", "").strip()
    header_row = data.get("header_row")
    
    from_date = data.get("from_date")
    to_date = data.get("to_date")
    
    if not file_id or not sheet_name or not mappings or not ledger_company:
        return jsonify({"success": False, "error": "Missing parameters for party checking"}), 400
        
    file_path = None
    for ext in ('.xlsx', '.xls'):
        p = os.path.join(UPLOAD_FOLDER, f"{file_id}{ext}")
        if os.path.exists(p):
            file_path = p
            break
            
    if not file_path:
        return jsonify({"success": False, "error": "File not found"}), 404
        
    try:
        # Load the selected sheet
        headers, df_data = find_headers_and_df(file_path, sheet_name, header_row=header_row)
        
        # Apply date range filtering if applicable
        df_data = filter_df_by_date_range(df_data, mappings, from_date, to_date)
        
        # Load Tally ledgers cache
        tally_ledgers = []
        safe_ledger_co = re.sub(r'[\\/*?:"<>|]', "", ledger_company).strip()
        cache_path = os.path.join(get_tally_cache_folder(), safe_ledger_co, "tally_ledger_cache.json")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                tally_ledgers = cache_data.get("ledgers", [])
                
        # Extract party name series
        src_party_col = mappings.get("Party Name")
        if not src_party_col or src_party_col not in df_data.columns:
            return jsonify({"success": False, "error": "Party Name column is not mapped or not found in sheet"}), 400
            
        party_series = df_data[src_party_col].apply(clean_text_cell).dropna().unique()
        
        perfect_matches = []
        similar_matches = []
        non_existing = []
        
        for party in party_series:
            party = str(party).strip()
            if not party or party.lower() in ("nan", "none", "null"):
                continue
                
            matched_val = party
            has_match = False
            is_exact = False
            
            # Retrieve row details first to determine the state and GSTIN
            row_match = df_data[df_data[src_party_col].apply(clean_text_cell) == party]
            state_val = ""
            gstin_val = ""
            if not row_match.empty:
                first_row = row_match.iloc[0]
                src_state_col = mappings.get("State Name")
                if src_state_col and src_state_col in df_data.columns:
                    state_val = clean_text_cell(first_row[src_state_col])
                src_gstin_col = mappings.get("GST no")
                if src_gstin_col and src_gstin_col in df_data.columns:
                    gstin_val = clean_gst_cell(first_row[src_gstin_col])
            
            if tally_ledgers:
                # 1. Exact match (ignoring case)
                for l in tally_ledgers:
                    if l.lower().strip() == party.lower():
                        has_match = True
                        is_exact = True
                        matched_val = l
                        break
                        
                # 2. Fuzzy word match
                if not has_match:
                    matched_val = find_matching_ledger(party, tally_ledgers)
                    if matched_val != party:
                        has_match = True
                    else:
                        for l in tally_ledgers:
                            if get_word_match_score(party, l) >= 0.60:
                                has_match = True
                                matched_val = l
                                break
                                
            if has_match:
                if is_exact:
                    perfect_matches.append(party)
                else:
                    score = int(get_word_match_score(party, matched_val) * 100)
                    similar_matches.append({
                        "original": party,
                        "matched": matched_val,
                        "score": score
                    })
            else:
                non_existing.append({
                    "name": party,
                    "state": state_val if state_val else "Andhra Pradesh",
                    "gstin": gstin_val if gstin_val else ""
                })
                
        return jsonify({
            "success": True,
            "perfect_matches": perfect_matches,
            "similar_matches": similar_matches,
            "non_existing": non_existing
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/check-products", methods=["POST"])
def check_products():
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name")
    mappings = data.get("mappings", {})
    stock_company = data.get("stock_company", "").strip()
    header_row = data.get("header_row")
    
    from_date = data.get("from_date")
    to_date = data.get("to_date")
    
    if not file_id or not sheet_name or not mappings or not stock_company:
        return jsonify({"success": False, "error": "Missing parameters for product checking"}), 400
        
    file_path = None
    for ext in ('.xlsx', '.xls'):
        p = os.path.join(UPLOAD_FOLDER, f"{file_id}{ext}")
        if os.path.exists(p):
            file_path = p
            break
            
    if not file_path:
        return jsonify({"success": False, "error": "File not found"}), 404
        
    try:
        # Load the selected sheet
        headers, df_data = find_headers_and_df(file_path, sheet_name, header_row=header_row)
        
        # Apply date range filtering if applicable
        df_data = filter_df_by_date_range(df_data, mappings, from_date, to_date)
        
        # Load Tally stock items cache
        tally_stock = []
        safe_stock_co = re.sub(r'[\\/*?:"<>|]', "", stock_company).strip()
        cache_path = os.path.join(get_tally_cache_folder(), safe_stock_co, "tally_stock_cache.json")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                tally_stock = cache_data.get("items", [])
                
        # Extract product series from mapped Excel column
        src_prod_col = mappings.get("Product")
        if not src_prod_col or src_prod_col not in df_data.columns:
            return jsonify({"success": False, "error": "Product column is not mapped or not found in sheet"}), 400
            
        product_series = df_data[src_prod_col].apply(clean_text_cell).dropna().unique()
        
        tally_stock_set = {str(item).strip().lower() for item in tally_stock}
        tally_stock_map = {str(item).strip().lower(): str(item).strip() for item in tally_stock}
        
        perfect_matches = []
        non_existing = []
        
        for prod in product_series:
            prod = str(prod).strip()
            if not prod or prod.lower() in ("nan", "none", "null"):
                continue
                
            prod_lower = prod.lower()
            if prod_lower in tally_stock_set:
                perfect_matches.append(tally_stock_map[prod_lower])
            else:
                non_existing.append(prod)
                
        return jsonify({
            "success": True,
            "perfect_matches": perfect_matches,
            "non_existing": non_existing
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/tally/create-missing-ledgers", methods=["POST"])
def create_missing_ledgers():
    data = request.json or {}
    ledger_company = data.get("ledger_company", "").strip()
    parties = data.get("parties", [])
    
    if not ledger_company or not parties:
        return jsonify({"success": False, "error": "Ledger Company and Parties list are required"}), 400
        
    tally_url = "http://localhost:9000"
    
    # Generate ledger creations XML body
    masters_body = ""
    processed_party_names = set()
    for p in parties:
        original_name = p.get("name", "").strip()
        name = normalize_party_name(original_name)
        state = p.get("state", "").strip() or "Andhra Pradesh"
        gstin = p.get("gstin", "").strip()
        
        if not name:
            continue
        if name.casefold() in processed_party_names:
            continue
        processed_party_names.add(name.casefold())

        name_xml = escape_xml_value(name)
        state_xml = escape_xml_value(state)
        gstin_xml = escape_xml_value(gstin)
            
        if gstin:
            gst_details = f"""
            <GSTREGISTRATIONTYPE>Regular</GSTREGISTRATIONTYPE>
            <PARTYGSTIN>{gstin_xml}</PARTYGSTIN>
            <LEDGERGSTREGISTRATIONTYPE>Regular</LEDGERGSTREGISTRATIONTYPE>
            <LEDGSTREGDETAILS.LIST>
              <APPLICABLEFROM>20240401</APPLICABLEFROM>
              <GSTREGISTRATIONTYPE>Regular</GSTREGISTRATIONTYPE>
              <STATE>{state_xml}</STATE>
              <GSTIN>{gstin_xml}</GSTIN>
            </LEDGSTREGDETAILS.LIST>"""
        else:
            gst_details = f"""
            <GSTREGISTRATIONTYPE>Unregistered</GSTREGISTRATIONTYPE>
            <LEDGERGSTREGISTRATIONTYPE>Unregistered</LEDGERGSTREGISTRATIONTYPE>
            <LEDGSTREGDETAILS.LIST>
              <APPLICABLEFROM>20240401</APPLICABLEFROM>
              <GSTREGISTRATIONTYPE>Unregistered</GSTREGISTRATIONTYPE>
              <STATE>{state_xml}</STATE>
            </LEDGSTREGDETAILS.LIST>"""
        
        masters_body += f"""
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <LEDGER NAME="{name_xml}" Action="Create">
        <NAME>{name_xml}</NAME>
        <PARENT>Sundry Debtors</PARENT>
        
        <!-- Location details -->
        <COUNTRYNAME>India</COUNTRYNAME>
        <LEDSTATENAME>{state_xml}</LEDSTATENAME>
        <LEDGERSTATENAME>{state_xml}</LEDGERSTATENAME>
        
        <BILLWISEENTRY>No</BILLWISEENTRY>
        <MAINTAINBILLWISE>No</MAINTAINBILLWISE>
        
        <MAILINGNAME.LIST TYPE="String">
          <MAILINGNAME>{name_xml}</MAILINGNAME>
        </MAILINGNAME.LIST>
        
        <LEDMAILINGDETAILS.LIST>
          <APPLICABLEFROM>20240401</APPLICABLEFROM>
          <MAILINGNAME>{name_xml}</MAILINGNAME>
          <STATE>{state_xml}</STATE>
          <COUNTRY>India</COUNTRY>
        </LEDMAILINGDETAILS.LIST>
        {gst_details}
      </LEDGER>
    </TALLYMESSAGE>"""

    xml_payload = f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Import Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <IMPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>All Masters</REPORTNAME>
        <STATICVARIABLES>
          <SVCURRENTCOMPANY>{escape_xml_value(ledger_company)}</SVCURRENTCOMPANY>
        </STATICVARIABLES>
      </REQUESTDESC>
      <REQUESTDATA>
        {masters_body}
      </REQUESTDATA>
    </IMPORTDATA>
  </BODY>
</ENVELOPE>"""

    try:
        print("--- LEDGER CREATION XML PAYLOAD ---")
        print(xml_payload[:5000])  # print up to 5000 chars
        print("-----------------------------------")
        response = requests.post(tally_url, data=xml_payload, headers={"Content-Type": "text/xml"}, timeout=1200)
        print("--- TALLY LEDGER CREATION RESPONSE ---")
        print(response.text)
        print("--------------------------------------")
        if response.status_code != 200:
            return jsonify({"success": False, "error": f"Tally server responded with status {response.status_code}"}), 400
            
        # Parse XML response
        root = ET.fromstring(response.content)
        created_el = root.find(".//CREATED")
        errors_el = root.find(".//ERRORS")
        exceptions_el = root.find(".//EXCEPTIONS")
        
        created = int(created_el.text) if created_el is not None else 0
        errors = int(errors_el.text) if errors_el is not None else 0
        exceptions = int(exceptions_el.text) if exceptions_el is not None else 0
        
        if errors > 0 or exceptions > 0:
            return jsonify({"success": False, "error": f"Tally reported {errors} errors and {exceptions} exceptions during import."}), 400
            
        # Trigger cache resync
        ledger_xml = """<ENVELOPE>
            <HEADER>
                <VERSION>1</VERSION>
                <TALLYREQUEST>Export Data</TALLYREQUEST>
                <TYPE>Collection</TYPE>
                <ID>Ledger</ID>
            </HEADER>
            <BODY>
                <DESC>
                    <STATICVARIABLES>
                        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                    </STATICVARIABLES>
                </DESC>
            </BODY>
        </ENVELOPE>"""
        
        r_sync = requests.post(tally_url, data=ledger_xml, timeout=1200)
        if r_sync.status_code == 200:
            def clean_tally_xml_str(content_bytes):
                text = content_bytes.decode("utf-8", errors="ignore")
                def repl(match):
                    ent = match.group(0)
                    try:
                        if ent.startswith("&#x"):
                            v = int(ent[3:-1], 16)
                        else:
                            v = int(ent[2:-1])
                        if v < 32 and v not in (9, 10, 13):
                            return ""
                    except:
                        pass
                    return ent
                return re.sub(r'&#x?[0-9a-fA-F]+;', repl, text).encode("utf-8", errors="ignore")
                
            root_sync = ET.fromstring(clean_tally_xml_str(r_sync.content))
            ledgers = []
            for ledger_el in root_sync.findall(".//LEDGER"):
                name = ledger_el.get("NAME") or ledger_el.findtext("NAME")
                if name:
                    ledgers.append(name.strip())
            if not ledgers:
                for name_el in root_sync.findall(".//NAME"):
                    if name_el.text:
                        ledgers.append(name_el.text.strip())
            ledgers = sorted(list(set(ledgers)))
            
            if ledgers:
                safe_ledger_co = re.sub(r'[\\/*?:"<>|]', "", ledger_company).strip()
                cache_path = os.path.join(get_tally_cache_folder(), safe_ledger_co, "tally_ledger_cache.json")
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "company_name": ledger_company,
                        "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "ledgers": ledgers
                    }, f, indent=4)
                    
        return jsonify({
            "success": True,
            "created_count": created
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Error interacting with Tally: {e}"}), 500

@app.route("/api/tally/create-missing-items", methods=["POST"])
def create_missing_items():
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name")
    mappings = data.get("mappings", {})
    header_row = data.get("header_row")
    company_name = data.get("company_name", "").strip()
    under = data.get("under", "").strip()
    units = data.get("units", "").strip() or "Nos"
    supply_type = data.get("supply_type", "Goods").strip()
    products = data.get("products", [])
    company_name_xml = escape_xml_value(company_name)
    under_xml = escape_xml_value(under)
    units_xml = escape_xml_value(units)
    supply_type_xml = escape_xml_value(supply_type)
    
    if not file_id or not sheet_name or not products or not company_name:
        return jsonify({"success": False, "error": "Missing parameters"}), 400
        
    file_path = None
    for ext in ('.xlsx', '.xls'):
        p = os.path.join(UPLOAD_FOLDER, f"{file_id}{ext}")
        if os.path.exists(p):
            file_path = p
            break
            
    if not file_path:
        return jsonify({"success": False, "error": "File not found"}), 404
        
    try:
        headers, df_data = find_headers_and_df(file_path, sheet_name, header_row=header_row)
        
        taxable_col = mappings.get("Taxable Amount")
        cgst_col = mappings.get("CGST Amount")
        sgst_col = mappings.get("SGST Amount")
        igst_col = mappings.get("IGST Amount")
        hsn_col = mappings.get("HSN Code")
        product_col = mappings.get("Product")
        
        def to_float(val):
            if val is None or pd.isna(val):
                return 0.0
            s = str(val).replace(",", "").strip()
            if s.lower() in ('nan', 'none', 'null', ''):
                return 0.0
            try:
                return float(s)
            except:
                return 0.0

        masters_body = ""
        for prod_name in products:
            prod_name = prod_name.strip()
            if not prod_name:
                continue
                
            prod_row = None
            if product_col in df_data.columns:
                matches = df_data[df_data[product_col].astype(str).str.strip() == prod_name]
                if not matches.empty:
                    prod_row = matches.iloc[0]
                    
            hsn_code = ""
            taxable_amt = 0.0
            cgst_amt = 0.0
            sgst_amt = 0.0
            igst_amt = 0.0
            
            if prod_row is not None:
                if hsn_col in df_data.columns:
                    hsn_code = str(prod_row.get(hsn_col, "")).strip().split(".")[0]
                taxable_amt = to_float(prod_row.get(taxable_col, 0))
                cgst_amt = to_float(prod_row.get(cgst_col, 0))
                sgst_amt = to_float(prod_row.get(sgst_col, 0))
                igst_amt = to_float(prod_row.get(igst_col, 0))
                
            if not hsn_code or hsn_code.lower() in ("nan", "none", "null"):
                hsn_code = "00000000"

            prod_name_xml = escape_xml_value(prod_name)
            hsn_code_xml = escape_xml_value(hsn_code)
                
            is_applicable = (cgst_amt > 0) or (sgst_amt > 0) or (igst_amt > 0)
            gst_app_status = "Applicable" if is_applicable else "Not Applicable"
            
            gst_details = ""
            if is_applicable and taxable_amt > 0:
                if cgst_amt > 0 or sgst_amt > 0:
                    # Intra-state supply: infer the combined GST rate.
                    gst_rate = round(((cgst_amt + sgst_amt) / taxable_amt) * 100, 2)
                else:
                    # Inter-state supply: infer the rate from IGST.
                    gst_rate = round((igst_amt / taxable_amt) * 100, 2)
                    
                gst_details = f"""
            <GSTDETAILS.LIST>
              <APPLICABLEFROM>20240401</APPLICABLEFROM>
              <TAXABILITY>Taxable</TAXABILITY>
              <SRCOFGSTDETAILS>Specify Details Here</SRCOFGSTDETAILS>
              <STATEWISEDETAILS.LIST>
                <STATENAME>&#4; Any</STATENAME>
                <RATEDETAILS.LIST>
                  <GSTRATEDUTYHEAD>IGST</GSTRATEDUTYHEAD>
                  <GSTRATEVALUATIONTYPE>Based on Value</GSTRATEVALUATIONTYPE>
                  <GSTRATE>{gst_rate}</GSTRATE>
                </RATEDETAILS.LIST>
              </STATEWISEDETAILS.LIST>
            </GSTDETAILS.LIST>"""

            parent_tag = f"<PARENT>{under_xml}</PARENT>" if under else ""
            
            masters_body += f"""
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <STOCKITEM NAME="{prod_name_xml}" Action="Create">
        <NAME>{prod_name_xml}</NAME>
        {parent_tag}
        <BASEUNITS>{units_xml}</BASEUNITS>
        <GSTAPPLICABLE>{gst_app_status}</GSTAPPLICABLE>
        <GSTTYPEOFSUPPLY>{supply_type_xml}</GSTTYPEOFSUPPLY>
        <HSNDETAILS.LIST>
          <APPLICABLEFROM>20240401</APPLICABLEFROM>
          <HSNCODE>{hsn_code_xml}</HSNCODE>
          <HSN>{prod_name_xml}</HSN>
          <SRCOFHSNDETAILS>Specify Details Here</SRCOFHSNDETAILS>
        </HSNDETAILS.LIST>
        {gst_details}
      </STOCKITEM>
    </TALLYMESSAGE>"""

        xml_payload = f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Import Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <IMPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>All Masters</REPORTNAME>
        <STATICVARIABLES>
          <SVCURRENTCOMPANY>{company_name_xml}</SVCURRENTCOMPANY>
        </STATICVARIABLES>
      </REQUESTDESC>
      <REQUESTDATA>
        {masters_body}
      </REQUESTDATA>
    </IMPORTDATA>
  </BODY>
</ENVELOPE>"""

        tally_url = "http://localhost:9000"
        print("--- STOCK ITEM CREATION XML PAYLOAD ---")
        print(xml_payload[:5000])  # print up to 5000 chars
        print("---------------------------------------")
        response = requests.post(tally_url, data=xml_payload, headers={"Content-Type": "text/xml"}, timeout=1200)
        print("--- TALLY STOCK ITEM CREATION RESPONSE ---")
        print(response.text)
        print("------------------------------------------")
        
        if response.status_code != 200:
            return jsonify({"success": False, "error": f"Tally server responded with status {response.status_code}"}), 400
            
        root = ET.fromstring(response.content)
        created_el = root.find(".//CREATED")
        altered_el = root.find(".//ALTERED")
        ignored_el = root.find(".//IGNORED")
        errors_el = root.find(".//ERRORS")
        exceptions_el = root.find(".//EXCEPTIONS")
        
        created = int(created_el.text) if created_el is not None else 0
        altered = int(altered_el.text) if altered_el is not None else 0
        ignored = int(ignored_el.text) if ignored_el is not None else 0
        errors = int(errors_el.text) if errors_el is not None else 0
        exceptions = int(exceptions_el.text) if exceptions_el is not None else 0
        
        if errors > 0 or exceptions > 0:
            err_msg = ""
            err_line = root.find(".//LINEERROR")
            if err_line is not None and err_line.text:
                err_msg = f": {err_line.text}"
            return jsonify({"success": False, "error": f"Tally reported {errors} errors and {exceptions} exceptions during import{err_msg}."}), 400

        if created + altered == 0:
            return jsonify({"success": False, "error": f"Tally did not create any stock items (ignored: {ignored})."}), 400
            
        stock_xml = """<ENVELOPE>
            <HEADER>
                <VERSION>1</VERSION>
                <TALLYREQUEST>Export Data</TALLYREQUEST>
                <TYPE>Collection</TYPE>
                <ID>StockItemCol</ID>
            </HEADER>
            <BODY>
                <DESC>
                    <STATICVARIABLES>
                        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                    </STATICVARIABLES>
                    <TDL>
                        <TDLMESSAGE>
                            <COLLECTION NAME="StockItemCol">
                                <TYPE>StockItem</TYPE>
                                <FETCH>NAME</FETCH>
                            </COLLECTION>
                        </TDLMESSAGE>
                    </TDL>
                </DESC>
            </BODY>
        </ENVELOPE>"""
        
        r_sync = requests.post(tally_url, data=stock_xml, timeout=1200)
        if r_sync.status_code == 200:
            root_sync = ET.fromstring(r_sync.content)
            items = []
            for item_el in root_sync.findall(".//STOCKITEM"):
                name = item_el.get("NAME") or item_el.findtext("NAME")
                if name:
                    items.append(name.strip())
            items = sorted(list(set(items)))
            
            if items:
                safe_co = re.sub(r'[\\/*?:"<>|]', "", company_name).strip()
                cache_path = os.path.join(get_tally_cache_folder(), safe_co, "tally_stock_cache.json")
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "company_name": company_name,
                        "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "items": items
                    }, f, indent=4)
                    
        return jsonify({
            "success": True,
            "created_count": created + altered,
            "ignored_count": ignored
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Error interacting with Tally: {e}"}), 500

def infer_ledger(tally_ledgers, tax_type, rate=None, fallback=None):
    tax_type_lower = tax_type.lower()
    if rate is not None:
        rate_int = int(round(rate))
        rate_str = f"{rate_int}%"
        rate_str_no_pct = f"{rate_int}"
        for l in tally_ledgers:
            l_lower = l.lower()
            if tax_type_lower in l_lower and (rate_str in l_lower or rate_str_no_pct in l_lower):
                return l
    for l in tally_ledgers:
        l_lower = l.lower()
        if tax_type_lower in l_lower:
            return l
    return fallback or f"{tax_type.upper()} Output"

@app.route("/generate", methods=["POST"])
def generate():
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name")
    mappings = data.get("mappings", {})
    original_filename = data.get("original_filename", "register.xlsx")
    ledger_company = data.get("ledger_company", "").strip()
    xml_company_name = data.get("xml_company_name", "").strip()
    sales_ledger_name = data.get("sales_ledger_name", "").strip()
    misc_ledger_name = data.get("misc_ledger_name", "").strip()
    header_row = data.get("header_row")
    tax_ledger_mappings = data.get("tax_ledger_mappings", {})
    
    from_date = data.get("from_date")
    to_date = data.get("to_date")
    
    if not file_id or not sheet_name or not mappings:
        return jsonify({"success": False, "error": "Missing parameters for file mapping"}), 400
    if not xml_company_name:
        return jsonify({"success": False, "error": "Tally Company Name for XML Import is required"}), 400
        
    file_path = None
    for ext in ('.xlsx', '.xls'):
        p = os.path.join(UPLOAD_FOLDER, f"{file_id}{ext}")
        if os.path.exists(p):
            file_path = p
            break
            
    if not file_path:
        return jsonify({"success": False, "error": "File not found"}), 404
        
    try:
        # Load and slice the selected sheet
        headers, df_data = find_headers_and_df(file_path, sheet_name, header_row=header_row)
        
        # Apply date range filtering if applicable
        df_data = filter_df_by_date_range(df_data, mappings, from_date, to_date)
        
        # Load Tally ledgers from cache
        tally_ledgers = []
        if ledger_company:
            try:
                safe_ledger_co = re.sub(r'[\\/*?:"<>|]', "", ledger_company).strip()
                cache_path = os.path.join(get_tally_cache_folder(), safe_ledger_co, "tally_ledger_cache.json")
                if os.path.exists(cache_path):
                    with open(cache_path, "r", encoding="utf-8") as f:
                        cache_data = json.load(f)
                        tally_ledgers = cache_data.get("ledgers", [])
            except Exception as cache_err:
                print(f"Error loading Tally ledger cache: {cache_err}")

        # Clean Excel columns mapping
        columns_to_include = [col for col in TARGET_COLUMNS if col in mappings]
        df_out = pd.DataFrame(columns=columns_to_include)
        
        empty_gst_count = 0
        
        for target_col in columns_to_include:
            src_col = mappings[target_col]
            if src_col in df_data.columns:
                raw_series = df_data[src_col]
                if target_col == "GST no":
                    cleaned_series = raw_series.apply(clean_gst_cell)
                    empty_gst_count = int(cleaned_series.isna().sum())
                    df_out[target_col] = cleaned_series
                elif target_col == "Invoice Date":
                    df_out[target_col] = raw_series.apply(clean_date_cell)
                elif target_col in ("Qty", "Taxable Amount", "CGST Amount", "SGST Amount", "IGST Amount", "Total Amount"):
                    df_out[target_col] = raw_series.apply(clean_numeric_cell)
                else:
                    df_out[target_col] = raw_series.apply(clean_text_cell)
            else:
                df_out[target_col] = None

        if "GST no" not in columns_to_include:
            empty_gst_count = len(df_data)

        # Build matched parties dictionary
        matched_parties_dict = {}
        for idx, row in df_out.iterrows():
            party_name = str(row.get("Party Name", "")).strip()
            if party_name and party_name.lower() not in ("nan", "none", "null", ""):
                if party_name not in matched_parties_dict:
                    matched_val = party_name
                    if tally_ledgers:
                        matched_val = find_matching_ledger(party_name, tally_ledgers)
                        if matched_val == party_name:
                            for l in tally_ledgers:
                                if get_word_match_score(party_name, l) >= 0.60:
                                    matched_val = l
                                    break
                    matched_parties_dict[party_name] = matched_val

        def to_float(val):
            if not val:
                return 0.0
            try:
                return float(str(val).replace(",", "").strip())
            except:
                return 0.0

        # Group rows by Invoice No, maintaining their order of appearance
        unique_invoice_nos = []
        for idx, row in df_out.iterrows():
            inv_no = str(row.get("Invoice No", "")).strip()
            if inv_no and inv_no not in unique_invoice_nos:
                unique_invoice_nos.append(inv_no)
                
        # Generate grouped vouchers XML
        vouchers_body = ""
        for inv_no in unique_invoice_nos:
            inv_rows = df_out[df_out["Invoice No"].astype(str).str.strip() == inv_no]
            if inv_rows.empty:
                continue
                
            first_row = inv_rows.iloc[0]
            date_str = str(first_row.get("Invoice Date", "")).strip()
            tally_date = "20260401"
            if date_str and date_str.lower() not in ("nan", "none", "null"):
                try:
                    tally_date = pd.to_datetime(date_str, dayfirst=True).strftime("%Y%m%d")
                except:
                    pass
            
            orig_party = str(first_row.get("Party Name", "")).strip()
            tally_party = matched_parties_dict.get(orig_party, orig_party)
            if not tally_party:
                tally_party = "Cash"
                
            total_taxable_amount = 0.0
            total_cgst_amount = 0.0
            total_sgst_amount = 0.0
            total_igst_amount = 0.0
            total_invoice_amount = 0.0
            
            inventory_entries_xml = ""
            narrations = []
            
            for _, r in inv_rows.iterrows():
                product_name = str(r.get("Product", "")).strip()
                qty = to_float(r.get("Qty", 1))
                if qty <= 0:
                    qty = 1.0
                taxable_amt = to_float(r.get("Taxable Amount", 0))
                
                total_taxable_amount += taxable_amt
                total_cgst_amount += to_float(r.get("CGST Amount", 0))
                total_sgst_amount += to_float(r.get("SGST Amount", 0))
                total_igst_amount += to_float(r.get("IGST Amount", 0))
                total_invoice_amount += to_float(r.get("Total Amount", 0))
                
            total_taxable_amount = round(total_taxable_amount, 2)
            total_cgst_amount = round(total_cgst_amount, 2)
            total_sgst_amount = round(total_sgst_amount, 2)
            total_igst_amount = round(total_igst_amount, 2)
            total_invoice_amount = round(total_invoice_amount, 2)
            
            for _, r in inv_rows.iterrows():
                product_name = str(r.get("Product", "")).strip()
                qty = to_float(r.get("Qty", 1))
                if qty <= 0:
                    qty = 1.0
                taxable_amt = to_float(r.get("Taxable Amount", 0))
                
                row_narration = str(r.get("Narration", "")).strip()
                if row_narration and row_narration.lower() not in ("nan", "none", "null", ""):
                    narrations.append(row_narration)
                
                rate = taxable_amt / qty
                
                inventory_entries_xml += f"""
            <ALLINVENTORYENTRIES.LIST>
              <STOCKITEMNAME>{product_name}</STOCKITEMNAME>
              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
              <RATE>{rate:.2f} Nos</RATE>
              <AMOUNT>{taxable_amt:.2f}</AMOUNT>
              <ACTUALQTY>{qty:.2f} Nos</ACTUALQTY>
              <BILLEDQTY>{qty:.2f} Nos</BILLEDQTY>
              <ACCOUNTINGALLOCATIONS.LIST>
                <LEDGERNAME>{sales_ledger_name or 'Goods Sales'}</LEDGERNAME>
                <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                <AMOUNT>{taxable_amt:.2f}</AMOUNT>
              </ACCOUNTINGALLOCATIONS.LIST>
            </ALLINVENTORYENTRIES.LIST>"""

            # Narration
            narration_clean = ", ".join(narrations)
            narration_text = f"Inv No: {inv_no}, Date: {date_str}."
            if narration_clean:
                narration_text += f" Narration: {narration_clean}"

            # Group and calculate tax ledger entries first (credits)
            invoice_cgst_by_key = {}
            invoice_sgst_by_key = {}
            invoice_igst_by_key = {}
            
            for _, r in inv_rows.iterrows():
                taxable = to_float(r.get("Taxable Amount", 0))
                if taxable <= 0:
                    continue
                    
                cgst_amt = to_float(r.get("CGST Amount", 0))
                if cgst_amt > 0:
                    rate = int(round((cgst_amt / taxable) * 100))
                    key = f"CGST Output {rate}%"
                    invoice_cgst_by_key[key] = invoice_cgst_by_key.get(key, 0.0) + cgst_amt
                    
                sgst_amt = to_float(r.get("SGST Amount", 0))
                if sgst_amt > 0:
                    rate = int(round((sgst_amt / taxable) * 100))
                    key = f"SGST Output {rate}%"
                    invoice_sgst_by_key[key] = invoice_sgst_by_key.get(key, 0.0) + sgst_amt
                    
                igst_amt = to_float(r.get("IGST Amount", 0))
                if igst_amt > 0:
                    rate = int(round((igst_amt / taxable) * 100))
                    key = f"IGST Output {rate}%"
                    invoice_igst_by_key[key] = invoice_igst_by_key.get(key, 0.0) + igst_amt

            # Compute sum of tax ledgers rounded exactly as they will be written in the XML
            cgst_ledgers_total = sum(round(amt, 2) for amt in invoice_cgst_by_key.values())
            sgst_ledgers_total = sum(round(amt, 2) for amt in invoice_sgst_by_key.values())
            igst_ledgers_total = sum(round(amt, 2) for amt in invoice_igst_by_key.values())

            # Now calculate the exact credits sum and the rounded total for the invoice
            exact_credits_sum = total_taxable_amount + cgst_ledgers_total + sgst_ledgers_total + igst_ledgers_total
            rounded_total = custom_round(total_invoice_amount)
            if rounded_total == 0:
                rounded_total = custom_round(exact_credits_sum)
                
            # Roundoff offset
            roundoff_offset = round(rounded_total - exact_credits_sum, 2)
            
            # Party ledger entry: Debit (negative)
            ledger_entries_xml = f"""
            <LEDGERENTRIES.LIST>
              <LEDGERNAME>{tally_party}</LEDGERNAME>
              <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
              <AMOUNT>-{rounded_total:.2f}</AMOUNT>
            </LEDGERENTRIES.LIST>"""
            
            # Generate XML strings for CGST, SGST, IGST with exact rounded amounts
            for key, amt in invoice_cgst_by_key.items():
                if amt > 0:
                    ledger_name = tax_ledger_mappings.get(key, key)
                    ledger_entries_xml += f"""
            <LEDGERENTRIES.LIST>
              <LEDGERNAME>{ledger_name}</LEDGERNAME>
              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
              <AMOUNT>{round(amt, 2):.2f}</AMOUNT>
            </LEDGERENTRIES.LIST>"""

            for key, amt in invoice_sgst_by_key.items():
                if amt > 0:
                    ledger_name = tax_ledger_mappings.get(key, key)
                    ledger_entries_xml += f"""
            <LEDGERENTRIES.LIST>
              <LEDGERNAME>{ledger_name}</LEDGERNAME>
              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
              <AMOUNT>{round(amt, 2):.2f}</AMOUNT>
            </LEDGERENTRIES.LIST>"""

            for key, amt in invoice_igst_by_key.items():
                if amt > 0:
                    ledger_name = tax_ledger_mappings.get(key, key)
                    ledger_entries_xml += f"""
            <LEDGERENTRIES.LIST>
              <LEDGERNAME>{ledger_name}</LEDGERNAME>
              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
              <AMOUNT>{round(amt, 2):.2f}</AMOUNT>
            </LEDGERENTRIES.LIST>"""
                
            # Round-off ledger entry
            if abs(roundoff_offset) > 0.001:
                ledger_entries_xml += f"""
            <LEDGERENTRIES.LIST>
              <LEDGERNAME>{misc_ledger_name or 'Misc'}</LEDGERNAME>
              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
              <AMOUNT>{roundoff_offset:.2f}</AMOUNT>
            </LEDGERENTRIES.LIST>"""

            vouchers_body += f"""
        <TALLYMESSAGE xmlns:UDF="TallyUDF">
          <VOUCHER VCHTYPE="Sales" Action="Create" OBJVIEW="Invoice Voucher View">
            <DATE>{tally_date}</DATE>
            <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
            <VOUCHERNUMBER>{inv_no}</VOUCHERNUMBER>
            <PARTYLEDGERNAME>{tally_party}</PARTYLEDGERNAME>
            <EFFECTIVEDATE>{tally_date}</EFFECTIVEDATE>
            <PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW>
            <ISINVOICE>Yes</ISINVOICE>
            <NARRATION>{narration_text}</NARRATION>
            {inventory_entries_xml}
            {ledger_entries_xml}
          </VOUCHER>
        </TALLYMESSAGE>"""

        vouchers_xml = f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Import Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <IMPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>Vouchers</REPORTNAME>
        <STATICVARIABLES>
          <SVCURRENTCOMPANY>{escape_xml_value(xml_company_name)}</SVCURRENTCOMPANY>
        </STATICVARIABLES>
      </REQUESTDESC>
      <REQUESTDATA>
        {vouchers_body}
      </REQUESTDATA>
    </IMPORTDATA>
  </BODY>
</ENVELOPE>"""

        base_name, _ = os.path.splitext(original_filename)
        vouchers_filename = f"{base_name}_vouchers.xml"
        vouchers_path = os.path.join(PROCESSED_FOLDER, vouchers_filename)
        with open(vouchers_path, "w", encoding="utf-8") as f:
            f.write(vouchers_xml)
            
        return jsonify({
            "success": True,
            "filename": vouchers_filename,
            "row_count": len(df_out)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/download/<path:filename>", methods=["GET"])
def download(filename):
    return send_from_directory(PROCESSED_FOLDER, filename, as_attachment=True)

def custom_round(val):
    if val is None or pd.isna(val):
        return 0
    try:
        val_float = float(str(val).replace(",", "").strip())
    except Exception:
        return 0
    dec = val_float - math.floor(val_float)
    if dec >= 0.5:
        return math.ceil(val_float)
    else:
        return math.floor(val_float)

@app.route("/generate_excel", methods=["POST"])
def generate_excel():
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name")
    mappings = data.get("mappings", {})
    original_filename = data.get("original_filename", "register.xlsx")
    header_row = data.get("header_row")
    from_date = data.get("from_date")
    to_date = data.get("to_date")
    
    if not file_id or not sheet_name or not mappings:
        return jsonify({"success": False, "error": "Missing parameters for file mapping"}), 400
        
    file_path = None
    for ext in ('.xlsx', '.xls'):
        p = os.path.join(UPLOAD_FOLDER, f"{file_id}{ext}")
        if os.path.exists(p):
            file_path = p
            break
            
    if not file_path:
        return jsonify({"success": False, "error": "File not found"}), 404
        
    try:
        # Load and slice the selected sheet
        headers, df_data = find_headers_and_df(file_path, sheet_name, header_row=header_row)
        
        # Apply date range filtering if applicable
        df_data = filter_df_by_date_range(df_data, mappings, from_date, to_date)
        
        # Clean Excel columns mapping
        columns_to_include = [col for col in TARGET_COLUMNS if col in mappings]
        df_out = pd.DataFrame(columns=columns_to_include)
        
        for target_col in columns_to_include:
            src_col = mappings[target_col]
            if src_col in df_data.columns:
                raw_series = df_data[src_col]
                if target_col == "GST no":
                    df_out[target_col] = raw_series.apply(clean_gst_cell)
                elif target_col == "Invoice Date":
                    df_out[target_col] = raw_series.apply(clean_date_cell)
                elif target_col in ("Qty", "Taxable Amount", "CGST Amount", "SGST Amount", "IGST Amount", "Total Amount"):
                    df_out[target_col] = raw_series.apply(clean_numeric_cell)
                else:
                    df_out[target_col] = raw_series.apply(clean_text_cell)
            else:
                df_out[target_col] = None

        # Local helper (to_float is a nested fn in other routes, define it here too)
        def to_float(val):
            if val is None:
                return 0.0
            try:
                return float(str(val).replace(",", "").strip())
            except Exception:
                return 0.0

        # ── Compute Misc (round-off) and Rounded Total per INVOICE ────────────
        # Uses same logic as XML generation: group taxes by rate → round each group
        # → exact_credits = taxable + sum(rounded groups) → misc = round(inv_total) - exact_credits
        misc_map    = {}   # inv_no  -> misc amount
        rounded_map = {}   # inv_no  -> rounded invoice total (what goes to Tally as debit)

        if "Invoice No" in df_out.columns and "Total Amount" in df_out.columns:
            for inv_no_key, inv_grp in df_out.groupby(
                df_out["Invoice No"].astype(str).str.strip(), sort=False
            ):
                inv_total   = sum(to_float(v) for v in inv_grp["Total Amount"])
                inv_taxable = round(sum(to_float(v) for v in inv_grp.get("Taxable Amount", [0])), 2)

                cgst_by_key = {}
                sgst_by_key = {}
                igst_by_key = {}
                for _, rr in inv_grp.iterrows():
                    txbl = to_float(rr.get("Taxable Amount", 0))
                    if txbl <= 0:
                        continue
                    c = to_float(rr.get("CGST Amount", 0))
                    if c > 0:
                        rk = int(round((c / txbl) * 100))
                        cgst_by_key[rk] = cgst_by_key.get(rk, 0.0) + c
                    s = to_float(rr.get("SGST Amount", 0))
                    if s > 0:
                        rk = int(round((s / txbl) * 100))
                        sgst_by_key[rk] = sgst_by_key.get(rk, 0.0) + s
                    ig = to_float(rr.get("IGST Amount", 0))
                    if ig > 0:
                        rk = int(round((ig / txbl) * 100))
                        igst_by_key[rk] = igst_by_key.get(rk, 0.0) + ig

                cgst_total = sum(round(v, 2) for v in cgst_by_key.values())
                sgst_total = sum(round(v, 2) for v in sgst_by_key.values())
                igst_total = sum(round(v, 2) for v in igst_by_key.values())

                exact_credits  = inv_taxable + cgst_total + sgst_total + igst_total
                rounded_total  = custom_round(inv_total)   # commercial rounding: always round .5 up (matches Tally)
                misc           = round(rounded_total - exact_credits, 2)

                misc_map[inv_no_key]    = misc
                rounded_map[inv_no_key] = rounded_total

        # Add Misc column right after Total Amount
        # Show the value only on the first row of each invoice; 0 for subsequent rows
        if "Invoice No" in df_out.columns:
            seen_inv  = set()
            misc_vals = []
            rounded_vals = []
            for _, rr in df_out.iterrows():
                inv_key = str(rr.get("Invoice No", "")).strip()
                if inv_key not in seen_inv:
                    seen_inv.add(inv_key)
                    misc_vals.append(misc_map.get(inv_key, 0.0))
                    rounded_vals.append(rounded_map.get(inv_key, 0))
                else:
                    misc_vals.append(0.0)
                    rounded_vals.append(0)

            if "Total Amount" in df_out.columns:
                pos = df_out.columns.get_loc("Total Amount") + 1
                df_out.insert(pos, "Misc", misc_vals)
                df_out.insert(pos + 1, "Invoice Rounded Total", rounded_vals)
            else:
                df_out["Misc"] = misc_vals
                df_out["Invoice Rounded Total"] = rounded_vals
        else:
            # No invoice grouping possible - calculate Rounded Total Amount per row (fallback)
            if "Total Amount" in df_out.columns:
                df_out["Misc"] = 0
                df_out["Invoice Rounded Total"] = df_out["Total Amount"].apply(lambda x: round(to_float(x)))

        # Remove the old per-row Rounded Total Amount (it was misleading - rounded individual product rows)
        if "Rounded Total Amount" in df_out.columns:
            df_out.drop(columns=["Rounded Total Amount"], inplace=True)

        # Save the processed DataFrame to Excel with two sheets
        base_name, _ = os.path.splitext(original_filename)
        processed_filename = f"{base_name}_processed.xlsx"
        processed_path = os.path.join(PROCESSED_FOLDER, processed_filename)

        with pd.ExcelWriter(processed_path, engine="xlsxwriter") as writer:
            # ── Sheet 1: Processed Data (unchanged) ──────────────────────────
            df_out.to_excel(writer, sheet_name="Processed Data", index=False)
            wb  = writer.book
            ws1 = writer.sheets["Processed Data"]

            # Auto-fit column widths for Sheet 1
            for col_idx, col_name in enumerate(df_out.columns):
                try:
                    col_max = df_out[col_name].astype(str).map(len).max() if len(df_out) > 0 else 0
                    col_max = 0 if (col_max != col_max) else int(col_max)  # NaN check: nan != nan
                    max_len = max(len(str(col_name)), col_max)
                    ws1.set_column(col_idx, col_idx, min(max_len + 4, 40))
                except Exception:
                    ws1.set_column(col_idx, col_idx, 15)

            # ── Sheet 2: Final Summary & Grouping ────────────────────────────
            ws2 = wb.add_worksheet("Final Summary & Grouping")

            # ---- Formats ----
            fmt_title = wb.add_format({
                "bold": True, "font_size": 14, "font_color": "#FFFFFF",
                "bg_color": "#1A3C6E", "align": "center", "valign": "vcenter",
                "border": 0
            })
            fmt_header = wb.add_format({
                "bold": True, "font_size": 9, "font_color": "#FFFFFF",
                "bg_color": "#2E6DA4", "align": "center", "valign": "vcenter",
                "border": 1, "border_color": "#BFCFE7"
            })
            fmt_inv_group = wb.add_format({
                "bold": True, "font_size": 9, "bg_color": "#FFD700",
                "font_color": "#1A1A1A",
                "border": 1, "border_color": "#C8A800", "valign": "vcenter"
            })
            fmt_inv_group_num = wb.add_format({
                "bold": True, "font_size": 9, "bg_color": "#FFD700",
                "font_color": "#1A1A1A",
                "border": 1, "border_color": "#C8A800", "num_format": "#,##0.00",
                "align": "right", "valign": "vcenter"
            })
            fmt_product = wb.add_format({
                "font_size": 9, "bg_color": "#FFFFFF",
                "border": 1, "border_color": "#D9E4F5", "valign": "vcenter"
            })
            fmt_product_num = wb.add_format({
                "font_size": 9, "bg_color": "#FFFFFF",
                "border": 1, "border_color": "#D9E4F5", "num_format": "#,##0.00",
                "align": "right", "valign": "vcenter"
            })
            # Format for CGST/SGST/IGST cells that contain rate% + amount as text
            fmt_tax_cell = wb.add_format({
                "italic": True, "font_size": 9, "font_color": "#1A3C6E",
                "bg_color": "#FFFFFF",
                "border": 1, "border_color": "#D9E4F5",
                "align": "right", "valign": "vcenter"
            })
            fmt_tax_label = wb.add_format({
                "italic": True, "font_size": 9, "font_color": "#555555",
                "bg_color": "#F5F8FF", "border": 1, "border_color": "#D9E4F5",
                "align": "right", "valign": "vcenter"
            })
            fmt_tax_value = wb.add_format({
                "italic": True, "font_size": 9, "font_color": "#555555",
                "bg_color": "#F5F8FF", "border": 1, "border_color": "#D9E4F5",
                "num_format": "#,##0.00", "align": "right", "valign": "vcenter"
            })
            fmt_subtotal_label = wb.add_format({
                "bold": True, "font_size": 9, "bg_color": "#D0E4FF",
                "border": 1, "border_color": "#BFCFE7", "align": "right", "valign": "vcenter"
            })
            fmt_subtotal_value = wb.add_format({
                "bold": True, "font_size": 9, "bg_color": "#D0E4FF",
                "border": 1, "border_color": "#BFCFE7", "num_format": "#,##0.00",
                "align": "right", "valign": "vcenter"
            })
            fmt_grand_label = wb.add_format({
                "bold": True, "font_size": 11, "font_color": "#FFFFFF",
                "bg_color": "#1A3C6E", "border": 1, "border_color": "#0D2547",
                "align": "right", "valign": "vcenter"
            })
            fmt_grand_value = wb.add_format({
                "bold": True, "font_size": 11, "font_color": "#FFD700",
                "bg_color": "#1A3C6E", "border": 1, "border_color": "#0D2547",
                "num_format": "#,##0.00", "align": "right", "valign": "vcenter"
            })
            fmt_blank = wb.add_format({
                "bg_color": "#F5F8FF", "border": 1, "border_color": "#D9E4F5"
            })

            # ---- Column widths ----
            ws2.set_column(0, 0, 6)    # SI No
            ws2.set_column(1, 1, 18)   # Invoice No
            ws2.set_column(2, 2, 14)   # Date
            ws2.set_column(3, 3, 28)   # Party Name
            ws2.set_column(4, 4, 38)   # Product
            ws2.set_column(5, 5, 10)   # HSN
            ws2.set_column(6, 6, 7)    # Qty
            ws2.set_column(7, 7, 7)    # UOM
            ws2.set_column(8, 8, 13)   # Taxable Amt
            ws2.set_column(9, 9, 11)   # CGST
            ws2.set_column(10, 10, 11) # SGST
            ws2.set_column(11, 11, 11) # IGST
            ws2.set_column(12, 12, 13) # Total Amt
            ws2.set_column(13, 13, 13) # Rounded Total

            # ---- Title row ----
            ws2.set_row(0, 24)
            ws2.merge_range(0, 0, 0, 13, "Final Summary & Grouping", fmt_title)

            # ---- Column header row ----
            col_headers = [
                "SI No", "Invoice No", "Invoice Date", "Party Name",
                "Product", "HSN Code", "Qty", "UOM",
                "Taxable Amount", "CGST", "SGST", "IGST",
                "Total Amount", "Rounded Total"
            ]
            ws2.set_row(1, 18)
            for ci, ch in enumerate(col_headers):
                ws2.write(1, ci, ch, fmt_header)

            # Freeze top 2 rows (title + column headers) so they stay visible on scroll
            ws2.freeze_panes(2, 0)

            # ---- Data rows ----
            has_inv_col   = "Invoice No" in df_out.columns
            has_date_col  = "Invoice Date" in df_out.columns
            has_party_col = "Party Name" in df_out.columns

            if has_inv_col:
                invoice_groups = df_out.groupby(
                    df_out["Invoice No"].astype(str).str.strip(),
                    sort=False
                )
            else:
                invoice_groups = [(None, df_out)]

            row = 2  # current write row (0-indexed)
            si_no = 1
            grand_total_debit = 0.0

            for inv_no, inv_df in invoice_groups:
                inv_no = str(inv_no).strip() if inv_no else ""
                date_val  = str(inv_df["Invoice Date"].iloc[0]).strip() if has_date_col else ""
                party_val = str(inv_df["Party Name"].iloc[0]).strip() if has_party_col else ""

                # -- Invoice header row --
                ws2.set_row(row, 16)
                ws2.write(row, 0, si_no, fmt_inv_group)
                ws2.write(row, 1, inv_no, fmt_inv_group)
                ws2.write(row, 2, date_val, fmt_inv_group)
                ws2.merge_range(row, 3, row, 13, party_val, fmt_inv_group)
                row += 1

                # -- Product rows --
                inv_taxable  = 0.0
                inv_total    = 0.0
                cgst_by_rate = {}  # {rate_pct: amount}
                sgst_by_rate = {}
                igst_by_rate = {}

                for _, pr in inv_df.iterrows():
                    product  = str(pr.get("Product", "")).strip()
                    hsn      = str(pr.get("HSN Code", "")).strip() if "HSN Code" in inv_df.columns else ""
                    qty      = to_float(pr.get("Qty", 0))
                    uom      = str(pr.get("UOM", "")).strip() if "UOM" in inv_df.columns else ""
                    taxable  = to_float(pr.get("Taxable Amount", 0))
                    cgst     = to_float(pr.get("CGST Amount", 0))
                    sgst     = to_float(pr.get("SGST Amount", 0))
                    igst     = to_float(pr.get("IGST Amount", 0))
                    total    = to_float(pr.get("Total Amount", 0))
                    rounded  = custom_round(total)

                    inv_taxable += taxable
                    inv_total   += total

                    # Compute per-row rate for inline cell label
                    def _rate_label(amt, tax):
                        if taxable > 0 and tax > 0:
                            r = int(round((tax / taxable) * 100))
                            return f"({r}%) {tax:.2f}"
                        return f"{tax:.2f}"

                    # Track per-rate tax amounts for subtotal row
                    if taxable > 0:
                        if cgst > 0:
                            r = int(round((cgst / taxable) * 100))
                            cgst_by_rate[r] = cgst_by_rate.get(r, 0.0) + cgst
                        if sgst > 0:
                            r = int(round((sgst / taxable) * 100))
                            sgst_by_rate[r] = sgst_by_rate.get(r, 0.0) + sgst
                        if igst > 0:
                            r = int(round((igst / taxable) * 100))
                            igst_by_rate[r] = igst_by_rate.get(r, 0.0) + igst

                    ws2.set_row(row, 15)
                    ws2.write(row, 0, "",                    fmt_product)
                    ws2.write(row, 1, "",                    fmt_product)
                    ws2.write(row, 2, "",                    fmt_product)
                    ws2.write(row, 3, "",                    fmt_product)
                    ws2.write(row, 4, product,               fmt_product)
                    ws2.write(row, 5, hsn,                   fmt_product)
                    ws2.write(row, 6, qty,                   fmt_product_num)
                    ws2.write(row, 7, uom,                   fmt_product)
                    ws2.write(row, 8, taxable,               fmt_product_num)
                    ws2.write(row, 9,  _rate_label(taxable, cgst), fmt_tax_cell)
                    ws2.write(row, 10, _rate_label(taxable, sgst), fmt_tax_cell)
                    ws2.write(row, 11, _rate_label(taxable, igst), fmt_tax_cell)
                    ws2.write(row, 12, total,                fmt_product_num)
                    ws2.write(row, 13, rounded,              fmt_product_num)
                    row += 1

                # -- Subtotals only (no separate per-rate tax lines) --
                inv_taxable = round(inv_taxable, 2)
                inv_rounded = custom_round(inv_total)   # commercial rounding: always round .5 up (matches Tally)
                grand_total_debit += inv_rounded

                # Recompute inv totals for subtotal row
                inv_cgst = round(sum(cgst_by_rate.values()), 2)
                inv_sgst = round(sum(sgst_by_rate.values()), 2)
                inv_igst = round(sum(igst_by_rate.values()), 2)

                # Invoice sub-total row
                ws2.set_row(row, 16)
                for ci in range(8):
                    ws2.write(row, ci, "", fmt_subtotal_label)
                ws2.write(row, 8,  inv_taxable,  fmt_subtotal_value)
                ws2.write(row, 9,  inv_cgst,     fmt_subtotal_value)
                ws2.write(row, 10, inv_sgst,     fmt_subtotal_value)
                ws2.write(row, 11, inv_igst,     fmt_subtotal_value)
                ws2.write(row, 12, round(inv_total, 2), fmt_subtotal_value)
                ws2.write(row, 13, inv_rounded,  fmt_subtotal_value)
                row += 1

                # 3 blank spacer rows between invoices
                for _ in range(3):
                    ws2.set_row(row, 6)
                    for ci in range(14):
                        ws2.write(row, ci, "", fmt_blank)
                    row += 1

                si_no += 1

            # ---- Grand Total Debits row ----
            ws2.set_row(row, 22)
            ws2.merge_range(row, 0, row, 12, "Total Debits", fmt_grand_label)
            ws2.write(row, 13, grand_total_debit, fmt_grand_value)
        
        return jsonify({
            "success": True,
            "filename": processed_filename,
            "row_count": len(df_out)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    port_no = 5005
    print(f"Starting Excel Header Mapper Flask server on http://localhost:{port_no}...")
    app.run(host="localhost", port=port_no, debug=False)
