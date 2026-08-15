import os
import re
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

from config import get_tally_cache_folder, TALLY_URL
from services.tally_ledger_service import clean_tally_xml

def sync_stock_from_tally(company_name):
    """
    Connect to Tally Prime on port 9000 and export all inventory Stock Items.
    Saves cache to tally_companies/<company_name>/tally_stock_cache.json
    """
    company_name = company_name.strip()
    if not company_name:
        raise ValueError("Company Name is required")
        
    envelope = f"""<ENVELOPE>
        <HEADER>
            <VERSION>1</VERSION>
            <TALLYREQUEST>Export Data</TALLYREQUEST>
            <TYPE>Collection</TYPE>
            <ID>StockItem</ID>
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
    items = []
    for item_el in root.findall(".//STOCKITEM"):
        name = item_el.get("NAME") or item_el.findtext("NAME")
        if name:
            items.append(name.strip())
            
    if not items:
        for name_el in root.findall(".//NAME"):
            if name_el.text:
                items.append(name_el.text.strip())
                
    items = sorted(list(set(items)))
    
    # Save cache
    safe_co = re.sub(r'[\\/*?:"<>|]', "", company_name).strip()
    company_dir = os.path.join(get_tally_cache_folder(), safe_co)
    os.makedirs(company_dir, exist_ok=True)
    cache_path = os.path.join(company_dir, "tally_stock_cache.json")
    
    cache_payload = {
        "company_name": company_name,
        "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(items),
        "stock_items": items
    }
    
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache_payload, f, indent=2, ensure_ascii=False)
        
    return len(items), company_name

def get_cached_stock(company_name):
    """Retrieve list of cached stock item names for a specific company."""
    if not company_name:
        return []
    safe_co = re.sub(r'[\\/*?:"<>|]', "", company_name).strip()
    cache_path = os.path.join(get_tally_cache_folder(), safe_co, "tally_stock_cache.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                return cache_data.get("stock_items", [])
        except Exception:
            return []
    return []
