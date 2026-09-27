import os
import re
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

# Port 9000 is Tally Prime's standard XML communication port
TALLY_URL = os.environ.get("TALLY_URL", "http://127.0.0.1:9000")

def get_accounting_cache_folder():
    """Returns local cache folder for accounting voucher company ledgers."""
    local_app_data = os.environ.get("LOCALAPPDATA") or os.path.expanduser(os.path.join("~", "AppData", "Local"))
    folder = os.path.join(local_app_data, "SALES2TALLY", "Accounting Invoice Mode")
    os.makedirs(folder, exist_ok=True)
    
    # Auto-migrate from legacy accounting_tally_cache if present
    legacy_folder = os.path.join(local_app_data, "SALES2TALLY", "accounting_tally_cache")
    if os.path.exists(legacy_folder):
        try:
            for item in os.listdir(legacy_folder):
                src_item = os.path.join(legacy_folder, item)
                dst_item = os.path.join(folder, item)
                if os.path.isdir(src_item) and not os.path.exists(dst_item):
                    import shutil
                    shutil.copytree(src_item, dst_item)
        except Exception:
            pass
            
    return folder

def get_accounting_saved_companies():
    """Returns list of companies saved in Accounting Invoice Mode cache."""
    cache_root = get_accounting_cache_folder()
    companies = []
    if not os.path.exists(cache_root):
        return companies
        
    for entry in os.listdir(cache_root):
        co_dir = os.path.join(cache_root, entry)
        if not os.path.isdir(co_dir):
            continue
        cache_file = os.path.join(co_dir, "accounting_ledgers_cache.json")
        ledgers_file = os.path.join(co_dir, "ledgers.json")
        
        target_file = cache_file if os.path.exists(cache_file) else (ledgers_file if os.path.exists(ledgers_file) else None)
        if target_file:
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    company_name = data.get("company_name") or entry
                    ledgers = data.get("ledgers", [])
                    last_sync = data.get("last_sync", "")
                    if not last_sync and os.path.exists(target_file):
                        mtime = os.path.getmtime(target_file)
                        last_sync = datetime.fromtimestamp(mtime).strftime("%d-%b-%Y")
                    elif last_sync:
                        last_sync = last_sync.split()[0]
                    companies.append({
                        "company_name": company_name,
                        "display_name": company_name,
                        "count": data.get("count", len(ledgers)),
                        "last_sync": last_sync
                    })
            except Exception:
                companies.append({
                    "company_name": entry,
                    "display_name": entry,
                    "count": 0,
                    "last_sync": ""
                })
    companies.sort(key=lambda x: x["company_name"].lower())
    return companies


def clean_tally_xml(content_bytes):
    """Remove illegal XML character entities emitted by Tally."""
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
        except Exception:
            pass
        return ent
    cleaned = re.sub(r'&#x?[0-9a-fA-F]+;', repl, text)
    return cleaned.encode("utf-8", errors="ignore")

def get_tally_open_companies():
    """Retrieve list of currently loaded companies in Gateway of Tally."""
    envelope = """<ENVELOPE>
        <HEADER>
            <VERSION>1</VERSION>
            <TALLYREQUEST>Export Data</TALLYREQUEST>
            <TYPE>Collection</TYPE>
            <ID>List of Companies</ID>
        </HEADER>
        <BODY>
            <DESC>
                <STATICVARIABLES>
                    <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                </STATICVARIABLES>
                <TDL>
                    <TDLMESSAGE>
                        <COLLECTION NAME="List of Companies">
                            <TYPE>Company</TYPE>
                            <FETCH>NAME</FETCH>
                        </COLLECTION>
                    </TDLMESSAGE>
                </TDL>
            </DESC>
        </BODY>
    </ENVELOPE>"""
    try:
        # 20-minute timeout for Tally requests
        r = requests.post(TALLY_URL, data=envelope.encode("utf-8"), timeout=1200)
        if r.status_code != 200:
            return []
        root = ET.fromstring(clean_tally_xml(r.content))
        companies = []
        for c in root.findall(".//COMPANY"):
            name = c.get("NAME") or c.findtext("NAME")
            if name and name.strip():
                companies.append(name.strip())
        return sorted(list(set(companies)))
    except Exception:
        return []

def sync_accounting_ledgers_from_tally(company_name):
    """
    Connects to Tally Prime on port 9000, exports all ledgers with their parent groups,
    caches to disk, and returns detailed dictionary of ledgers.
    """
    company_name = (company_name or "").strip()
    if not company_name:
        raise ValueError("Tally Company Name is required")

    open_cos = get_tally_open_companies()
    if open_cos:
        matched = next((c for c in open_cos if c.lower() == company_name.lower()), None)
        if not matched:
            open_list_str = ", ".join([f"'{c}'" for c in open_cos])
            raise RuntimeError(
                f"Company '{company_name}' is not currently loaded in Gateway of Tally. "
                f"Open companies in Tally: {open_list_str}. "
                f"Please ensure company name is typed exactly as shown in Gateway of Tally."
            )
        company_name = matched

    envelope = f"""<ENVELOPE>
      <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export Data</TALLYREQUEST>
        <TYPE>Collection</TYPE>
        <ID>DetailedLedgers</ID>
      </HEADER>
      <BODY>
        <DESC>
          <STATICVARIABLES>
            <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
            <SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>
          </STATICVARIABLES>
          <TDL>
            <TDLMESSAGE>
              <COLLECTION NAME="DetailedLedgers">
                <TYPE>Ledger</TYPE>
                <FETCH>NAME,PARENT,COUNTRYNAME,COUNTRYOFRESIDENCE,LEDSTATENAME,STATENAME,GSTREGISTRATIONTYPE,PARTYGSTIN,PINCODE,LEDMAILINGDETAILS.*,LEDGSTREGDETAILS.*</FETCH>
              </COLLECTION>
            </TDLMESSAGE>
          </TDL>
        </DESC>
      </BODY>
    </ENVELOPE>"""

    # 20-minute timeout for Tally large ledger database retrieval
    r = requests.post(TALLY_URL, data=envelope.encode("utf-8"), timeout=1200)
    if r.status_code != 200:
        raise RuntimeError(f"Tally server returned status {r.status_code}")

    cleaned = clean_tally_xml(r.content)
    root = ET.fromstring(cleaned)

    ledgers = []
    ledger_details = {}

    for l_elem in root.findall(".//LEDGER"):
        name = l_elem.get("NAME", "").strip()
        if not name:
            name_elem = l_elem.find("NAME")
            if name_elem is not None and name_elem.text:
                name = name_elem.text.strip()
        if not name:
            continue

        parent = (l_elem.findtext("PARENT") or "").strip()
        state = (l_elem.findtext("LEDSTATENAME") or l_elem.findtext("STATENAME") or "").strip()
        country = (l_elem.findtext("COUNTRYNAME") or l_elem.findtext("COUNTRYOFRESIDENCE") or "India").strip()
        reg_type = (l_elem.findtext("GSTREGISTRATIONTYPE") or "").strip()
        gstin = (l_elem.findtext("PARTYGSTIN") or "").strip()

        mailing = l_elem.find(".//LEDMAILINGDETAILS.LIST")
        if mailing is not None:
            if not state:
                state = (mailing.findtext("STATE") or "").strip()
            if not country or country == "India":
                c = (mailing.findtext("COUNTRY") or "").strip()
                if c: country = c

        gst_reg = l_elem.find(".//LEDGSTREGDETAILS.LIST")
        if gst_reg is not None:
            if not reg_type:
                reg_type = (gst_reg.findtext("GSTREGISTRATIONTYPE") or "").strip()
            if not gstin:
                gstin = (gst_reg.findtext("GSTIN") or "").strip()
            if not state:
                pos = (gst_reg.findtext("PLACEOFSUPPLY") or "").strip()
                if pos: state = pos

        ledgers.append(name)
        ledger_details[name.lower()] = {
            "name": name,
            "parent": parent,
            "state": state or "Andhra Pradesh",
            "country": country or "India",
            "registration_type": reg_type or ("Regular" if gstin else "Unregistered/Consumer"),
            "gstin": gstin
        }

    unique_ledgers = sorted(list(set(ledgers)))

    # Save to local cache under Accounting Invoice Mode / <company_name>
    safe_co = re.sub(r'[\\/*?:"<>|]', "", company_name).strip()
    co_dir = os.path.join(get_accounting_cache_folder(), safe_co)
    os.makedirs(co_dir, exist_ok=True)
    cache_path = os.path.join(co_dir, "accounting_ledgers_cache.json")
    ledgers_path = os.path.join(co_dir, "ledgers.json")

    last_sync_str = datetime.now().strftime("%d-%b-%Y")
    payload = {
        "company_name": company_name,
        "last_sync": last_sync_str,
        "count": len(unique_ledgers),
        "ledgers": unique_ledgers,
        "ledger_details": ledger_details
    }

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    ledgers_payload = {
        "company_name": company_name,
        "last_sync": last_sync_str,
        "count": len(unique_ledgers),
        "ledgers": unique_ledgers
    }
    with open(ledgers_path, "w", encoding="utf-8") as f:
        json.dump(ledgers_payload, f, indent=2, ensure_ascii=False)

    return len(unique_ledgers), company_name, unique_ledgers, ledger_details, last_sync_str

def _resolve_company_dir(company_name):
    if not company_name:
        return None
    cache_root = get_accounting_cache_folder()
    safe_co = re.sub(r'[\\/*?:"<>|]', "", company_name).strip()
    direct = os.path.join(cache_root, safe_co)
    if os.path.isdir(direct):
        return direct
    # Case-insensitive search
    for entry in os.listdir(cache_root):
        if entry.lower() == safe_co.lower():
            p = os.path.join(cache_root, entry)
            if os.path.isdir(p):
                return p
    return None

def get_cached_accounting_company_info(company_name):
    """Retrieve cached company data including ledgers, details, count, and last sync date."""
    co_dir = _resolve_company_dir(company_name)
    if not co_dir:
        return {"ledgers": [], "ledger_details": {}, "count": 0, "last_sync": ""}
    for fname in ("accounting_ledgers_cache.json", "ledgers.json"):
        cache_path = os.path.join(co_dir, fname)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    ledgers = data.get("ledgers", [])
                    details = data.get("ledger_details", {})
                    last_sync = data.get("last_sync", "")
                    if not last_sync:
                        mtime = os.path.getmtime(cache_path)
                        last_sync = datetime.fromtimestamp(mtime).strftime("%d-%b-%Y")
                    elif len(last_sync.split()) > 1:
                        last_sync = last_sync.split()[0]
                    return {
                        "company_name": data.get("company_name", company_name),
                        "count": data.get("count", len(ledgers)),
                        "last_sync": last_sync,
                        "ledgers": ledgers,
                        "ledger_details": details
                    }
            except Exception:
                pass
    return {"ledgers": [], "ledger_details": {}, "count": 0, "last_sync": ""}

def get_cached_accounting_ledgers(company_name):
    """Retrieve list of cached ledgers for the company."""
    info = get_cached_accounting_company_info(company_name)
    return info.get("ledgers", [])

def get_cached_accounting_ledger_details(company_name):
    """Retrieve detailed ledger map for the company."""
    info = get_cached_accounting_company_info(company_name)
    return info.get("ledger_details", {})
