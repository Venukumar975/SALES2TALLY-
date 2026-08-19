import os
import re
import pandas as pd
from datetime import datetime

from config import PROCESSED_FOLDER
from utils.helpers import (
    find_headers_and_df, clean_date_cell, clean_text_cell,
    filter_df_by_date_range, to_float, custom_round
)
from utils.matching import find_matching_ledger, clean_and_resolve_state
from services.tally_ledger_service import get_cached_ledgers, fetch_live_party_details
from services.master_creator import escape_xml_value

def generate_tally_vouchers_xml(file_path, sheet_name, mappings, original_filename, ledger_company, xml_company_name, sales_ledger_name, misc_ledger_name, header_row=None, from_date=None, to_date=None, tax_ledger_mappings=None, sales_ledger_mappings=None):
    """
    Groups multi-item sales register records by Invoice No and builds Tally Prime Import XML Vouchers.
    Dynamically maps each item's accounting allocation (Particulars) to its matching rate-wise Sales Ledger.
    Balances debit and credit using exact commercial half-up rounding and Misc offset.
    Fetches live party metadata (State, GSTIN, Registration Type) directly from Tally Prime.
    """
    if tax_ledger_mappings is None:
        tax_ledger_mappings = {}
    if sales_ledger_mappings is None:
        sales_ledger_mappings = {}
        
    headers, df_data = find_headers_and_df(file_path, sheet_name, header_row=header_row)
    
    # Filter by date range
    df_data = filter_df_by_date_range(df_data, mappings, from_date, to_date)
    
    tally_ledgers = get_cached_ledgers(ledger_company)
    
    # Standardize mapped columns
    df_std = pd.DataFrame()
    for std_col, excel_col in mappings.items():
        if excel_col and excel_col in df_data.columns:
            if std_col == "Invoice Date":
                df_std[std_col] = df_data[excel_col].apply(clean_date_cell)
            elif std_col == "Party Name":
                df_std[std_col] = df_data[excel_col].apply(clean_text_cell).apply(lambda p: find_matching_ledger(p, tally_ledgers))
            else:
                df_std[std_col] = df_data[excel_col].apply(clean_text_cell)
                
    if df_std.empty or "Invoice No" not in df_std.columns:
        raise ValueError("No valid data or Invoice No column found to generate vouchers.")

    base_name, _ = os.path.splitext(original_filename)
    xml_filename = f"{base_name}_vouchers.xml"
    xml_path = os.path.join(PROCESSED_FOLDER, xml_filename)

    # Fetch live party details directly from Tally Prime for the target company
    target_company = (xml_company_name or ledger_company or "").strip()
    live_parties_map = fetch_live_party_details(target_company)

    # Group records by Invoice No
    grouped = df_std.groupby("Invoice No", sort=False)
    tally_messages = ""

    for inv_no, group in grouped:
        inv_no_str = str(inv_no).strip()
        first_row = group.iloc[0]
        
        # Parse and format date to YYYYMMDD
        date_raw = str(first_row.get("Invoice Date", "")).strip()
        date_tally = datetime.now().strftime("%Y%m%d")
        if date_raw:
            for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(date_raw, fmt)
                    date_tally = dt.strftime("%Y%m%d")
                    break
                except ValueError:
                    pass

        party_name = first_row.get("Party Name", "Cash")
        party_name_clean = escape_xml_value(party_name)

        # Retrieve live party details fetched directly from Tally Prime
        party_meta = live_parties_map.get(party_name.lower().strip(), {})
        buyer_name = party_meta.get("name") or party_name
        buyer_name_clean = escape_xml_value(buyer_name)
        party_state = party_meta.get("state") or ""
        party_state_clean = escape_xml_value(party_state)
        country_name = party_meta.get("country") or "India"
        country_name_clean = escape_xml_value(country_name)
        gstin_no = party_meta.get("gstin") or ""
        gstin_no_clean = escape_xml_value(gstin_no)
        reg_type = party_meta.get("registration_type") or ("Regular" if gstin_no else "Unregistered/Consumer")
        if reg_type.lower() == "unregistered":
            reg_type = "Unregistered/Consumer"
        reg_type_clean = escape_xml_value(reg_type)

        # Place of supply matches the party's official registered / shipping state
        place_of_supply = party_state_clean

        # Left Section: Buyer (Bill to) party tags
        buyer_state_tags = ""
        if party_state_clean:
            buyer_state_tags = f"""
        <STATENAME>{party_state_clean}</STATENAME>
        <PLACEOFSUPPLY>{place_of_supply}</PLACEOFSUPPLY>"""

        gstin_tag = f"\n        <PARTYGSTIN>{gstin_no_clean}</PARTYGSTIN>" if gstin_no_clean else ""

        # Right Section: Consignee (Ship to) party tags
        # In manual Tally Prime voucher entry, pressing Enter on Party Details auto-populates
        # the right-hand Consignee (Ship to) section with party name, state, and country.
        # Bulk XML imports do not trigger interactive UI hooks, so explicit Consignee tags
        # are required to populate both sides and avoid GSTR-1 "Uncertain Transactions".
        consignee_state_tag = f"\n        <CONSIGNEESTATENAME>{party_state_clean}</CONSIGNEESTATENAME>" if party_state_clean else ""
        consignee_tags = f"""
        <BASICSHIPPEDBYNAME>{buyer_name_clean}</BASICSHIPPEDBYNAME>
        <CONSIGNEEMAILINGNAME>{buyer_name_clean}</CONSIGNEEMAILINGNAME>{consignee_state_tag}
        <CONSIGNEECOUNTRYNAME>{country_name_clean}</CONSIGNEECOUNTRYNAME>"""
        
        # Accumulate inventory lines and totals
        inventory_entries = ""
        narrations = []
        
        for _, row in group.iterrows():
            prod_name = escape_xml_value(row.get("Product", "Item"))
            qty = to_float(row.get("Qty", 1))
            taxable = to_float(row.get("Taxable Amount", 0))
            uom = escape_xml_value(row.get("UOM", "Nos"))
            
            rate = (taxable / qty) if qty > 0 else taxable
            
            # Determine this specific product line's total GST tax rate
            c_amt = to_float(row.get("CGST Amount", 0))
            s_amt = to_float(row.get("SGST Amount", 0))
            i_amt = to_float(row.get("IGST Amount", 0))
            
            if taxable > 0:
                if c_amt > 0 or s_amt > 0:
                    item_gst_rate = int(round(((c_amt + s_amt) / taxable) * 100))
                elif i_amt > 0:
                    item_gst_rate = int(round((i_amt / taxable) * 100))
                else:
                    item_gst_rate = 0
            else:
                item_gst_rate = 0

            # Match product line to its rate-specific Sales Ledger (e.g. 18% -> Goods Sales, 12% -> Goods Sales - 12%, 0% -> Goods Sales - Nil Rated)
            allocated_sales_ledger = (
                sales_ledger_mappings.get(str(item_gst_rate))
                or sales_ledger_mappings.get(f"{item_gst_rate}%")
                or sales_ledger_mappings.get(item_gst_rate)
                or sales_ledger_name
                or (f"Goods Sales - {item_gst_rate}%" if item_gst_rate > 0 else "Goods Sales - Nil Rated")
            )
            
            inventory_entries += f"""
            <ALLINVENTORYENTRIES.LIST>
              <STOCKITEMNAME>{prod_name}</STOCKITEMNAME>
              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
              <RATE>{rate:.2f}/{uom}</RATE>
              <AMOUNT>{taxable:.2f}</AMOUNT>
              <ACTUALQTY>{qty:.2f} {uom}</ACTUALQTY>
              <BILLEDQTY>{qty:.2f} {uom}</BILLEDQTY>
              <ACCOUNTINGALLOCATIONS.LIST>
                <LEDGERNAME>{escape_xml_value(allocated_sales_ledger)}</LEDGERNAME>
                <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                <AMOUNT>{taxable:.2f}</AMOUNT>
              </ACCOUNTINGALLOCATIONS.LIST>
            </ALLINVENTORYENTRIES.LIST>"""

        # Group and calculate tax ledger entries (credits)
        invoice_cgst_by_key = {}
        invoice_sgst_by_key = {}
        invoice_igst_by_key = {}
        
        total_taxable_amount = 0.0
        total_invoice_amount = 0.0

        for _, r in group.iterrows():
            taxable = to_float(r.get("Taxable Amount", 0))
            total_taxable_amount += taxable
            total_invoice_amount += to_float(r.get("Total Amount", 0))
            
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

        # Compute sum of tax ledgers rounded exactly to 2 decimal places
        cgst_ledgers_total = sum(round(amt, 2) for amt in invoice_cgst_by_key.values())
        sgst_ledgers_total = sum(round(amt, 2) for amt in invoice_sgst_by_key.values())
        igst_ledgers_total = sum(round(amt, 2) for amt in invoice_igst_by_key.values())

        # Exact credits sum and commercial rounded invoice total
        exact_credits_sum = total_taxable_amount + cgst_ledgers_total + sgst_ledgers_total + igst_ledgers_total
        rounded_total = custom_round(total_invoice_amount)
        if rounded_total == 0:
            rounded_total = custom_round(exact_credits_sum)
            
        # Round-off offset
        roundoff_offset = round(rounded_total - exact_credits_sum, 2)

        # 1. Party Ledger Entry: Debit (negative amount in Tally XML)
        ledger_entries_xml = f"""
        <LEDGERENTRIES.LIST>
          <LEDGERNAME>{party_name_clean}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <ISPARTYLEDGER>Yes</ISPARTYLEDGER>
          <AMOUNT>-{rounded_total:.2f}</AMOUNT>
        </LEDGERENTRIES.LIST>"""

        # 2. Tax Ledger Entries: Credits (positive amounts)
        for key, amt in invoice_cgst_by_key.items():
            if amt > 0:
                ledger_name = tax_ledger_mappings.get(key, key)
                ledger_entries_xml += f"""
        <LEDGERENTRIES.LIST>
          <LEDGERNAME>{escape_xml_value(ledger_name)}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{round(amt, 2):.2f}</AMOUNT>
        </LEDGERENTRIES.LIST>"""

        for key, amt in invoice_sgst_by_key.items():
            if amt > 0:
                ledger_name = tax_ledger_mappings.get(key, key)
                ledger_entries_xml += f"""
        <LEDGERENTRIES.LIST>
          <LEDGERNAME>{escape_xml_value(ledger_name)}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{round(amt, 2):.2f}</AMOUNT>
        </LEDGERENTRIES.LIST>"""

        for key, amt in invoice_igst_by_key.items():
            if amt > 0:
                ledger_name = tax_ledger_mappings.get(key, key)
                ledger_entries_xml += f"""
        <LEDGERENTRIES.LIST>
          <LEDGERNAME>{escape_xml_value(ledger_name)}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{round(amt, 2):.2f}</AMOUNT>
        </LEDGERENTRIES.LIST>"""

        # 3. Misc / Round-off Entry: Added only if roundoff_offset is non-zero
        if abs(roundoff_offset) > 0.001:
            ledger_entries_xml += f"""
        <LEDGERENTRIES.LIST>
          <LEDGERNAME>{escape_xml_value(misc_ledger_name or 'Misc')}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{roundoff_offset:.2f}</AMOUNT>
        </LEDGERENTRIES.LIST>"""

        narration_text = f"Inv No: {inv_no_str}, Date: {date_raw}."

        tally_messages += f"""
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER VCHTYPE="Sales" ACTION="Create">
        <DATE>{date_tally}</DATE>
        <EFFECTIVEDATE>{date_tally}</EFFECTIVEDATE>
        <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
        <VOUCHERNUMBER>{escape_xml_value(inv_no_str)}</VOUCHERNUMBER>
        <REFERENCE>{escape_xml_value(inv_no_str)}</REFERENCE>
        <REFERENCEDATE>{date_tally}</REFERENCEDATE>
        <ISINVOICE>Yes</ISINVOICE>
        <PARTYLEDGERNAME>{party_name_clean}</PARTYLEDGERNAME>
        <!-- Buyer (Bill to) Details - Left Section -->
        <PARTYNAME>{buyer_name_clean}</PARTYNAME>
        <BASICBUYERNAME>{buyer_name_clean}</BASICBUYERNAME>{buyer_state_tags}{gstin_tag}
        <COUNTRYOFRESIDENCE>{country_name_clean}</COUNTRYOFRESIDENCE>
        <GSTREGISTRATIONTYPE>{reg_type_clean}</GSTREGISTRATIONTYPE>
        <!-- Consignee (Ship to) Details - Right Section -->{consignee_tags}
        <PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW>
        <NARRATION>{escape_xml_value(narration_text)}</NARRATION>
        {ledger_entries_xml}
        {inventory_entries}
      </VOUCHER>
    </TALLYMESSAGE>"""

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
        <SVCURRENTCOMPANY>{escape_xml_value(xml_company_name)}</SVCURRENTCOMPANY>
      </STATICVARIABLES>
    </DESC>
    <DATA>
      {tally_messages}
    </DATA>
  </BODY>
</ENVELOPE>"""

    with open(xml_path, "w", encoding="utf-8") as f:
        f.write(full_xml.strip())
        
    return xml_filename, len(df_std)
