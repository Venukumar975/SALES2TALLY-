import sys
import os
import re
import uuid
import math
import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime
import pandas as pd
from flask import Flask, request, jsonify, render_template, send_from_directory

app = Flask(__name__, template_folder="templates")

# Configure directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
PROCESSED_FOLDER = os.path.join(BASE_DIR, "processed")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

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

def find_headers_and_df(file_path, sheet_name):
    """
    Finds the optimal header row in the excel sheet by checking the first 15 rows,
    resolving duplicate/empty headers, and returning the headers and sliced DataFrame.
    """
    # Read without header first to inspect rows
    df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
    if df_raw.empty:
        return [], df_raw
    
    best_row_idx = 0
    max_non_nulls = 0
    
    # Analyze the first 15 rows
    for i in range(min(15, len(df_raw))):
        row_vals = df_raw.iloc[i].dropna().tolist()
        non_null_count = sum(1 for x in row_vals if str(x).strip() != "")
        if non_null_count > max_non_nulls:
            max_non_nulls = non_null_count
            best_row_idx = i
            
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
            
        # Get LOCALAPPDATA folder path system-independently
        local_appdata = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~/.local/share')
        cache_dir = os.path.join(local_appdata, "TallyExcelMapper", "tally_companies")
        os.makedirs(cache_dir, exist_ok=True)
        
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
        local_appdata = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~/.local/share')
        cache_dir = os.path.join(local_appdata, "TallyExcelMapper", "tally_companies")
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
            
        local_appdata = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~/.local/share')
        cache_dir = os.path.join(local_appdata, "TallyExcelMapper", "tally_companies")
        os.makedirs(cache_dir, exist_ok=True)
        
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
        headers, _ = find_headers_and_df(file_path, sheet_name)
        return jsonify({
            "success": True,
            "headers": headers
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
            
    # 2. Suffix-cleaned exact match
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
        headers, df_data = find_headers_and_df(file_path, sheet_name)
        
        # Load Tally ledgers cache
        tally_ledgers = []
        local_appdata = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~/.local/share')
        safe_ledger_co = re.sub(r'[\\/*?:"<>|]', "", ledger_company).strip()
        cache_path = os.path.join(local_appdata, "TallyExcelMapper", "tally_companies", safe_ledger_co, "tally_ledger_cache.json")
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
    for p in parties:
        name = p.get("name", "").strip()
        state = p.get("state", "").strip() or "Andhra Pradesh"
        gstin = p.get("gstin", "").strip()
        
        if not name:
            continue
            
        if gstin:
            gst_details = f"""
            <GSTREGISTRATIONTYPE>Regular</GSTREGISTRATIONTYPE>
            <PARTYGSTIN>{gstin}</PARTYGSTIN>
            <LEDGERGSTREGISTRATIONTYPE>Regular</LEDGERGSTREGISTRATIONTYPE>
            <LEDGSTREGDETAILS.LIST>
              <APPLICABLEFROM>20260401</APPLICABLEFROM>
              <GSTREGISTRATIONTYPE>Regular</GSTREGISTRATIONTYPE>
              <STATE>{state}</STATE>
              <PARTYGSTIN>{gstin}</PARTYGSTIN>
            </LEDGSTREGDETAILS.LIST>"""
        else:
            gst_details = f"""
            <GSTREGISTRATIONTYPE>Unregistered</GSTREGISTRATIONTYPE>
            <LEDGERGSTREGISTRATIONTYPE>Unregistered</LEDGERGSTREGISTRATIONTYPE>
            <LEDGSTREGDETAILS.LIST>
              <APPLICABLEFROM>20260401</APPLICABLEFROM>
              <GSTREGISTRATIONTYPE>Unregistered</GSTREGISTRATIONTYPE>
              <STATE>{state}</STATE>
            </LEDGSTREGDETAILS.LIST>"""
        
        masters_body += f"""
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <LEDGER NAME="{name}" Action="Create">
        <NAME>{name}</NAME>
        <PARENT>Sundry Debtors</PARENT>
        <COUNTRYNAME>India</COUNTRYNAME>
        <LEDSTATENAME>{state}</LEDSTATENAME>
        <BILLWISEENTRY>No</BILLWISEENTRY>
        <MAINTAINBILLWISE>No</MAINTAINBILLWISE>
        <MAILINGNAME.LIST TYPE="String">
          <MAILINGNAME>{name}</MAILINGNAME>
        </MAILINGNAME.LIST>
        <LEDMAILINGDETAILS.LIST>
          <MAILINGNAME>{name}</MAILINGNAME>
          <COUNTRYNAME>India</COUNTRYNAME>
          <LEDSTATENAME>{state}</LEDSTATENAME>
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
          <SVCURRENTCOMPANY>{ledger_company}</SVCURRENTCOMPANY>
        </STATICVARIABLES>
      </REQUESTDESC>
      <REQUESTDATA>
        {masters_body}
      </REQUESTDATA>
    </IMPORTDATA>
  </BODY>
</ENVELOPE>"""

    try:
        response = requests.post(tally_url, data=xml_payload, headers={"Content-Type": "text/xml"}, timeout=120)
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
                local_appdata = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~/.local/share')
                safe_ledger_co = re.sub(r'[\\/*?:"<>|]', "", ledger_company).strip()
                cache_path = os.path.join(local_appdata, "TallyExcelMapper", "tally_companies", safe_ledger_co, "tally_ledger_cache.json")
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

@app.route("/generate", methods=["POST"])
def generate():
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name")
    mappings = data.get("mappings", {})
    original_filename = data.get("original_filename", "register.xlsx")
    ledger_company = data.get("ledger_company", "").strip()
    stock_company = data.get("stock_company", "").strip()
    
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
        headers, df_data = find_headers_and_df(file_path, sheet_name)
        
        # Load Tally ledgers & stock items from their respective company folders
        tally_ledgers = []
        tally_stock_items = []
        local_appdata = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~/.local/share')
        
        if ledger_company:
            try:
                safe_ledger_co = re.sub(r'[\\/*?:"<>|]', "", ledger_company).strip()
                cache_path = os.path.join(local_appdata, "TallyExcelMapper", "tally_companies", safe_ledger_co, "tally_ledger_cache.json")
                if os.path.exists(cache_path):
                    with open(cache_path, "r", encoding="utf-8") as f:
                        cache_data = json.load(f)
                        tally_ledgers = cache_data.get("ledgers", [])
            except Exception as cache_err:
                print(f"Error loading Tally ledger cache: {cache_err}")
                
        if stock_company:
            try:
                safe_stock_co = re.sub(r'[\\/*?:"<>|]', "", stock_company).strip()
                stock_cache_path = os.path.join(local_appdata, "TallyExcelMapper", "tally_companies", safe_stock_co, "tally_stock_cache.json")
                if os.path.exists(stock_cache_path):
                    with open(stock_cache_path, "r", encoding="utf-8") as f:
                        stock_cache_data = json.load(f)
                        tally_stock_items = stock_cache_data.get("items", [])
            except Exception as cache_err:
                print(f"Error loading Tally stock cache: {cache_err}")

        # Only include columns that are mapped by the user
        columns_to_include = [col for col in TARGET_COLUMNS if col in mappings]
        df_out = pd.DataFrame(columns=columns_to_include)
        
        # Track statistics
        empty_gst_count = 0
        parties_mapped_count = 0
        products_mapped_count = 0
        
        # Populate mapped columns row-by-row (NO matching party/product name replacements in the excel itself)
        for target_col in columns_to_include:
            src_col = mappings[target_col]
            if src_col in df_data.columns:
                raw_series = df_data[src_col]
                
                # Apply specific cleaning functions depending on the column type
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

        # Match party names for the XML output to find missing ones and map matched ones
        matched_parties_dict = {} # maps original clean name to matched Tally name or original if unmatched
        unmatched_parties_details = {} # maps unmatched clean name to its row details (State Name, GST no)
        matched_products_dict = {} # maps original clean name to matched stock item name
        
        for idx, row in df_out.iterrows():
            # Match Party Name
            party_name = str(row.get("Party Name", "")).strip() if "Party Name" in df_out.columns else ""
            if party_name and party_name.lower() not in ("nan", "none", "null", ""):
                if party_name not in matched_parties_dict:
                    matched_val = party_name
                    has_match = False
                    if tally_ledgers:
                        matched_val = find_matching_ledger(party_name, tally_ledgers)
                        if matched_val != party_name:
                            has_match = True
                        else:
                            # Double check Jaccard score
                            for l in tally_ledgers:
                                if get_word_match_score(party_name, l) >= 0.60:
                                    has_match = True
                                    matched_val = l
                                    break
                    
                    if has_match:
                        matched_parties_dict[party_name] = matched_val
                    else:
                        matched_parties_dict[party_name] = party_name
                        # Save details of unmatched party for master creation
                        state_val = str(row.get("State Name", "")).strip() if "State Name" in df_out.columns else ""
                        gst_val = str(row.get("GST no", "")).strip() if "GST no" in df_out.columns else ""
                        unmatched_parties_details[party_name] = {
                            "state": state_val if state_val and state_val.lower() not in ("nan", "none", "null") else "Andhra Pradesh",
                            "gstin": gst_val if gst_val and gst_val.lower() not in ("nan", "none", "null") else ""
                        }
            
            # Match Product Name
            product_name = str(row.get("Product", "")).strip() if "Product" in df_out.columns else ""
            if product_name and product_name.lower() not in ("nan", "none", "null", ""):
                if product_name not in matched_products_dict:
                    matched_prod = product_name
                    if tally_stock_items:
                        matched_prod = find_matching_ledger(product_name, tally_stock_items)
                        if matched_prod != product_name:
                            products_mapped_count += 1
                        else:
                            for item in tally_stock_items:
                                if get_word_match_score(product_name, item) >= 0.60:
                                    matched_prod = item
                                    products_mapped_count += 1
                                    break
                    matched_products_dict[product_name] = matched_prod

        # Generate XML content
        # 1. masters.xml
        masters_body = ""
        for name, details in unmatched_parties_details.items():
            state_name = details["state"]
            gstin = details["gstin"]
            
            if gstin:
                gst_details = f"""
            <GSTREGISTRATIONTYPE>Regular</GSTREGISTRATIONTYPE>
            <PARTYGSTIN>{gstin}</PARTYGSTIN>
            <LEDGERGSTREGISTRATIONTYPE>Regular</LEDGERGSTREGISTRATIONTYPE>
            <LEDGSTREGDETAILS.LIST>
              <APPLICABLEFROM>20260401</APPLICABLEFROM>
              <GSTREGISTRATIONTYPE>Regular</GSTREGISTRATIONTYPE>
              <STATE>{state_name}</STATE>
              <PARTYGSTIN>{gstin}</PARTYGSTIN>
            </LEDGSTREGDETAILS.LIST>"""
            else:
                gst_details = f"""
            <GSTREGISTRATIONTYPE>Unregistered</GSTREGISTRATIONTYPE>
            <LEDGERGSTREGISTRATIONTYPE>Unregistered</LEDGERGSTREGISTRATIONTYPE>
            <LEDGSTREGDETAILS.LIST>
              <APPLICABLEFROM>20260401</APPLICABLEFROM>
              <GSTREGISTRATIONTYPE>Unregistered</GSTREGISTRATIONTYPE>
              <STATE>{state_name}</STATE>
            </LEDGSTREGDETAILS.LIST>"""
            
            masters_body += f"""
        <TALLYMESSAGE xmlns:UDF="TallyUDF">
          <LEDGER NAME="{name}" Action="Create">
            <NAME>{name}</NAME>
            <PARENT>Sundry Debtors</PARENT>
            <COUNTRYNAME>India</COUNTRYNAME>
            <LEDSTATENAME>{state_name}</LEDSTATENAME>
            <BILLWISEENTRY>No</BILLWISEENTRY>
            <MAINTAINBILLWISE>No</MAINTAINBILLWISE>
            <MAILINGNAME.LIST TYPE="String">
              <MAILINGNAME>{name}</MAILINGNAME>
            </MAILINGNAME.LIST>
            <LEDMAILINGDETAILS.LIST>
              <MAILINGNAME>{name}</MAILINGNAME>
              <COUNTRYNAME>India</COUNTRYNAME>
              <LEDSTATENAME>{state_name}</LEDSTATENAME>
            </LEDMAILINGDETAILS.LIST>
            {gst_details}
          </LEDGER>
        </TALLYMESSAGE>"""

        masters_xml = f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Import Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <IMPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>All Masters</REPORTNAME>
        <STATICVARIABLES>
          <SVCURRENTCOMPANY>{ledger_company or 'Tally Test'}</SVCURRENTCOMPANY>
        </STATICVARIABLES>
      </REQUESTDESC>
      <REQUESTDATA>
        {masters_body}
      </REQUESTDATA>
    </IMPORTDATA>
  </BODY>
</ENVELOPE>"""

        # 2. vouchers.xml
        vouchers_body = ""
        for idx, row in df_out.iterrows():
            date_str = str(row.get("Invoice Date", "")).strip() if "Invoice Date" in df_out.columns else ""
            tally_date = "20260401"
            if date_str and date_str.lower() not in ("nan", "none", "null"):
                try:
                    tally_date = pd.to_datetime(date_str, dayfirst=True).strftime("%Y%m%d")
                except:
                    pass
            
            inv_no = str(row.get("Invoice No", f"INV-{idx+1}")).strip() if "Invoice No" in df_out.columns else f"INV-{idx+1}"
            orig_party = str(row.get("Party Name", "")).strip() if "Party Name" in df_out.columns else ""
            tally_party = matched_parties_dict.get(orig_party, orig_party)
            if not tally_party:
                tally_party = "Cash"
                
            def to_float(val):
                if not val:
                    return 0.0
                try:
                    return float(str(val).replace(",", "").strip())
                except:
                    return 0.0
            
            taxable_amt = to_float(row.get("Taxable Amount", 0))
            cgst_amt = to_float(row.get("CGST Amount", 0))
            sgst_amt = to_float(row.get("SGST Amount", 0))
            igst_amt = to_float(row.get("IGST Amount", 0))
            total_amt = to_float(row.get("Total Amount", 0))
            
            if total_amt == 0:
                total_amt = taxable_amt + cgst_amt + sgst_amt + igst_amt
                
            orig_prod = str(row.get("Product", "")).strip() if "Product" in df_out.columns else ""
            tally_prod = matched_products_dict.get(orig_prod, orig_prod)
            qty = to_float(row.get("Qty", 1))
            if qty <= 0:
                qty = 1.0
                
            inventory_block = ""
            if tally_prod and tally_prod.lower() not in ("nan", "none", "null", ""):
                inventory_block = f"""
            <ALLINVENTORYENTRIES.LIST>
              <STOCKITEMNAME>{tally_prod}</STOCKITEMNAME>
              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
              <BILLEDQTY>{qty}</BILLEDQTY>
              <RATE>{taxable_amt / qty:.2f}</RATE>
              <AMOUNT>-{taxable_amt:.2f}</AMOUNT>
            </ALLINVENTORYENTRIES.LIST>"""
            
            ledger_entries = f"""
            <ALLLEDGERENTRIES.LIST>
              <LEDGERNAME>{tally_party}</LEDGERNAME>
              <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
              <AMOUNT>{total_amt:.2f}</AMOUNT>
            </ALLLEDGERENTRIES.LIST>"""
            
            if not inventory_block:
                ledger_entries += f"""
            <ALLLEDGERENTRIES.LIST>
              <LEDGERNAME>Sales</LEDGERNAME>
              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
              <AMOUNT>-{taxable_amt:.2f}</AMOUNT>
            </ALLLEDGERENTRIES.LIST>"""
            
            if cgst_amt > 0:
                ledger_entries += f"""
            <ALLLEDGERENTRIES.LIST>
              <LEDGERNAME>CGST</LEDGERNAME>
              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
              <AMOUNT>-{cgst_amt:.2f}</AMOUNT>
            </ALLLEDGERENTRIES.LIST>"""
            if sgst_amt > 0:
                ledger_entries += f"""
            <ALLLEDGERENTRIES.LIST>
              <LEDGERNAME>SGST</LEDGERNAME>
              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
              <AMOUNT>-{sgst_amt:.2f}</AMOUNT>
            </ALLLEDGERENTRIES.LIST>"""
            if igst_amt > 0:
                ledger_entries += f"""
            <ALLLEDGERENTRIES.LIST>
              <LEDGERNAME>IGST</LEDGERNAME>
              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
              <AMOUNT>-{igst_amt:.2f}</AMOUNT>
            </ALLLEDGERENTRIES.LIST>"""
            
            vouchers_body += f"""
        <TALLYMESSAGE xmlns:UDF="TallyUDF">
          <VOUCHER VCHTYPE="Sales" Action="Create">
            <DATE>{tally_date}</DATE>
            <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
            <VOUCHERNUMBER>{inv_no}</VOUCHERNUMBER>
            <PARTYNAME>{tally_party}</PARTYNAME>
            {inventory_block}
            {ledger_entries}
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
          <SVCURRENTCOMPANY>{ledger_company or 'Tally Test'}</SVCURRENTCOMPANY>
        </STATICVARIABLES>
      </REQUESTDESC>
      <REQUESTDATA>
        {vouchers_body}
      </REQUESTDATA>
    </IMPORTDATA>
  </BODY>
</ENVELOPE>"""

        # Generate output files
        base_name, _ = os.path.splitext(original_filename)
        excel_filename = f"{base_name}_intermediate.xlsx"
        excel_path = os.path.join(PROCESSED_FOLDER, excel_filename)
        
        # Save Excel
        df_out.to_excel(excel_path, index=False, sheet_name="Sales Register")
        
        # Color Excel headers
        import openpyxl
        from openpyxl.styles import PatternFill, Font
        try:
            wb = openpyxl.load_workbook(excel_path)
            ws = wb.active
            yellow_fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
            font_bold = Font(name="Calibri", size=11, bold=True)
            for col_idx in range(1, len(df_out.columns) + 1):
                cell = ws.cell(row=1, column=col_idx)
                cell.fill = yellow_fill
                cell.font = font_bold
            if ws.sheet_view:
                ws.sheet_view.showGridLines = True
            wb.save(excel_path)
        except Exception as style_err:
            print(f"Error styling headers: {style_err}")

        # Save XML files
        masters_filename = f"{base_name}_masters.xml"
        masters_path = os.path.join(PROCESSED_FOLDER, masters_filename)
        with open(masters_path, "w", encoding="utf-8") as f:
            f.write(masters_xml)
            
        vouchers_filename = f"{base_name}_vouchers.xml"
        vouchers_path = os.path.join(PROCESSED_FOLDER, vouchers_filename)
        with open(vouchers_path, "w", encoding="utf-8") as f:
            f.write(vouchers_xml)
            
        # Create ZIP archive
        import zipfile
        zip_filename = f"{base_name}_package.zip"
        zip_path = os.path.join(PROCESSED_FOLDER, zip_filename)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(excel_path, arcname=excel_filename)
            z.write(masters_path, arcname="masters.xml")
            z.write(vouchers_path, arcname="vouchers.xml")
        
        return jsonify({
            "success": True,
            "filename": zip_filename,
            "row_count": len(df_out),
            "empty_gst_count": empty_gst_count,
            "parties_mapped_count": len(unmatched_parties_details),
            "products_mapped_count": products_mapped_count
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/download/<path:filename>", methods=["GET"])
def download(filename):
    return send_from_directory(PROCESSED_FOLDER, filename, as_attachment=True)

if __name__ == "__main__":
    port_no = 5005
    print(f"Starting Excel Header Mapper Flask server on http://localhost:{port_no}...")
    app.run(host="localhost", port=port_no, debug=False)
