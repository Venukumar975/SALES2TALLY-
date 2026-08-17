import os
import re
from flask import Blueprint, request, jsonify

from config import UPLOAD_FOLDER
from utils.helpers import (
    find_headers_and_df, clean_text_cell, clean_gst_cell,
    filter_df_by_date_range, parse_date_to_comparable, to_float
)
from utils.matching import find_matching_ledger, get_word_match_score
from services.tally_ledger_service import get_cached_ledgers
from services.tally_stock_service import get_cached_stock

analysis_bp = Blueprint("analysis_bp", __name__)

@analysis_bp.route("/api/get-date-range", methods=["POST"])
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
            return jsonify({"success": False, "error": "Date column not found"}), 400
            
        valid_dates = []
        for val in df_data[date_col].dropna():
            d = parse_date_to_comparable(val)
            if d:
                valid_dates.append(d)
                
        if not valid_dates:
            return jsonify({"success": True, "min_date": None, "max_date": None})
            
        min_date = min(valid_dates).strftime("%Y-%m-%d")
        max_date = max(valid_dates).strftime("%Y-%m-%d")
        return jsonify({"success": True, "min_date": min_date, "max_date": max_date})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@analysis_bp.route("/api/detect-tax-rates", methods=["POST"])
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
        taxable_col = mappings.get("Taxable Amount")
        cgst_col = mappings.get("CGST Amount")
        sgst_col = mappings.get("SGST Amount")
        igst_col = mappings.get("IGST Amount")
        
        detected_keys = set()
        for _, r in df_data.iterrows():
            taxable = to_float(r.get(taxable_col, 0)) if taxable_col in df_data.columns else 0.0
            if taxable <= 0:
                continue
                
            if cgst_col and cgst_col in df_data.columns:
                c_amt = to_float(r.get(cgst_col, 0))
                if c_amt > 0:
                    rate = int(round((c_amt / taxable) * 100))
                    detected_keys.add(f"CGST Output {rate}%")
                    
            if sgst_col and sgst_col in df_data.columns:
                s_amt = to_float(r.get(sgst_col, 0))
                if s_amt > 0:
                    rate = int(round((s_amt / taxable) * 100))
                    detected_keys.add(f"SGST Output {rate}%")
                    
            if igst_col and igst_col in df_data.columns:
                i_amt = to_float(r.get(igst_col, 0))
                if i_amt > 0:
                    rate = int(round((i_amt / taxable) * 100))
                    detected_keys.add(f"IGST Output {rate}%")
                    
        def sort_key(k):
            m = re.search(r'(\d+)%', k)
            rate = int(m.group(1)) if m else 0
            tax_type = 0 if k.startswith("CGST") else (1 if k.startswith("SGST") else 2)
            return (tax_type, rate)
            
        sorted_keys = sorted(list(detected_keys), key=sort_key)
        return jsonify({"success": True, "tax_keys": sorted_keys})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@analysis_bp.route("/api/check-parties", methods=["POST"])
def api_check_parties():
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name")
    mappings = data.get("mappings", {})
    ledger_company = data.get("ledger_company", "").strip()
    from_date = data.get("from_date")
    to_date = data.get("to_date")
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
        df_data = filter_df_by_date_range(df_data, mappings, from_date, to_date)
        
        tally_ledgers = get_cached_ledgers(ledger_company)
        
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
                for l in tally_ledgers:
                    if l.lower().strip() == party.lower():
                        has_match = True
                        is_exact = True
                        matched_val = l
                        break
                        
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
                    score = int(round(get_word_match_score(party, matched_val) * 100))
                    if score == 0:
                        score = 100
                    similar_matches.append({
                        "original": party,
                        "matched": matched_val,
                        "score": score
                    })
            else:
                non_existing.append({
                    "name": party,
                    "state": state_val or "",
                    "gstin": gstin_val or ""
                })
                
        return jsonify({
            "success": True,
            "perfect_matches": sorted(perfect_matches),
            "similar_matches": similar_matches,
            "non_existing": non_existing
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@analysis_bp.route("/api/check-products", methods=["POST"])
def api_check_products():
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name")
    mappings = data.get("mappings", {})
    stock_company = data.get("stock_company", "").strip()
    from_date = data.get("from_date")
    to_date = data.get("to_date")
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
        df_data = filter_df_by_date_range(df_data, mappings, from_date, to_date)
        
        tally_stock = get_cached_stock(stock_company)
        tally_stock_lower = [str(x).strip().lower() for x in tally_stock]
        
        src_prod_col = mappings.get("Product")
        if not src_prod_col or src_prod_col not in df_data.columns:
            return jsonify({"success": False, "error": "Product column is not mapped or not found in sheet"}), 400
            
        prod_series = df_data[src_prod_col].apply(clean_text_cell).dropna().unique()
        
        perfect_matches = []
        non_existing = []
        
        for prod in prod_series:
            prod = str(prod).strip()
            if not prod or prod.lower() in ("nan", "none", "null"):
                continue
                
            if prod.lower() in tally_stock_lower:
                perfect_matches.append(prod)
            else:
                non_existing.append(prod)
        
        # Detect unique unit types for missing products from UOM column
        detected_units = []
        uom_col = mappings.get("UOM")
        if uom_col and uom_col in df_data.columns and non_existing:
            non_existing_lower = [p.strip().lower() for p in non_existing]
            uom_series = df_data[df_data[src_prod_col].apply(clean_text_cell).str.strip().str.lower().isin(non_existing_lower)][uom_col]
            raw_units = uom_series.dropna().astype(str).str.strip().unique()
            detected_units = sorted([u for u in raw_units if u and u.lower() not in ("nan", "none", "null", "")])
                
        return jsonify({
            "success": True,
            "perfect_matches": sorted(perfect_matches),
            "non_existing": sorted(non_existing),
            "detected_units": detected_units
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@analysis_bp.route("/api/check-units", methods=["POST"])
def api_check_units():
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
        uom_col = mappings.get("UOM")
        
        detected_units = []
        if uom_col and uom_col in df_data.columns:
            raw_units = df_data[uom_col].dropna().astype(str).str.strip().unique()
            detected_units = sorted([u for u in raw_units if u and u.lower() not in ("nan", "none", "null", "")])
            
        return jsonify({
            "success": True,
            "units": detected_units,
            "uom_mapped": bool(uom_col and uom_col in df_data.columns)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

