import os
import re
from datetime import datetime
import pandas as pd
from difflib import SequenceMatcher

def parse_date_to_comparable(val):
    if val is None or pd.isna(val):
        return None
    if isinstance(val, (datetime, pd.Timestamp)):
        return val.date()
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s.split()[0], fmt).date()
        except Exception:
            pass
    return None

def get_spares_date_range(df, date_col):
    if not date_col or date_col not in df.columns:
        return None, None
    valid_dates = []
    for val in df[date_col].dropna():
        d = parse_date_to_comparable(val)
        if d:
            valid_dates.append(d)
    if not valid_dates:
        return None, None
    return min(valid_dates).strftime("%Y-%m-%d"), max(valid_dates).strftime("%Y-%m-%d")

def filter_spares_df_by_date(df, date_col, from_date=None, to_date=None):
    if not date_col or date_col not in df.columns:
        return df
    from_d = None
    to_d = None
    if from_date:
        try:
            from_d = datetime.strptime(from_date, "%Y-%m-%d").date()
        except Exception:
            pass
    if to_date:
        try:
            to_d = datetime.strptime(to_date, "%Y-%m-%d").date()
        except Exception:
            pass
    if not from_d and not to_d:
        return df
    def in_range(v):
        d = parse_date_to_comparable(v)
        if d is None:
            return False
        if from_d and d < from_d:
            return False
        if to_d and d > to_d:
            return False
        return True
    return df[df[date_col].apply(in_range)].copy()

def clean_str(val):
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none", "null") else s

def to_float(val, default=0.0):
    if val is None or pd.isna(val):
        return default
    try:
        s = str(val).replace(",", "").strip()
        return float(s)
    except (ValueError, TypeError):
        return default

def best_match_ledger(target_name, available_ledgers, threshold=0.6):
    """Find best matching ledger name from available Tally ledgers."""
    if not target_name or not available_ledgers:
        return ""
        
    t_clean = re.sub(r'[^a-zA-Z0-9]', '', target_name).lower()
    
    # Extract any 4+ digit number (like HSN code) from target
    hsn_numbers = re.findall(r'\b\d{4,8}\b', target_name)
    
    # 1. Exact match (case insensitive)
    for l in available_ledgers:
        if l.strip().lower() == target_name.strip().lower():
            return l
            
    # 2. Normalized alphanumeric match
    for l in available_ledgers:
        l_clean = re.sub(r'[^a-zA-Z0-9]', '', l).lower()
        if l_clean == t_clean:
            return l

    # Filter candidates if HSN numbers present in target, or if tax/misc keywords present
    candidates = []
    if hsn_numbers:
        for l in available_ledgers:
            if all(num in l for num in hsn_numbers):
                candidates.append(l)
    else:
        target_lower = target_name.lower()
        if "cgst" in target_lower:
            candidates = [l for l in available_ledgers if "cgst" in l.lower()]
        elif "sgst" in target_lower:
            candidates = [l for l in available_ledgers if "sgst" in l.lower()]
        elif "igst" in target_lower:
            candidates = [l for l in available_ledgers if "igst" in l.lower()]
        elif "misc" in target_lower:
            candidates = [l for l in available_ledgers if "misc" in l.lower()]
        elif "round" in target_lower:
            candidates = [l for l in available_ledgers if "round" in l.lower()]
        else:
            candidates = available_ledgers[:50]

        # If a percentage rate exists in target (e.g. 9%), candidates must strictly contain that rate number
        rate_m = re.search(r'\b(\d+(?:\.\d+)?)\s*%', target_name)
        if rate_m:
            r = rate_m.group(1)
            rate_candidates = [l for l in candidates if re.search(rf'\b{re.escape(r)}\b', l)]
            if rate_candidates:
                candidates = rate_candidates
            else:
                return ""
            
    best_ledger = ""
    best_score = 0.0
    for l in candidates:
        l_clean = re.sub(r'[^a-zA-Z0-9]', '', l).lower()
        score = SequenceMatcher(None, t_clean, l_clean).ratio()
        if score > best_score:
            best_score = score
            best_ledger = l
            
    if best_score >= threshold:
        return best_ledger
    return ""

def auto_detect_columns(df_columns):
    """
    Intelligently auto-map standard Excel columns for Accounting Spares Vouchers.
    Required: Invoice Number, Invoice Date, HSN Code, Selling Price, CGST Amount, SGST Amount
    """
    cols_clean = {c: str(c).strip().lower() for c in df_columns}
    mapping = {
        "invoice_no": "",
        "invoice_date": "",
        "hsn_code": "",
        "selling_price": "",
        "cgst_amount": "",
        "sgst_amount": "",
        "cgst_rate": "",
        "sgst_rate": "",
        "igst_amount": "",
        "igst_rate": ""
    }
    
    for orig, c in cols_clean.items():
        if not mapping["invoice_no"] and any(k in c for k in ["invoice number", "invoice no", "inv no", "bill no", "voucher no"]):
            mapping["invoice_no"] = orig
        elif not mapping["invoice_date"] and any(k in c for k in ["invoice date", "inv date", "bill date", "date"]):
            mapping["invoice_date"] = orig
        elif not mapping["hsn_code"] and any(k in c for k in ["hsn code", "hsn", "sac", "hsn/sac"]):
            mapping["hsn_code"] = orig
        elif not mapping["selling_price"] and any(k in c for k in ["selling price", "taxable amount", "taxable value", "taxable", "basic amount", "net amount"]):
            mapping["selling_price"] = orig
        elif not mapping["cgst_amount"] and ("cgst" in c and any(a in c for a in ["amount", "amt", "val"])):
            mapping["cgst_amount"] = orig
        elif not mapping["sgst_amount"] and ("sgst" in c and any(a in c for a in ["amount", "amt", "val"])):
            mapping["sgst_amount"] = orig
        elif not mapping["cgst_rate"] and ("cgst" in c and any(r in c for r in ["%", "rate", "percent"])):
            mapping["cgst_rate"] = orig
        elif not mapping["sgst_rate"] and ("sgst" in c and any(r in c for r in ["%", "rate", "percent"])):
            mapping["sgst_rate"] = orig
        elif not mapping["igst_amount"] and ("igst" in c and any(a in c for a in ["amount", "amt", "val"])):
            mapping["igst_amount"] = orig
            
    # Fallback checks if amount without explicit word
    if not mapping["cgst_amount"]:
        for orig, c in cols_clean.items():
            if c == "cgst":
                mapping["cgst_amount"] = orig
                break
    if not mapping["sgst_amount"]:
        for orig, c in cols_clean.items():
            if c == "sgst":
                mapping["sgst_amount"] = orig
                break
                
    return mapping

def analyze_spares_excel(file_path, sheet_name=0, column_mappings=None, available_ledgers=None):
    """
    Parses the spares register Excel and extracts:
    1. All unique HSN codes + combined GST rates -> expected ledger names (Gst Spares {Rate}%-{HSN Code}).
    2. All detected Tax ledgers (CGST, SGST, IGST).
    3. Auto-maps them to available Tally ledgers.
    4. Auto-maps Misc / Round-off ledger (e.g. Misc Exp).
    """
    if available_ledgers is None:
        available_ledgers = []
        
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    if df.empty:
        raise ValueError("The selected sheet is empty")
        
    if not column_mappings:
        column_mappings = auto_detect_columns(df.columns.tolist())
        
    col_inv = column_mappings.get("invoice_no")
    col_date = column_mappings.get("invoice_date")
    col_hsn = column_mappings.get("hsn_code")
    col_price = column_mappings.get("selling_price")
    col_cgst = column_mappings.get("cgst_amount")
    col_sgst = column_mappings.get("sgst_amount")
    col_cgst_pct = column_mappings.get("cgst_rate")
    col_sgst_pct = column_mappings.get("sgst_rate")
    col_igst = column_mappings.get("igst_amount")

    if not col_inv or col_inv not in df.columns:
        raise ValueError("Could not find or map 'Invoice Number' column")
    if not col_hsn or col_hsn not in df.columns:
        raise ValueError("Could not find or map 'HSN Code' column")
    if not col_price or col_price not in df.columns:
        raise ValueError("Could not find or map 'Selling Price' (Taxable Amount) column")

    hsn_rate_map = {}
    tax_keys = set()
    total_selling_price = 0.0
    total_cgst = 0.0
    total_sgst = 0.0
    total_igst = 0.0

    for _, row in df.iterrows():
        raw_hsn = clean_str(row.get(col_hsn))
        # Remove trailing .0 from float conversion of HSN
        if raw_hsn.endswith(".0"):
            raw_hsn = raw_hsn[:-2]
        if not raw_hsn:
            continue
            
        price = to_float(row.get(col_price))
        total_selling_price += price
        
        c_amt = to_float(row.get(col_cgst)) if col_cgst and col_cgst in df.columns else 0.0
        s_amt = to_float(row.get(col_sgst)) if col_sgst and col_sgst in df.columns else 0.0
        i_amt = to_float(row.get(col_igst)) if col_igst and col_igst in df.columns else 0.0
        
        total_cgst += c_amt
        total_sgst += s_amt
        total_igst += i_amt
        
        # Determine rates
        c_pct = to_float(row.get(col_cgst_pct)) if col_cgst_pct and col_cgst_pct in df.columns else None
        s_pct = to_float(row.get(col_sgst_pct)) if col_sgst_pct and col_sgst_pct in df.columns else None
        
        if c_pct is not None and s_pct is not None and (c_pct > 0 or s_pct > 0):
            c_rate = int(round(c_pct))
            s_rate = int(round(s_pct))
            tot_rate = c_rate + s_rate
        elif price > 0:
            if c_amt > 0 or s_amt > 0:
                c_rate = int(round((c_amt / price) * 100))
                s_rate = int(round((s_amt / price) * 100))
                tot_rate = int(round(((c_amt + s_amt) / price) * 100))
            elif i_amt > 0:
                tot_rate = int(round((i_amt / price) * 100))
                c_rate, s_rate = 0, 0
            else:
                tot_rate, c_rate, s_rate = 0, 0, 0
        else:
            tot_rate, c_rate, s_rate = 0, 0, 0
            
        if c_rate > 0:
            tax_keys.add(f"Cgst {c_rate}% Output")
        if s_rate > 0:
            tax_keys.add(f"Sgst {s_rate}% Output")
        if tot_rate > 0 and (c_amt == 0 and s_amt == 0 and i_amt > 0):
            tax_keys.add(f"Igst {tot_rate}% Output")
            
        key = (raw_hsn, tot_rate)
        if key not in hsn_rate_map:
            hsn_rate_map[key] = {
                "hsn_code": raw_hsn,
                "gst_rate": tot_rate,
                "target_ledger": f"Gst Spares {tot_rate}%-{raw_hsn}",
                "rows_count": 0,
                "total_price": 0.0
            }
        hsn_rate_map[key]["rows_count"] += 1
        hsn_rate_map[key]["total_price"] += price

    # 1. HSN Spares Mappings list
    detected_hsn_list = []
    for (hsn, rate), item in sorted(hsn_rate_map.items(), key=lambda x: (-x[1]["rows_count"], x[0])):
        target = item["target_ledger"]
        matched = best_match_ledger(target, available_ledgers)
        # Also check alternative pattern without hyphen or spaces (e.g. 'Gst Spares 18% - 87141090' or 'spares 18% - 87141090')
        if not matched:
            alt1 = f"Gst Spares {rate}% - {hsn}"
            matched = best_match_ledger(alt1, available_ledgers)
        if not matched:
            alt2 = f"Spares {rate}% - {hsn}"
            matched = best_match_ledger(alt2, available_ledgers)
        if not matched:
            alt3 = f"Spares {rate}%-{hsn}"
            matched = best_match_ledger(alt3, available_ledgers)
            
        detected_hsn_list.append({
            "hsn_code": hsn,
            "gst_rate": rate,
            "target_ledger": target,
            "matched_ledger": matched or "",
            "is_matched": bool(matched),
            "rows_count": item["rows_count"],
            "total_price": round(item["total_price"], 2)
        })

    # 2. Tax Mappings list
    detected_taxes_list = []
    for tax_key in sorted(list(tax_keys)):
        matched = best_match_ledger(tax_key, available_ledgers)
        if not matched:
            # Try alternate formats like "Cgst 9%", "CGST Output 9%", etc.
            m = re.match(r'(Cgst|Sgst|Igst)\s*(\d+)%\s*Output', tax_key, re.IGNORECASE)
            if m:
                t_type, t_rate = m.group(1), m.group(2)
                for cand in [f"{t_type} {t_rate}%", f"{t_type} {t_rate}", f"{t_type} Output {t_rate}%"]:
                    matched = best_match_ledger(cand, available_ledgers)
                    if matched:
                        break
        detected_taxes_list.append({
            "tax_key": tax_key,
            "target_ledger": tax_key,
            "matched_ledger": matched or "",
            "is_matched": bool(matched)
        })

    # 3. Misc / Round-off Ledger auto-match
    misc_candidates = ["Misc Exp", "Misc Expense", "Misc Expenses", "Misc", "Round Off", "Rounding Off", "Round-Off"]
    matched_misc = ""
    for cand in misc_candidates:
        m = best_match_ledger(cand, available_ledgers, threshold=0.8)
        if m:
            matched_misc = m
            break
            
    # 4. Party Ledger auto-match (look for ledger starting with or matching Srikara)
    suggested_party = ""
    for l in available_ledgers:
        if l.strip().lower().startswith("srikara"):
            suggested_party = l
            break
    if not suggested_party:
        for cand in ["Srikara Tuni Branch Service", "Srikara Tuni Branch", "Srikara"]:
            p = best_match_ledger(cand, available_ledgers, threshold=0.7)
            if p:
                suggested_party = p
                break
            
    unique_invoices = df[col_inv].dropna().nunique()
    min_date, max_date = get_spares_date_range(df, col_date)
    unique_hsn_codes = sorted(list({str(item["hsn_code"]).strip() for item in hsn_rate_map.values() if item.get("hsn_code")}))

    return {
        "success": True,
        "total_rows": len(df),
        "total_invoices": unique_invoices,
        "total_selling_price": round(total_selling_price, 2),
        "total_cgst": round(total_cgst, 2),
        "total_sgst": round(total_sgst, 2),
        "total_igst": round(total_igst, 2),
        "column_mappings": column_mappings,
        "unique_hsn_codes": unique_hsn_codes,
        "detected_hsn_ledgers": detected_hsn_list,
        "detected_tax_ledgers": detected_taxes_list,
        "matched_misc_ledger": matched_misc or "",
        "suggested_party": suggested_party,
        "min_date": min_date,
        "max_date": max_date
    }
