import re

GST_STATE_MAP = {
    "01": "Jammu & Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra & Nagar Haveli and Daman & Diu",
    "27": "Maharashtra",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman & Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory"
}

STATE_ALIAS_MAP = {
    "ap": "Andhra Pradesh",
    "andhra": "Andhra Pradesh",
    "andhra pradesh": "Andhra Pradesh",
    "ts": "Telangana",
    "tg": "Telangana",
    "telangana": "Telangana",
    "ka": "Karnataka",
    "karnataka": "Karnataka",
    "tn": "Tamil Nadu",
    "tamil nadu": "Tamil Nadu",
    "tamilnadu": "Tamil Nadu",
    "kl": "Kerala",
    "kerala": "Kerala",
    "mh": "Maharashtra",
    "maharashtra": "Maharashtra",
    "delhi": "Delhi",
    "up": "Uttar Pradesh",
    "uttar pradesh": "Uttar Pradesh",
    "mp": "Madhya Pradesh",
    "madhya pradesh": "Madhya Pradesh",
    "wb": "West Bengal",
    "west bengal": "West Bengal",
    "gujarat": "Gujarat",
    "gj": "Gujarat",
    "odisha": "Odisha",
    "orissa": "Odisha",
    "punjab": "Punjab",
    "pb": "Punjab",
    "haryana": "Haryana",
    "hr": "Haryana",
    "rajasthan": "Rajasthan",
    "rj": "Rajasthan",
    "bihar": "Bihar",
    "br": "Bihar"
}

def clean_and_resolve_state(state, gstin=""):
    """
    Standardize state name to Tally Prime standard names.
    Supports state codes (e.g. '37-Andhra Pradesh'), aliases ('AP', 'TG'),
    and falls back to resolving state from the first 2 digits of GSTIN if missing.
    """
    state_str = str(state or "").strip()
    gstin_str = str(gstin or "").strip()
    
    # 1. Match code prefix like '37-Andhra Pradesh', '37 - AP', '37'
    m_code = re.match(r"^(\d{2})\s*[-:]?\s*(.*)$", state_str)
    if m_code:
        code, rest = m_code.group(1), m_code.group(2).strip()
        if code in GST_STATE_MAP:
            return GST_STATE_MAP[code]
        state_str = rest

    # 2. Check alias mapping
    st_clean = re.sub(r'[^a-zA-Z\s]', '', state_str).strip().lower()
    if st_clean in STATE_ALIAS_MAP:
        return STATE_ALIAS_MAP[st_clean]

    for std_state in GST_STATE_MAP.values():
        if st_clean == std_state.lower().replace('&', 'and') or st_clean == std_state.lower():
            return std_state

    # 3. Fallback to GSTIN first 2 digits if available
    if gstin_str and len(gstin_str) >= 2:
        g_code = gstin_str[:2]
        if g_code in GST_STATE_MAP:
            return GST_STATE_MAP[g_code]

    return state_str

def normalize_party_name(value):
    """Create a Tally-friendly party name from an Excel party name."""
    if value is None:
        return ""

    name = str(value).strip()
    replacements = {
        "&": " and ",
        "+": " plus ",
        "@": " at ",
    }
    for symbol, word in replacements.items():
        name = name.replace(symbol, word)

    # Keep letters, numbers and spaces only. This prevents punctuation from
    # producing invalid or inconsistently named Tally ledgers.
    name = re.sub(r"[^A-Za-z0-9\s]", " ", name)
    return re.sub(r"\s+", " ", name).strip()

def clean_and_tokenize(name):
    if not name:
        return []
    name = str(name).lower()
    # Replace non-alphanumeric characters with space
    name = re.sub(r'[^a-z0-9\s]', ' ', name)
    # Strip common business suffixes
    suffixes = [
        'private limited', 'pvt ltd', 'pvt. ltd.', 'pvt.ltd.', 'p ltd', 'p. ltd.',
        'limited', 'ltd', 'ltd.',
        'llp', 'l.l.p.',
        'inc', 'inc.', 'incorporated',
        'corp', 'corp.', 'corporation',
        'co', 'co.', 'company',
        'enterprises', 'enterprise',
        'industries', 'industry',
        'solutions', 'services',
        'traders', 'trading',
        'agency', 'agencies',
        'india', 'intl', 'international'
    ]
    for s in suffixes:
        name = re.sub(r'\b' + re.escape(s) + r'\b', ' ', name)
    
    tokens = [w for w in name.split() if len(w) > 1]
    return tokens

def get_word_match_score(name1, name2):
    t1 = clean_and_tokenize(name1)
    t2 = clean_and_tokenize(name2)
    if not t1 or not t2:
        return 0.0
    
    set1 = set(t1)
    set2 = set(t2)
    
    intersection = set1.intersection(set2)
    union = set1.union(set2)
    
    jaccard = len(intersection) / len(union) if union else 0.0
    coverage = len(intersection) / min(len(set1), len(set2)) if min(len(set1), len(set2)) > 0 else 0.0
    
    return max(jaccard, coverage * 0.85)

def compact_party_name(name):
    if not name:
        return ""
    return re.sub(r'[^a-z0-9]', '', str(name).lower())

def find_matching_ledger(excel_party, tally_ledgers):
    """
    Given an Excel party name and a list of Tally ledgers,
    find the best matching Tally ledger name. Returns excel_party if no match found.
    """
    if not excel_party or not tally_ledgers:
        return excel_party
    
    ep_lower = str(excel_party).strip().lower()
    
    # 1. Exact case-insensitive match
    for l in tally_ledgers:
        if l.strip().lower() == ep_lower:
            return l
    
    # 2. Compact string match
    ep_compact = compact_party_name(excel_party)
    if ep_compact:
        for l in tally_ledgers:
            if compact_party_name(l) == ep_compact:
                return l
                
    # 3. Best word match score >= 0.60
    best_match = None
    best_score = 0.0
    for l in tally_ledgers:
        score = get_word_match_score(excel_party, l)
        if score > best_score:
            best_score = score
            best_match = l
            
    if best_score >= 0.60:
        return best_match
        
    return excel_party
