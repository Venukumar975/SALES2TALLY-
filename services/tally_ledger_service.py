import os
import re
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

from config import get_tally_cache_folder, TALLY_URL

def clean_tally_xml(content_bytes):
    """
    Remove illegal XML numeric character references (e.g. &#x4; or &#4;)
    that Tally sometimes emits in element values.
    """
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

def sync_ledgers_from_tally(company_name):
    """
    Connect to Tally Prime on port 9000 and export all accounting Ledgers.
    Saves cache to tally_companies/<company_name>/tally_ledger_cache.json
    """
    company_name = company_name.strip()
    if not company_name:
        raise ValueError("Company Name is required")
        
    envelope = f"""<ENVELOPE>
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
                    <SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>
                </STATICVARIABLES>
            </DESC>
        </BODY>
    </ENVELOPE>"""
    
    # 20 minutes timeout
    r = requests.post(TALLY_URL, data=envelope, timeout=1200)
    if r.status_code != 200:
        raise RuntimeError(f"Tally server responded with status {r.status_code}")
        
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
    
    # Save cache
    safe_co = re.sub(r'[\\/*?:"<>|]', "", company_name).strip()
    company_dir = os.path.join(get_tally_cache_folder(), safe_co)
    os.makedirs(company_dir, exist_ok=True)
    cache_path = os.path.join(company_dir, "tally_ledger_cache.json")
    
    cache_payload = {
        "company_name": company_name,
        "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(ledgers),
        "ledgers": ledgers
    }
    
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache_payload, f, indent=2, ensure_ascii=False)
        
    return len(ledgers), company_name

def get_cached_ledgers(company_name):
    """Retrieve list of cached ledger names for a specific company."""
    if not company_name:
        return []
    safe_co = re.sub(r'[\\/*?:"<>|]', "", company_name).strip()
    cache_path = os.path.join(get_tally_cache_folder(), safe_co, "tally_ledger_cache.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                return cache_data.get("ledgers", [])
        except Exception:
            return []
    return []

def get_all_cached_companies():
    """Scan tally_companies directory and return metadata of all cached companies."""
    companies_map = {}
    base_cache = get_tally_cache_folder()
    if os.path.exists(base_cache):
        for item in os.listdir(base_cache):
            co_dir = os.path.join(base_cache, item)
            if os.path.isdir(co_dir):
                ledger_cache = os.path.join(co_dir, "tally_ledger_cache.json")
                stock_cache = os.path.join(co_dir, "tally_stock_cache.json")
                
                co_entry = {
                    "safe_name": item,
                    "display_name": item,
                    "has_ledgers": False,
                    "ledger_count": 0,
                    "ledger_last_sync": None,
                    "has_stock": False,
                    "stock_count": 0,
                    "stock_last_sync": None
                }
                
                if os.path.exists(ledger_cache):
                    try:
                        with open(ledger_cache, "r", encoding="utf-8") as f:
                            ld = json.load(f)
                            co_entry["has_ledgers"] = True
                            co_entry["ledger_count"] = ld.get("count", len(ld.get("ledgers", [])))
                            co_entry["ledger_last_sync"] = ld.get("last_sync")
                            if ld.get("company_name"):
                                co_entry["display_name"] = ld.get("company_name")
                    except Exception:
                        pass
                        
                if os.path.exists(stock_cache):
                    try:
                        with open(stock_cache, "r", encoding="utf-8") as f:
                            sd = json.load(f)
                            co_entry["has_stock"] = True
                            co_entry["stock_count"] = sd.get("count", len(sd.get("stock_items", [])))
                            co_entry["stock_last_sync"] = sd.get("last_sync")
                            if sd.get("company_name") and not co_entry.get("display_name"):
                                co_entry["display_name"] = sd.get("company_name")
                    except Exception:
                        pass
                        
                if co_entry["has_ledgers"] or co_entry["has_stock"]:
                    companies_map[item] = co_entry
                    
    return list(companies_map.values())
