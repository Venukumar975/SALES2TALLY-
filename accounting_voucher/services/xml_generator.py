import os
import re
import math
from datetime import datetime
from xml.sax.saxutils import escape as xml_escape
import pandas as pd

from config import PROCESSED_FOLDER
from accounting_voucher.services.analysis_service import filter_spares_df_by_date

def escape_xml_value(value):
    """Return text safe for interpolation into Tally XML elements and attributes."""
    if value is None:
        return ""
    return xml_escape(str(value), {'"': '&quot;', "'": '&apos;'})

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

def parse_date_to_tally(val):
    """Parses date cell into YYYYMMDD string format."""
    if pd.isna(val) or val is None:
        return datetime.now().strftime("%Y%m%d")
    if isinstance(val, (datetime, pd.Timestamp)):
        return val.strftime("%Y%m%d")
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%b-%y", "%d-%b-%Y"):
        try:
            dt = datetime.strptime(s.split()[0], fmt)
            return dt.strftime("%Y%m%d")
        except ValueError:
            pass
    try:
        dt = pd.to_datetime(s, dayfirst=True)
        return dt.strftime("%Y%m%d")
    except Exception:
        return datetime.now().strftime("%Y%m%d")

def generate_accounting_vouchers_xml(
    file_path,
    sheet_name=0,
    column_mappings=None,
    original_filename="spares_register.xlsx",
    company_name="SRIKARA AUTOMOBILES PRIVATE LIMITED",
    voucher_type="GST SALES",
    party_name="Srikara Tuni Branch Service",
    party_details=None,
    hsn_ledger_mappings=None,
    tax_ledger_mappings=None,
    misc_ledger_name="Misc Exp",
    narration_prefix="GST Invoice Number :: ",
    from_date=None,
    to_date=None
):
    """
    Generates Tally Prime Import XML for Accounting Invoices (Spares HSN Ledgers).
    - Mode: Accounting Voucher View (<PERSISTEDVIEW>Accounting Voucher View</PERSISTEDVIEW>)
    - Debits: Single Party Ledger (<AMOUNT>-Total</AMOUNT>)
    - Credits:
      1. HSN Spares Ledgers (e.g. Gst Spares 18%-87141090) for Selling Price
      2. Tax Ledgers (Cgst 9% Output, Sgst 9% Output, etc.)
      3. Misc / Round-off entry (Misc Exp) for exact commercial debit/credit balancing
    """
    if party_details is None:
        party_details = {}
    if hsn_ledger_mappings is None:
        hsn_ledger_mappings = {}
    if tax_ledger_mappings is None:
        tax_ledger_mappings = {}
        
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    if df.empty:
        raise ValueError("Excel file contains no data")
        
    col_inv = column_mappings.get("invoice_no")
    col_date = column_mappings.get("invoice_date")
    col_hsn = column_mappings.get("hsn_code")
    col_price = column_mappings.get("selling_price")
    col_cgst = column_mappings.get("cgst_amount")
    col_sgst = column_mappings.get("sgst_amount")
    col_cgst_pct = column_mappings.get("cgst_rate")
    col_sgst_pct = column_mappings.get("sgst_rate")
    col_igst = column_mappings.get("igst_amount")

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
    xml_filename = f"{base_name}_accounting_vouchers.xml"
    xml_path = os.path.join(PROCESSED_FOLDER, xml_filename)

    # Party details tags setup
    party_name_clean = escape_xml_value((party_name or "Cash").strip())
    buyer_name = escape_xml_value((party_details.get("buyer_name") or party_name or "Cash").strip())
    state_clean = escape_xml_value((party_details.get("state") or "Andhra Pradesh").strip())
    pos_clean = escape_xml_value((party_details.get("place_of_supply") or state_clean or "Andhra Pradesh").strip())
    country_clean = escape_xml_value((party_details.get("country") or "India").strip())
    reg_type_clean = escape_xml_value((party_details.get("registration_type") or "Unregistered/Consumer").strip())
    gstin_val = (party_details.get("gstin") or "").strip()
    gstin_tag = f"\n        <PARTYGSTIN>{escape_xml_value(gstin_val)}</PARTYGSTIN>" if gstin_val else ""
    vch_type_clean = escape_xml_value((voucher_type or "GST SALES").strip())

    # Group by Invoice Number
    grouped = df.groupby(col_inv, sort=False)
    tally_messages = []
    
    total_file_debits = 0.0
    total_file_credits = 0.0
    unbalanced_invoices = []

    # Global aggregates for verification stats tables
    global_hsn_stats = {}      # hsn_code -> {"rows_count": 0, "total_price": 0.0}
    global_tax_stats = {}      # (type, rate) -> float
    global_misc_total = 0.0
    global_selling_price = 0.0
    global_cgst = 0.0
    global_sgst = 0.0
    global_igst = 0.0
    global_grand_total = 0.0
    global_rows_count = 0

    for inv_no, grp in grouped:
        inv_no_str = str(inv_no).strip()
        if not inv_no_str or inv_no_str.lower() in ("nan", "none"):
            continue

        first_row = grp.iloc[0]
        date_tally = parse_date_to_tally(first_row.get(col_date)) if col_date and col_date in grp.columns else datetime.now().strftime("%Y%m%d")

        # 1. Aggregate Selling Price per HSN Code & GST rate
        hsn_amounts = {}
        cgst_amounts = {}
        sgst_amounts = {}
        igst_amounts = {}
        
        invoice_total_price = 0.0
        invoice_total_cgst = 0.0
        invoice_total_sgst = 0.0
        invoice_total_igst = 0.0

        for _, row in grp.iterrows():
            raw_hsn = str(row.get(col_hsn, "")).strip()
            if raw_hsn.endswith(".0"):
                raw_hsn = raw_hsn[:-2]
            if not raw_hsn or raw_hsn.lower() in ("nan", "none"):
                continue

            price = float(str(row.get(col_price, 0)).replace(",", "")) if pd.notna(row.get(col_price)) else 0.0
            c_amt = float(str(row.get(col_cgst, 0)).replace(",", "")) if col_cgst and pd.notna(row.get(col_cgst)) else 0.0
            s_amt = float(str(row.get(col_sgst, 0)).replace(",", "")) if col_sgst and pd.notna(row.get(col_sgst)) else 0.0
            i_amt = float(str(row.get(col_igst, 0)).replace(",", "")) if col_igst and pd.notna(row.get(col_igst)) else 0.0

            invoice_total_price += price
            invoice_total_cgst += c_amt
            invoice_total_sgst += s_amt
            invoice_total_igst += i_amt

            global_rows_count += 1
            global_selling_price += price
            global_cgst += c_amt
            global_sgst += s_amt
            global_igst += i_amt

            # Determine rate
            c_pct = float(row.get(col_cgst_pct)) if col_cgst_pct and pd.notna(row.get(col_cgst_pct)) else None
            s_pct = float(row.get(col_sgst_pct)) if col_sgst_pct and pd.notna(row.get(col_sgst_pct)) else None

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

            # HSN key
            hsn_key = f"{raw_hsn}_{tot_rate}"
            hsn_amounts[hsn_key] = hsn_amounts.get(hsn_key, 0.0) + price

            if raw_hsn not in global_hsn_stats:
                global_hsn_stats[raw_hsn] = {"rows_count": 0, "total_price": 0.0}
            global_hsn_stats[raw_hsn]["rows_count"] += 1
            global_hsn_stats[raw_hsn]["total_price"] += price

            # Tax keys
            if c_rate > 0 and c_amt > 0:
                t_key = f"Cgst {c_rate}% Output"
                cgst_amounts[t_key] = cgst_amounts.get(t_key, 0.0) + c_amt
                k_tax = ("CGST", f"{c_rate}%")
                global_tax_stats[k_tax] = global_tax_stats.get(k_tax, 0.0) + c_amt

            if s_rate > 0 and s_amt > 0:
                t_key = f"Sgst {s_rate}% Output"
                sgst_amounts[t_key] = sgst_amounts.get(t_key, 0.0) + s_amt
                k_tax = ("SGST", f"{s_rate}%")
                global_tax_stats[k_tax] = global_tax_stats.get(k_tax, 0.0) + s_amt

            if tot_rate > 0 and i_amt > 0:
                t_key = f"Igst {tot_rate}% Output"
                igst_amounts[t_key] = igst_amounts.get(t_key, 0.0) + i_amt
                k_tax = ("IGST", f"{tot_rate}%")
                global_tax_stats[k_tax] = global_tax_stats.get(k_tax, 0.0) + i_amt

        # 2. Credits: HSN Spares Ledgers
        ledger_entries_xml = []
        exact_credits_sum = 0.0

        for hsn_key, price_sum in hsn_amounts.items():
            if price_sum <= 0:
                continue
            parts = hsn_key.split("_")
            hsn_code, rate = parts[0], parts[1]
            default_target = f"Gst Spares {rate}%-{hsn_code}"
            ledger_name = hsn_ledger_mappings.get(hsn_key) or hsn_ledger_mappings.get(default_target) or default_target
            price_rounded = round(price_sum, 2)
            exact_credits_sum += price_rounded

            ledger_entries_xml.append(f"""
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{escape_xml_value(ledger_name)}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{price_rounded:.2f}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>""")

        # 3. Credits: Tax Ledgers
        for t_key, t_amt in cgst_amounts.items():
            if t_amt > 0:
                tax_ledger_name = tax_ledger_mappings.get(t_key, t_key)
                amt_rounded = round(t_amt, 2)
                exact_credits_sum += amt_rounded
                ledger_entries_xml.append(f"""
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{escape_xml_value(tax_ledger_name)}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{amt_rounded:.2f}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>""")

        for t_key, t_amt in sgst_amounts.items():
            if t_amt > 0:
                tax_ledger_name = tax_ledger_mappings.get(t_key, t_key)
                amt_rounded = round(t_amt, 2)
                exact_credits_sum += amt_rounded
                ledger_entries_xml.append(f"""
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{escape_xml_value(tax_ledger_name)}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{amt_rounded:.2f}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>""")

        for t_key, t_amt in igst_amounts.items():
            if t_amt > 0:
                tax_ledger_name = tax_ledger_mappings.get(t_key, t_key)
                amt_rounded = round(t_amt, 2)
                exact_credits_sum += amt_rounded
                ledger_entries_xml.append(f"""
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{escape_xml_value(tax_ledger_name)}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{amt_rounded:.2f}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>""")

        # 4. Total and Misc Round-off Calculation
        gross_sum = invoice_total_price + invoice_total_cgst + invoice_total_sgst + invoice_total_igst
        rounded_total = float(custom_round(gross_sum))
        if rounded_total == 0:
            rounded_total = float(custom_round(exact_credits_sum))

        misc_offset = round(rounded_total - exact_credits_sum, 2)
        global_misc_total += misc_offset
        global_grand_total += rounded_total

        if abs(misc_offset) > 0.001:
            ledger_entries_xml.append(f"""
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{escape_xml_value(misc_ledger_name or 'Misc Exp')}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{misc_offset:.2f}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>""")

        # 5. Party Ledger Debit Entry
        party_entry = f"""
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{party_name_clean}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <ISPARTYLEDGER>Yes</ISPARTYLEDGER>
          <AMOUNT>-{rounded_total:.2f}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>"""

        # Verify debit/credit balance for this voucher
        vch_debit = rounded_total
        vch_credit = exact_credits_sum + misc_offset
        if abs(vch_debit - vch_credit) > 0.01:
            unbalanced_invoices.append({
                "invoice_no": inv_no_str,
                "debit": vch_debit,
                "credit": vch_credit,
                "difference": round(vch_debit - vch_credit, 2)
            })

        total_file_debits += vch_debit
        total_file_credits += vch_credit

        narration_text = f"{narration_prefix}{inv_no_str}"

        # Combine all voucher entries
        all_entries_str = party_entry + "".join(ledger_entries_xml)

        voucher_msg = f"""
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER VCHTYPE="Sales" ACTION="Create">
        <DATE>{date_tally}</DATE>
        <EFFECTIVEDATE>{date_tally}</EFFECTIVEDATE>
        <VOUCHERTYPENAME>{vch_type_clean}</VOUCHERTYPENAME>
        <VOUCHERNUMBER>{escape_xml_value(inv_no_str)}</VOUCHERNUMBER>
        <REFERENCE>{escape_xml_value(inv_no_str)}</REFERENCE>
        <REFERENCEDATE>{date_tally}</REFERENCEDATE>
        <ISINVOICE>Yes</ISINVOICE>
        <PARTYLEDGERNAME>{party_name_clean}</PARTYLEDGERNAME>
        <!-- Buyer (Bill to) Details -->
        <PARTYNAME>{buyer_name}</PARTYNAME>
        <BASICBUYERNAME>{buyer_name}</BASICBUYERNAME>
        <STATENAME>{state_clean}</STATENAME>
        <PLACEOFSUPPLY>{pos_clean}</PLACEOFSUPPLY>
        <COUNTRYOFRESIDENCE>{country_clean}</COUNTRYOFRESIDENCE>
        <GSTREGISTRATIONTYPE>{reg_type_clean}</GSTREGISTRATIONTYPE>{gstin_tag}
        <!-- Consignee (Ship to) Details -->
        <BASICSHIPPEDBYNAME>{buyer_name}</BASICSHIPPEDBYNAME>
        <CONSIGNEEMAILINGNAME>{buyer_name}</CONSIGNEEMAILINGNAME>
        <CONSIGNEESTATENAME>{state_clean}</CONSIGNEESTATENAME>
        <CONSIGNEECOUNTRYNAME>{country_clean}</CONSIGNEECOUNTRYNAME>
        <PERSISTEDVIEW>Accounting Voucher View</PERSISTEDVIEW>
        <NARRATION>{escape_xml_value(narration_text)}</NARRATION>
        {all_entries_str}
      </VOUCHER>
    </TALLYMESSAGE>"""
        tally_messages.append(voucher_msg)

    # Wrap in Tally Import ENVELOPE
    messages_body = "".join(tally_messages)
    full_xml = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE>
    <ID>Vouchers</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVCURRENTCOMPANY>{escape_xml_value(company_name)}</SVCURRENTCOMPANY>
      </STATICVARIABLES>
    </DESC>
    <DATA>
      {messages_body}
    </DATA>
  </BODY>
</ENVELOPE>"""

    with open(xml_path, "w", encoding="utf-8") as f:
        f.write(full_xml.strip())

    # Build HSN breakdown list sorted by rows count descending
    hsn_breakdown = []
    for hsn, stats in sorted(global_hsn_stats.items(), key=lambda x: (-x[1]["rows_count"], x[0])):
        hsn_breakdown.append({
            "hsn_code": hsn,
            "rows_count": stats["rows_count"],
            "total_price": round(stats["total_price"], 2)
        })

    # Build tax breakdown list sorted by tax type and rate
    tax_breakdown = []
    for (t_type, rate), amt in sorted(global_tax_stats.items()):
        tax_breakdown.append({
            "tax_type": t_type,
            "rate": rate,
            "total_tax": round(amt, 2)
        })

    audit_summary = {
        "success": True,
        "xml_filename": xml_filename,
        "xml_path": xml_path,
        "total_vouchers": len(tally_messages),
        "total_rows": global_rows_count,
        "total_debits": round(total_file_debits, 2),
        "total_credits": round(total_file_credits, 2),
        "difference": round(total_file_debits - total_file_credits, 2),
        "unbalanced_count": len(unbalanced_invoices),
        "is_all_passed": len(unbalanced_invoices) == 0,
        "hsn_breakdown": hsn_breakdown,
        "tax_breakdown": tax_breakdown,
        "misc_offset": round(global_misc_total, 2),
        "misc_ledger_name": misc_ledger_name or "Misc Exp",
        "total_selling_price": round(global_selling_price, 2),
        "total_cgst": round(global_cgst, 2),
        "total_sgst": round(global_sgst, 2),
        "total_igst": round(global_igst, 2),
        "grand_total": round(global_grand_total, 2)
    }

    return xml_filename, len(tally_messages), audit_summary
