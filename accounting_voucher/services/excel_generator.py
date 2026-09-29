import os
import math
import pandas as pd
from datetime import datetime

from config import PROCESSED_FOLDER
from accounting_voucher.services.analysis_service import filter_spares_df_by_date

def to_float(val, default=0.0):
    if val is None or pd.isna(val):
        return default
    try:
        s = str(val).replace(",", "").strip()
        return float(s)
    except (ValueError, TypeError):
        return default

def custom_round(val):
    """Exact half-up commercial rounding to whole rupee."""
    try:
        f = float(val)
    except (ValueError, TypeError):
        return 0
    sign = 1 if f >= 0 else -1
    return sign * math.floor(abs(f) + 0.5)

def custom_round_2dec(val):
    """Exact half-up commercial rounding to 2 decimal places."""
    try:
        f = float(val)
    except (ValueError, TypeError):
        return 0.0
    sign = 1 if f >= 0 else -1
    return sign * (math.floor(abs(f) * 100.0 + 0.5) / 100.0)

def generate_accounting_formatted_excel(
    file_path,
    sheet_name=0,
    column_mappings=None,
    original_filename="spares_register.xlsx",
    party_name="Srikara Tuni Branch Service",
    hsn_ledger_mappings=None,
    misc_ledger_name="Misc Exp",
    from_date=None,
    to_date=None
):
    """
    Generates a 2-sheet formatted summary Excel workbook for Accounting Invoices:
    - Sheet 1: 'Processed Data' (Standardized Spares Data with Line Totals, Misc & Rounded Total)
    - Sheet 2: 'Final Summary & Grouping' (Hierarchical grouping with gold invoice headers,
               spares HSN rows, light-blue subtotals, and navy grand totals).
    """
    if hsn_ledger_mappings is None:
        hsn_ledger_mappings = {}
        
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    if df.empty:
        raise ValueError("Excel file contains no data")
        
    col_inv = column_mappings.get("invoice_no")
    col_date = column_mappings.get("invoice_date")
    col_hsn = column_mappings.get("hsn_code")
    col_price = column_mappings.get("selling_price")
    col_cgst_pct = column_mappings.get("cgst_rate")
    col_sgst_pct = column_mappings.get("sgst_rate")
    col_igst_pct = column_mappings.get("igst_rate")

    # Filter by date range if provided
    if col_date and (from_date or to_date):
        df = filter_spares_df_by_date(df, col_date, from_date, to_date)
        if df.empty:
            raise ValueError("No records found within the selected date filter range")

    if not col_inv or col_inv not in df.columns:
        raise ValueError("Missing Invoice Number column")
    if not col_hsn or col_hsn not in df.columns:
        raise ValueError("Missing HSN Code column")
    if not col_price or col_price not in df.columns:
        raise ValueError("Missing Selling Price column")

    os.makedirs(PROCESSED_FOLDER, exist_ok=True)
    base_name, _ = os.path.splitext(os.path.basename(original_filename))
    excel_filename = f"{base_name}_accounting_summary.xlsx"
    excel_path = os.path.join(PROCESSED_FOLDER, excel_filename)

    # 1. Build standardized output records
    rows_out = []
    
    # Calculate Misc & Rounded Total per invoice
    grouped = df.groupby(col_inv, sort=False)
    
    invoice_misc_map = {}
    invoice_rounded_map = {}

    for inv_no, grp in grouped:
        inv_key = str(inv_no).strip()
        inv_price = 0.0
        inv_cgst = 0.0
        inv_sgst = 0.0
        inv_igst = 0.0

        for _, r in grp.iterrows():
            price = to_float(r.get(col_price))
            c_pct = to_float(r.get(col_cgst_pct)) if col_cgst_pct and col_cgst_pct in grp.columns else 0.0
            s_pct = to_float(r.get(col_sgst_pct)) if col_sgst_pct and col_sgst_pct in grp.columns else 0.0
            i_pct = to_float(r.get(col_igst_pct)) if col_igst_pct and col_igst_pct in grp.columns else 0.0

            c_rate = int(round(c_pct)) if c_pct > 0 else 0
            s_rate = int(round(s_pct)) if s_pct > 0 else 0
            i_rate = int(round(i_pct)) if i_pct > 0 else 0

            c_amt = custom_round_2dec(price * (c_rate / 100.0)) if c_rate > 0 else 0.0
            s_amt = custom_round_2dec(price * (s_rate / 100.0)) if s_rate > 0 else 0.0
            i_amt = custom_round_2dec(price * (i_rate / 100.0)) if i_rate > 0 else 0.0
            
            inv_price += price
            inv_cgst += c_amt
            inv_sgst += s_amt
            inv_igst += i_amt

        gross = inv_price + inv_cgst + inv_sgst + inv_igst
        rounded_total = float(custom_round(gross))
        exact_credits = round(inv_price, 2) + round(inv_cgst, 2) + round(inv_sgst, 2) + round(inv_igst, 2)
        misc_offset = round(rounded_total - exact_credits, 2)

        invoice_misc_map[inv_key] = misc_offset
        invoice_rounded_map[inv_key] = rounded_total

    seen_inv_first_row = set()

    for _, r in df.iterrows():
        inv_no_str = str(r.get(col_inv, "")).strip()
        date_str = str(r.get(col_date, "")).strip() if col_date and col_date in df.columns else ""
        if pd.notna(r.get(col_date)) and isinstance(r.get(col_date), (datetime, pd.Timestamp)):
            date_str = r.get(col_date).strftime("%d-%m-%Y")
        elif date_str.endswith("00:00:00"):
            date_str = date_str.split()[0]

        raw_hsn = str(r.get(col_hsn, "")).strip()
        if raw_hsn.endswith(".0"):
            raw_hsn = raw_hsn[:-2]

        price = to_float(r.get(col_price))
        c_pct = to_float(r.get(col_cgst_pct)) if col_cgst_pct and col_cgst_pct in df.columns else 0.0
        s_pct = to_float(r.get(col_sgst_pct)) if col_sgst_pct and col_sgst_pct in df.columns else 0.0
        i_pct = to_float(r.get(col_igst_pct)) if col_igst_pct and col_igst_pct in df.columns else 0.0

        c_rate = int(round(c_pct)) if c_pct > 0 else 0
        s_rate = int(round(s_pct)) if s_pct > 0 else 0
        i_rate = int(round(i_pct)) if i_pct > 0 else 0
        tot_rate = i_rate if i_rate > 0 else (c_rate + s_rate)

        c_amt = custom_round_2dec(price * (c_rate / 100.0)) if c_rate > 0 else 0.0
        s_amt = custom_round_2dec(price * (s_rate / 100.0)) if s_rate > 0 else 0.0
        i_amt = custom_round_2dec(price * (i_rate / 100.0)) if i_rate > 0 else 0.0

        hsn_key = f"{raw_hsn}_{tot_rate}"
        default_target = f"Gst Spares {tot_rate}%-{raw_hsn}"
        spares_ledger = hsn_ledger_mappings.get(hsn_key) or hsn_ledger_mappings.get(default_target) or default_target

        line_total = round(price + c_amt + s_amt + i_amt, 2)

        # Misc and rounded total assigned to first line of invoice
        if inv_no_str not in seen_inv_first_row:
            seen_inv_first_row.add(inv_no_str)
            misc_val = invoice_misc_map.get(inv_no_str, 0.0)
            inv_rounded = invoice_rounded_map.get(inv_no_str, 0.0)
        else:
            misc_val = 0.0
            inv_rounded = 0.0

        rows_out.append({
            "Invoice No": inv_no_str,
            "Invoice Date": date_str,
            "Party Name": party_name,
            "HSN Code": raw_hsn,
            "Spares Ledger": spares_ledger,
            "Taxable Base": price,
            "CGST": c_amt,
            "SGST": s_amt,
            "IGST": i_amt,
            "Total Amount": line_total,
            "Misc": misc_val,
            "Invoice Rounded Total": inv_rounded
        })

    df_out = pd.DataFrame(rows_out)

    # 2. Write formatted workbook with xlsxwriter
    with pd.ExcelWriter(excel_path, engine="xlsxwriter") as writer:
        # Sheet 1: Processed Data
        df_out.to_excel(writer, sheet_name="Processed Data", index=False)
        wb = writer.book
        ws1 = writer.sheets["Processed Data"]

        for col_idx, col_name in enumerate(df_out.columns):
            try:
                col_max = df_out[col_name].astype(str).map(len).max() if len(df_out) > 0 else 0
                max_len = max(len(str(col_name)), int(col_max))
                ws1.set_column(col_idx, col_idx, min(max_len + 4, 38))
            except Exception:
                ws1.set_column(col_idx, col_idx, 15)

        # Sheet 2: Final Summary & Grouping
        ws2 = wb.add_worksheet("Final Summary & Grouping")

        # ---- Formats ----
        fmt_title = wb.add_format({
            "bold": True, "font_size": 14, "font_color": "#FFFFFF",
            "bg_color": "#1A3C6E", "align": "center", "valign": "vcenter"
        })
        fmt_header = wb.add_format({
            "bold": True, "font_size": 9, "font_color": "#FFFFFF",
            "bg_color": "#2E6DA4", "align": "center", "valign": "vcenter",
            "border": 1, "border_color": "#BFCFE7"
        })
        fmt_inv_group = wb.add_format({
            "bold": True, "font_size": 9, "bg_color": "#FFD700",
            "font_color": "#1A1A1A", "border": 1, "border_color": "#C8A800",
            "valign": "vcenter"
        })
        fmt_item = wb.add_format({
            "font_size": 9, "bg_color": "#FFFFFF", "border": 1,
            "border_color": "#D9E4F5", "valign": "vcenter"
        })
        fmt_item_num = wb.add_format({
            "font_size": 9, "bg_color": "#FFFFFF", "border": 1,
            "border_color": "#D9E4F5", "num_format": "#,##0.00",
            "align": "right", "valign": "vcenter"
        })
        fmt_subtotal_label = wb.add_format({
            "bold": True, "font_size": 9, "bg_color": "#D0E4FF",
            "border": 1, "border_color": "#BFCFE7", "align": "right",
            "valign": "vcenter"
        })
        fmt_subtotal_val = wb.add_format({
            "bold": True, "font_size": 9, "bg_color": "#D0E4FF",
            "border": 1, "border_color": "#BFCFE7", "num_format": "#,##0.00",
            "align": "right", "valign": "vcenter"
        })
        fmt_grand_label = wb.add_format({
            "bold": True, "font_size": 12, "font_color": "#FFD700",
            "bg_color": "#1A3C6E", "border": 1, "border_color": "#0D2547",
            "align": "center", "valign": "vcenter"
        })
        fmt_grand_navy_blank = wb.add_format({
            "bg_color": "#1A3C6E", "border": 1, "border_color": "#0D2547"
        })
        fmt_grand_val = wb.add_format({
            "bold": True, "font_size": 11, "font_color": "#FFD700",
            "bg_color": "#1A3C6E", "border": 1, "border_color": "#0D2547",
            "num_format": "#,##0.00", "align": "right", "valign": "vcenter"
        })
        fmt_blank = wb.add_format({
            "bg_color": "#F5F8FF", "border": 1, "border_color": "#D9E4F5"
        })

        # Columns:
        # 0: SI No
        # 1: Invoice No
        # 2: Invoice Date
        # 3: Party Name
        # 4: HSN Code
        # 5: Spares Ledger
        # 6: Taxable Base
        # 7: CGST
        # 8: SGST
        # 9: IGST
        # 10: Total Amount
        # 11: Misc
        # 12: Rounded Total

        ws2.set_column(0, 0, 7)    # SI No
        ws2.set_column(1, 1, 20)   # Invoice No
        ws2.set_column(2, 2, 14)   # Date
        ws2.set_column(3, 3, 26)   # Party Name
        ws2.set_column(4, 4, 12)   # HSN Code
        ws2.set_column(5, 5, 28)   # Spares Ledger
        ws2.set_column(6, 6, 14)   # Taxable Base
        ws2.set_column(7, 7, 11)   # CGST
        ws2.set_column(8, 8, 11)   # SGST
        ws2.set_column(9, 9, 11)   # IGST
        ws2.set_column(10, 10, 14) # Total Amount
        ws2.set_column(11, 11, 10) # Misc
        ws2.set_column(12, 12, 14) # Rounded Total

        # Title
        ws2.set_row(0, 24)
        ws2.merge_range(0, 0, 0, 12, "Final Summary & Grouping - Spares Register", fmt_title)

        # Header row
        headers = [
            "SI No", "Invoice No", "Invoice Date", "Party Name",
            "HSN Code", "Spares Ledger", "Taxable Base", "CGST", "SGST", "IGST",
            "Total Amount", "Misc", "Rounded Total"
        ]
        ws2.set_row(1, 18)
        for ci, ch in enumerate(headers):
            ws2.write(1, ci, ch, fmt_header)

        ws2.freeze_panes(2, 0)

        row_idx = 2
        si_no = 1

        grand_taxable = 0.0
        grand_cgst = 0.0
        grand_sgst = 0.0
        grand_igst = 0.0
        grand_total = 0.0
        grand_misc = 0.0
        grand_rounded = 0.0

        grouped_summary = df_out.groupby("Invoice No", sort=False)

        for inv_no, grp in grouped_summary:
            first = grp.iloc[0]
            dt_str = str(first["Invoice Date"])
            party_str = str(first["Party Name"])

            # 1. Gold Header Row
            ws2.set_row(row_idx, 16)
            ws2.write(row_idx, 0, si_no, fmt_inv_group)
            ws2.write(row_idx, 1, inv_no, fmt_inv_group)
            ws2.write(row_idx, 2, dt_str, fmt_inv_group)
            ws2.merge_range(row_idx, 3, row_idx, 12, party_str, fmt_inv_group)
            row_idx += 1

            # 2. Detail Rows
            sub_taxable = 0.0
            sub_cgst = 0.0
            sub_sgst = 0.0
            sub_igst = 0.0
            sub_total = 0.0

            for _, item_row in grp.iterrows():
                ws2.set_row(row_idx, 15)
                ws2.write(row_idx, 0, "", fmt_blank)
                ws2.write(row_idx, 1, "", fmt_blank)
                ws2.write(row_idx, 2, "", fmt_blank)
                ws2.write(row_idx, 3, party_str, fmt_item)
                ws2.write(row_idx, 4, str(item_row["HSN Code"]), fmt_item)
                ws2.write(row_idx, 5, str(item_row["Spares Ledger"]), fmt_item)

                p = float(item_row["Taxable Base"])
                c = float(item_row["CGST"])
                s = float(item_row["SGST"])
                ig = float(item_row["IGST"])
                tot = float(item_row["Total Amount"])

                sub_taxable += p
                sub_cgst += c
                sub_sgst += s
                sub_igst += ig
                sub_total += tot

                ws2.write(row_idx, 6, p, fmt_item_num)
                ws2.write(row_idx, 7, c, fmt_item_num)
                ws2.write(row_idx, 8, s, fmt_item_num)
                ws2.write(row_idx, 9, ig, fmt_item_num)
                ws2.write(row_idx, 10, tot, fmt_item_num)
                ws2.write(row_idx, 11, "", fmt_blank)
                ws2.write(row_idx, 12, "", fmt_blank)
                row_idx += 1

            # 3. Light Blue Subtotal Row
            sub_misc = invoice_misc_map.get(str(inv_no).strip(), 0.0)
            sub_rounded = invoice_rounded_map.get(str(inv_no).strip(), 0.0)

            grand_taxable += sub_taxable
            grand_cgst += sub_cgst
            grand_sgst += sub_sgst
            grand_igst += sub_igst
            grand_total += sub_total
            grand_misc += sub_misc
            grand_rounded += sub_rounded

            ws2.set_row(row_idx, 16)
            ws2.merge_range(row_idx, 0, row_idx, 5, f"Subtotal - {inv_no}", fmt_subtotal_label)
            ws2.write(row_idx, 6, sub_taxable, fmt_subtotal_val)
            ws2.write(row_idx, 7, sub_cgst, fmt_subtotal_val)
            ws2.write(row_idx, 8, sub_sgst, fmt_subtotal_val)
            ws2.write(row_idx, 9, sub_igst, fmt_subtotal_val)
            ws2.write(row_idx, 10, sub_total, fmt_subtotal_val)
            ws2.write(row_idx, 11, sub_misc, fmt_subtotal_val)
            ws2.write(row_idx, 12, sub_rounded, fmt_subtotal_val)
            row_idx += 1

            # Spacer row
            ws2.set_row(row_idx, 6)
            for ci in range(13):
                ws2.write_blank(row_idx, ci, None, wb.add_format({"bg_color": "#F0F4F8"}))
            row_idx += 1
            si_no += 1

        # 4. Navy Grand Total Row
        ws2.set_row(row_idx, 22)
        ws2.write(row_idx, 0, "", fmt_grand_navy_blank)
        ws2.write(row_idx, 1, "", fmt_grand_navy_blank)
        ws2.write(row_idx, 2, "", fmt_grand_navy_blank)
        ws2.merge_range(row_idx, 3, row_idx, 5, "GRAND TOTALS", fmt_grand_label)
        ws2.write(row_idx, 6, grand_taxable, fmt_grand_val)
        ws2.write(row_idx, 7, grand_cgst, fmt_grand_val)
        ws2.write(row_idx, 8, grand_sgst, fmt_grand_val)
        ws2.write(row_idx, 9, grand_igst, fmt_grand_val)
        ws2.write(row_idx, 10, grand_total, fmt_grand_val)
        ws2.write(row_idx, 11, grand_misc, fmt_grand_val)
        ws2.write(row_idx, 12, grand_rounded, fmt_grand_val)

    return excel_filename, len(df_out)
