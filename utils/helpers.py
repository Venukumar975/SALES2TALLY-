import math
from datetime import datetime
import pandas as pd

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

def custom_round(val):
    """
    Commercial rounding (round-half-up). Matches standard Indian accounting practice:
    values with decimal part >= 0.5 round UP to the next integer;
    values with decimal part < 0.5 round DOWN.
    """
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
