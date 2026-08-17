import os
import re
import json
import requests
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as xml_escape
import pandas as pd

from config import get_tally_cache_folder, TALLY_URL
from utils.helpers import find_headers_and_df, to_float
from utils.matching import normalize_party_name
from services.tally_ledger_service import clean_tally_xml, get_cached_ledgers
from services.tally_stock_service import get_cached_stock

def escape_xml_value(value):
    """Return text safe for interpolation into Tally XML elements and attributes."""
    if value is None:
        return ""
    return xml_escape(str(value), {'"': '&quot;', "'": '&apos;'})

def create_missing_ledgers_in_tally(ledger_company, parties):
    """
    Construct XML and POST to Tally Prime to create Sundry Debtors customer ledgers.
    Updates local JSON cache upon completion.
    """
    if not ledger_company:
        raise ValueError("Ledger Company is required")
    if not parties:
        raise ValueError("Parties list is required")
        
    masters_body = ""
    for p in parties:
        p_name = normalize_party_name(p.get("name", ""))
        p_state = p.get("state", "").strip()
        p_gstin = p.get("gstin", "").strip() if p.get("gstin") else ""
        
        if not p_name:
            continue
            
        p_name_xml = escape_xml_value(p_name)
        p_state_xml = escape_xml_value(p_state)
        p_gstin_xml = escape_xml_value(p_gstin)
        
        gst_reg_type = "Regular" if p_gstin else "Unregistered"
        
        gstin_node = f"<PARTYGSTIN>{p_gstin_xml}</PARTYGSTIN>" if p_gstin else ""
        state_node = f"<LEDSTATENAME>{p_state_xml}</LEDSTATENAME>" if p_state else ""
        
        masters_body += f"""
        <TALLYMESSAGE xmlns:UDF="TallyUDF">
          <LEDGER NAME="{p_name_xml}" ACTION="Create">
            <NAME>{p_name_xml}</NAME>
            <PARENT>Sundry Debtors</PARENT>
            <ISBILLWISEON>Yes</ISBILLWISEON>
            <AFFECTSSTOCK>No</AFFECTSSTOCK>
            <COUNTRYNAME>India</COUNTRYNAME>
            {state_node}
            <GSTREGISTRATIONTYPE>{gst_reg_type}</GSTREGISTRATIONTYPE>
            {gstin_node}
          </LEDGER>
        </TALLYMESSAGE>"""
        
    envelope = f"""<ENVELOPE>
      <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Import</TALLYREQUEST>
        <TYPE>Data</TYPE>
        <ID>All Masters</ID>
      </HEADER>
      <BODY>
        <DESC>
          <STATICVARIABLES>
            <SVCURRENTCOMPANY>{escape_xml_value(ledger_company)}</SVCURRENTCOMPANY>
          </STATICVARIABLES>
        </DESC>
        <DATA>
          {masters_body}
        </DATA>
      </BODY>
    </ENVELOPE>"""
    
    r = requests.post(TALLY_URL, data=envelope.encode("utf-8"), timeout=1200)
    if r.status_code != 200:
        raise RuntimeError(f"Tally server responded with HTTP {r.status_code}")
        
    resp_text = r.content.decode("utf-8", errors="ignore")
    if "<LINEERROR>" in resp_text:
        raise RuntimeError(f"Tally returned import errors: {resp_text[:500]}")
        
    # Update local ledger cache
    safe_co = re.sub(r'[\\/*?:"<>|]', "", ledger_company).strip()
    cache_path = os.path.join(get_tally_cache_folder(), safe_co, "tally_ledger_cache.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                c_data = json.load(f)
            ledgers_set = set(c_data.get("ledgers", []))
            for p in parties:
                norm_name = normalize_party_name(p.get("name", ""))
                if norm_name:
                    ledgers_set.add(norm_name)
            c_data["ledgers"] = sorted(list(ledgers_set))
            c_data["count"] = len(c_data["ledgers"])
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(c_data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
            
    return len(parties)

def create_missing_stock_items_in_tally(file_path, sheet_name, mappings, header_row, company_name, under, units, supply_type, products):
    """
    Infers HSN and GST rate from Excel data, constructs XML, and creates Stock Items in Tally.
    Updates local stock item cache upon completion.
    """
    if not company_name:
        raise ValueError("Company Name is required")
    if not products:
        raise ValueError("Products list is required")
        
    under = (under or "Primary").strip()
    units = (units or "Nos").strip()
    supply_type = (supply_type or "Goods").strip()
    
    under_xml = escape_xml_value(under)
    units_xml = escape_xml_value(units)
    supply_type_xml = escape_xml_value(supply_type)
    
    headers, df_data = find_headers_and_df(file_path, sheet_name, header_row=header_row)
    
    product_col = mappings.get("Product")
    hsn_col = mappings.get("HSN Code")
    taxable_col = mappings.get("Taxable Amount")
    cgst_col = mappings.get("CGST Amount")
    sgst_col = mappings.get("SGST Amount")
    igst_col = mappings.get("IGST Amount")
    
    masters_body = ""
    for prod_name in products:
        prod_name = prod_name.strip()
        if not prod_name:
            continue
            
        prod_row = None
        if product_col and product_col in df_data.columns:
            matches = df_data[df_data[product_col].astype(str).str.strip() == prod_name]
            if not matches.empty:
                prod_row = matches.iloc[0]
                
        hsn_code = ""
        taxable_amt = 0.0
        cgst_amt = 0.0
        sgst_amt = 0.0
        igst_amt = 0.0
        
        if prod_row is not None:
            if hsn_col and hsn_col in df_data.columns:
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
        gst_app_status = "Applicable"
        
        if is_applicable and taxable_amt > 0:
            taxability = "Taxable"
            if cgst_amt > 0 or sgst_amt > 0:
                gst_rate = round(((cgst_amt + sgst_amt) / taxable_amt) * 100, 2)
            else:
                gst_rate = round((igst_amt / taxable_amt) * 100, 2)
        else:
            taxability = "Nil Rated"
            gst_rate = 0
                
        gst_details = f"""
        <GSTDETAILS.LIST>
          <APPLICABLEFROM>20240401</APPLICABLEFROM>
          <TAXABILITY>{taxability}</TAXABILITY>
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

        parent_tag = f"<PARENT>{under_xml}</PARENT>" if under and under.lower() != "primary" else ""

        masters_body += f"""
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <STOCKITEM NAME="{prod_name_xml}" ACTION="Create">
        <NAME>{prod_name_xml}</NAME>
        {parent_tag}
        <BASEUNITS>{units_xml}</BASEUNITS>
        <GSTAPPLICABLE>{gst_app_status}</GSTAPPLICABLE>
        <GSTTYPEOFSUPPLY>{supply_type_xml}</GSTTYPEOFSUPPLY>
        <HSNDETAILS.LIST>
          <APPLICABLEFROM>20240401</APPLICABLEFROM>
          <HSNCODE>{hsn_code_xml}</HSNCODE>
          <HSN>{hsn_code_xml}</HSN>
          <SRCOFHSNDETAILS>Specify Details Here</SRCOFHSNDETAILS>
        </HSNDETAILS.LIST>{gst_details}
      </STOCKITEM>
    </TALLYMESSAGE>"""

    envelope = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE>
    <ID>All Masters</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVCURRENTCOMPANY>{escape_xml_value(company_name)}</SVCURRENTCOMPANY>
      </STATICVARIABLES>
    </DESC>
    <DATA>
      {masters_body}
    </DATA>
  </BODY>
</ENVELOPE>"""

    r = requests.post(TALLY_URL, data=envelope.encode("utf-8"), timeout=1200)
    if r.status_code != 200:
        raise RuntimeError(f"Tally server responded with HTTP {r.status_code}")
        
    resp_text = r.content.decode("utf-8", errors="ignore")
    
    created_count = 0
    ignored_count = 0
    try:
        resp_root = ET.fromstring(clean_tally_xml(r.content))
        created_elem = resp_root.find(".//CREATED")
        if created_elem is not None and created_elem.text:
            created_count = int(created_elem.text.strip())
        ignored_elem = resp_root.find(".//IGNORED")
        if ignored_elem is not None and ignored_elem.text:
            ignored_count = int(ignored_elem.text.strip())
    except Exception:
        created_count = len(products)
        
    # Update local stock cache
    safe_co = re.sub(r'[\\/*?:"<>|]', "", company_name).strip()
    cache_path = os.path.join(get_tally_cache_folder(), safe_co, "tally_stock_cache.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                c_data = json.load(f)
            stock_set = set(c_data.get("stock_items", []))
            for prod in products:
                if prod.strip():
                    stock_set.add(prod.strip())
            c_data["stock_items"] = sorted(list(stock_set))
            c_data["count"] = len(c_data["stock_items"])
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(c_data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
            
    return created_count, ignored_count
