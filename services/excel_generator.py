import os
import pandas as pd
from datetime import datetime

from config import PROCESSED_FOLDER, TARGET_COLUMNS
from utils.helpers import (
    find_headers_and_df, clean_date_cell, clean_gst_cell,
    clean_numeric_cell, clean_text_cell, filter_df_by_date_range,
    to_float, custom_round
)

def generate_formatted_excel(file_path, sheet_name, mappings, original_filename, header_row=None, from_date=None, to_date=None):
    """
    Generates a 2-sheet formatted summary Excel workbook:
    - Sheet 1: 'Processed Data' (Standardized columns + Misc + Invoice Rounded Total)
    - Sheet 2: 'Final Summary & Grouping' (Hierarchical invoice grouping with gold invoice headers, product rows with (rate%), light blue subtotals, spacer rows, and navy grand total debits)
    """
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

    # Compute Misc (round-off) and Rounded Total per INVOICE
    misc_map = {}
    rounded_map = {}

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
            rounded_total  = custom_round(inv_total)
            misc           = round(rounded_total - exact_credits, 2)

            misc_map[inv_no_key]    = misc
            rounded_map[inv_no_key] = rounded_total

    # Add Misc column right after Total Amount
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
        if "Total Amount" in df_out.columns:
            df_out["Misc"] = 0
            df_out["Invoice Rounded Total"] = df_out["Total Amount"].apply(lambda x: round(to_float(x)))

    if "Rounded Total Amount" in df_out.columns:
        df_out.drop(columns=["Rounded Total Amount"], inplace=True)

    base_name, _ = os.path.splitext(original_filename)
    processed_filename = f"{base_name}_processed.xlsx"
    processed_path = os.path.join(PROCESSED_FOLDER, processed_filename)

    with pd.ExcelWriter(processed_path, engine="xlsxwriter") as writer:
        # ── Sheet 1: Processed Data ──────────────────────────────────────
        df_out.to_excel(writer, sheet_name="Processed Data", index=False)
        wb  = writer.book
        ws1 = writer.sheets["Processed Data"]

        # Auto-fit column widths for Sheet 1
        for col_idx, col_name in enumerate(df_out.columns):
            try:
                col_max = df_out[col_name].astype(str).map(len).max() if len(df_out) > 0 else 0
                col_max = 0 if (col_max != col_max) else int(col_max)
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
        fmt_product = wb.add_format({
            "font_size": 9, "bg_color": "#FFFFFF",
            "border": 1, "border_color": "#D9E4F5", "valign": "vcenter"
        })
        fmt_product_num = wb.add_format({
            "font_size": 9, "bg_color": "#FFFFFF",
            "border": 1, "border_color": "#D9E4F5", "num_format": "#,##0.00",
            "align": "right", "valign": "vcenter"
        })
        fmt_tax_cell = wb.add_format({
            "italic": True, "font_size": 9, "font_color": "#1A3C6E",
            "bg_color": "#FFFFFF",
            "border": 1, "border_color": "#D9E4F5",
            "align": "right", "valign": "vcenter"
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
        # Bigger centred label for the merged 'Grand Totals' cell (cols 3-5)
        fmt_grand_label_center = wb.add_format({
            "bold": True, "font_size": 14, "font_color": "#FFD700",
            "bg_color": "#1A3C6E", "border": 1, "border_color": "#0D2547",
            "align": "center", "valign": "vcenter"
        })
        # Plain navy filler for cols 0-2 and 6-7 in the grand totals row
        fmt_grand_navy_blank = wb.add_format({
            "bg_color": "#1A3C6E", "border": 1, "border_color": "#0D2547"
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
        ws2.set_column(13, 13, 10) # Misc
        ws2.set_column(14, 14, 13) # Rounded Total

        # ---- Title row ----
        ws2.set_row(0, 24)
        ws2.merge_range(0, 0, 0, 14, "Final Summary & Grouping", fmt_title)

        # ---- Column header row ----
        col_headers = [
            "SI No", "Invoice No", "Invoice Date", "Party Name",
            "Product", "HSN Code", "Qty", "UOM",
            "Taxable Amount", "CGST", "SGST", "IGST",
            "Total Amount", "Misc", "Rounded Total"
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

        row = 2
        si_no = 1
        grand_total_debit   = 0.0
        grand_total_taxable = 0.0
        grand_total_cgst    = 0.0
        grand_total_sgst    = 0.0
        grand_total_igst    = 0.0
        grand_total_amount  = 0.0
        grand_total_misc    = 0.0

        for inv_no, inv_df in invoice_groups:
            inv_no = str(inv_no).strip() if inv_no else ""
            date_val  = str(inv_df["Invoice Date"].iloc[0]).strip() if has_date_col else ""
            party_val = str(inv_df["Party Name"].iloc[0]).strip() if has_party_col else ""
            if date_val.lower() in ("nan", "none", "null"):
                date_val = ""
            if party_val.lower() in ("nan", "none", "null"):
                party_val = ""

            # -- Invoice header row (Gold) --
            ws2.set_row(row, 16)
            ws2.write(row, 0, si_no, fmt_inv_group)
            ws2.write(row, 1, inv_no, fmt_inv_group)
            ws2.write(row, 2, date_val, fmt_inv_group)
            ws2.merge_range(row, 3, row, 14, party_val, fmt_inv_group)
            row += 1

            # -- Product rows --
            inv_taxable  = 0.0
            inv_total    = 0.0
            cgst_by_rate = {}
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

                if product.lower() in ("nan", "none", "null"): product = ""
                if hsn.lower() in ("nan", "none", "null"): hsn = ""
                if uom.lower() in ("nan", "none", "null"): uom = ""

                inv_taxable += taxable
                inv_total   += total

                def _rate_label(amt, tax):
                    if taxable > 0 and tax > 0:
                        r = int(round((tax / taxable) * 100))
                        return f"({r}%) {tax:.2f}"
                    return f"{tax:.2f}"

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
                ws2.write(row, 13, "",                   fmt_product)
                ws2.write(row, 14, rounded,              fmt_product_num)
                row += 1

            # -- Subtotals --
            inv_taxable = round(inv_taxable, 2)
            inv_rounded = custom_round(inv_total)
            inv_cgst = round(sum(cgst_by_rate.values()), 2)
            inv_sgst = round(sum(sgst_by_rate.values()), 2)
            inv_igst = round(sum(igst_by_rate.values()), 2)
            inv_misc = round(inv_rounded - (inv_taxable + inv_cgst + inv_sgst + inv_igst), 2)

            # Accumulate grand totals
            grand_total_taxable += inv_taxable
            grand_total_cgst    += inv_cgst
            grand_total_sgst    += inv_sgst
            grand_total_igst    += inv_igst
            grand_total_amount  += round(inv_total, 2)
            grand_total_misc    += inv_misc
            grand_total_debit   += inv_rounded

            ws2.set_row(row, 16)
            for ci in range(8):
                ws2.write(row, ci, "", fmt_subtotal_label)
            ws2.write(row, 8,  inv_taxable,         fmt_subtotal_value)
            ws2.write(row, 9,  inv_cgst,            fmt_subtotal_value)
            ws2.write(row, 10, inv_sgst,            fmt_subtotal_value)
            ws2.write(row, 11, inv_igst,            fmt_subtotal_value)
            ws2.write(row, 12, round(inv_total, 2), fmt_subtotal_value)
            ws2.write(row, 13, inv_misc,            fmt_subtotal_value)
            ws2.write(row, 14, inv_rounded,         fmt_subtotal_value)
            row += 1

            # 3 blank spacer rows between invoices
            for _ in range(3):
                ws2.set_row(row, 6)
                for ci in range(15):
                    ws2.write(row, ci, "", fmt_blank)
                row += 1

            si_no += 1

        # ---- Grand Totals row ----
        # Layout: [empty navy 0-2] ["Grand Totals" centered 3-5] [empty navy 6-7] [values 8-14]
        ws2.set_row(row, 26)
        for ci in range(3):
            ws2.write(row, ci, "", fmt_grand_navy_blank)          # cols 0-2: empty navy
        ws2.merge_range(row, 3, row, 5, "Grand Totals", fmt_grand_label_center)  # cols 3-5: big centred label
        ws2.write(row, 6, "", fmt_grand_navy_blank)               # col 6: empty navy
        ws2.write(row, 7, "", fmt_grand_navy_blank)               # col 7: empty navy
        ws2.write(row, 8,  round(grand_total_taxable, 2), fmt_grand_value)
        ws2.write(row, 9,  round(grand_total_cgst, 2),    fmt_grand_value)
        ws2.write(row, 10, round(grand_total_sgst, 2),    fmt_grand_value)
        ws2.write(row, 11, round(grand_total_igst, 2),    fmt_grand_value)
        ws2.write(row, 12, round(grand_total_amount, 2),  fmt_grand_value)
        ws2.write(row, 13, round(grand_total_misc, 2),    fmt_grand_value)
        ws2.write(row, 14, grand_total_debit,             fmt_grand_value)

    return processed_filename, len(df_out)
