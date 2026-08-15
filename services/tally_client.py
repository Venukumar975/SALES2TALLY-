import os
import re
import json
import requests
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as xml_escape
from datetime import datetime

from config import TALLY_CACHE_FOLDER, TALLY_URL

def get_tally_cache_folder():
    """Keep sync data beside the app so the server can always read and write it."""
    os.makedirs(TALLY_CACHE_FOLDER, exist_ok=True)
    return TALLY_CACHE_FOLDER

def escape_xml_value(value):
    """Return text safe for interpolation into Tally XML elements and attributes."""
    if value is None:
        return ""
    return xml_escape(str(value), {'"': '&quot;', "'": '&apos;'})

def clean_tally_xml(content_bytes):
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
    """Export and cache all ledgers from Tally Prime."""
    ledger_xml = """<ENVELOPE>
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
                </STATICVARIABLES>
            </DESC>
        </BODY>
    </ENVELOPE>"""
    
    # 20 minutes timeout
    r = requests.post(TALLY_URL, data=ledger_xml, timeout=1200)
    if r.status_code != 200:
        raise Exception(f"Tally server responded with status {r.status_code}")
        
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
    if not ledgers:
        raise Exception("No ledgers were retrieved. Verify that a company is open in Tally Prime.")
        
    cache_dir = get_tally_cache_folder()
    safe_company_name = re.sub(r'[\\/*?:"<>|]', "", company_name).strip()
    company_folder = os.path.join(cache_dir, safe_company_name)
    os.makedirs(company_folder, exist_ok=True)
    
    cache_path = os.path.join(company_folder, "tally_ledger_cache.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump({
            "company_name": company_name,
            "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ledgers": ledgers
        }, f, indent=4)
        
    return ledgers

def sync_stock_from_tally(company_name):
    """Export and cache all stock items from Tally Prime."""
    stock_xml = """<ENVELOPE>
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
                </STATICVARIABLES>
            </DESC>
        </BODY>
    </ENVELOPE>"""
    
    r = requests.post(TALLY_URL, data=stock_xml, timeout=1200)
    if r.status_code != 200:
        raise Exception(f"Tally server responded with status {r.status_code}")
        
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
    if not items:
        raise Exception("No stock items were retrieved. Verify that a company is open in Tally Prime.")
        
    cache_dir = get_tally_cache_folder()
    safe_company_name = re.sub(r'[\\/*?:"<>|]', "", company_name).strip()
    company_folder = os.path.join(cache_dir, safe_company_name)
    os.makedirs(company_folder, exist_ok=True)
    
    cache_path = os.path.join(company_folder, "tally_stock_cache.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump({
            "company_name": company_name,
            "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "items": items
        }, f, indent=4)
        
    return items

def get_cached_companies():
    """Retrieve metadata of all cached companies."""
    cache_dir = get_tally_cache_folder()
    if not os.path.exists(cache_dir):
        return []
        
    companies_map = {}
    for item in os.listdir(cache_dir):
        item_path = os.path.join(cache_dir, item)
        if os.path.isdir(item_path):
            display_name = item
            ledger_last_sync = ""
            stock_last_sync = ""
            has_ledgers = False
            has_stock = False
            ledger_count = 0
            stock_count = 0
            
            ledger_cache = os.path.join(item_path, "tally_ledger_cache.json")
            if os.path.exists(ledger_cache):
                try:
                    with open(ledger_cache, "r", encoding="utf-8") as f:
                        c_data = json.load(f)
                        display_name = c_data.get("company_name", display_name)
                        ledger_last_sync = c_data.get("last_sync", "")
                        ledger_count = len(c_data.get("ledgers", []))
                        has_ledgers = True
                except:
                    pass
                    
            stock_cache = os.path.join(item_path, "tally_stock_cache.json")
            if os.path.exists(stock_cache):
                try:
                    with open(stock_cache, "r", encoding="utf-8") as f:
                        c_data = json.load(f)
                        display_name = c_data.get("company_name", display_name)
                        stock_last_sync = c_data.get("last_sync", "")
                        stock_count = len(c_data.get("items", []))
                        has_stock = True
                except:
                    pass
                    
            if has_ledgers or has_stock:
                companies_map[item] = {
                    "safe_name": item,
                    "display_name": display_name,
                    "ledger_last_sync": ledger_last_sync,
                    "stock_last_sync": stock_last_sync,
                    "has_ledgers": has_ledgers,
                    "has_stock": has_stock,
                    "ledger_count": ledger_count,
                    "stock_count": stock_count
                }
                
    return list(companies_map.values())

def get_cached_ledgers(company_name):
    """Get ledger list for a specific company from local cache."""
    safe_co = re.sub(r'[\\/*?:"<>|]', "", company_name).strip()
    cache_path = os.path.join(get_tally_cache_folder(), safe_co, "tally_ledger_cache.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
            return cache_data.get("ledgers", [])
    return []

def get_cached_stock(company_name):
    """Get stock items for a specific company from local cache."""
    safe_co = re.sub(r'[\\/*?:"<>|]', "", company_name).strip()
    cache_path = os.path.join(get_tally_cache_folder(), safe_co, "tally_stock_cache.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
            return cache_data.get("items", [])
    return []
