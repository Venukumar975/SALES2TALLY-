import re

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
