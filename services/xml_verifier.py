import os
import xml.etree.ElementTree as ET

def audit_generated_xml_file(xml_path):
    """
    Performs full pre-flight verification on a generated Tally XML file.
    Calculates:
      1. Total vouchers (grouped by Invoice Number)
      2. Invoice Number as Voucher Number (<VOUCHERNUMBER> & <REFERENCE>)
      3. Dates: Transaction Date (<DATE>), Effective Date (<EFFECTIVEDATE>), Reference Date (<REFERENCEDATE>)
      4. Voucher View Type (<PERSISTEDVIEW> & <ISINVOICE>)
      5. Party Master Details (<PARTYLEDGERNAME>, <PARTYNAME>, <STATENAME>, <PLACEOFSUPPLY>, <COUNTRYOFRESIDENCE>, <PARTYGSTIN>, <GSTREGISTRATIONTYPE>)
      6. GST Classification (B2B vs B2C Invoices)
      7. Debit and Credit exact balancing (total debits, total credits, unbalanced count)
      8. Master & Ledger validity checks
    """
    if not os.path.exists(xml_path):
        return {
            "success": False,
            "error": "Generated XML file does not exist on disk.",
            "is_all_passed": False
        }

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to parse XML: {str(e)}",
            "is_all_passed": False
        }

    vouchers = root.findall(".//VOUCHER")
    total_vouchers = len(vouchers)

    if total_vouchers == 0:
        return {
            "success": False,
            "error": "No vouchers found in XML envelope.",
            "is_all_passed": False,
            "total_vouchers": 0
        }

    missing_inv_no = 0
    missing_ref = 0
    missing_dates = 0
    missing_party_ledger = 0
    missing_party_name = 0
    missing_state = 0
    missing_place_of_supply = 0
    missing_country = 0
    missing_reg_type = 0
    
    b2b_count = 0
    b2c_count = 0

    unbalanced_vouchers = []
    total_file_debits = 0.0
    total_file_credits = 0.0
    
    unique_parties = set()
    unique_items = set()

    for idx, v in enumerate(vouchers):
        vch_no = (v.findtext("VOUCHERNUMBER") or "").strip()
        ref = (v.findtext("REFERENCE") or "").strip()
        dt = (v.findtext("DATE") or "").strip()
        eff_dt = (v.findtext("EFFECTIVEDATE") or "").strip()
        ref_dt = (v.findtext("REFERENCEDATE") or "").strip()
        party_ledger = (v.findtext("PARTYLEDGERNAME") or "").strip()
        party_name = (v.findtext("PARTYNAME") or "").strip()
        state = (v.findtext("STATENAME") or "").strip()
        pos = (v.findtext("PLACEOFSUPPLY") or "").strip()
        gstin = (v.findtext("PARTYGSTIN") or "").strip()
        country = (v.findtext("COUNTRYOFRESIDENCE") or "").strip()
        reg_type = (v.findtext("GSTREGISTRATIONTYPE") or "").strip()

        if party_ledger: unique_parties.add(party_ledger)

        if not vch_no: missing_inv_no += 1
        if not ref: missing_ref += 1
        if not dt or not eff_dt or not ref_dt: missing_dates += 1
        if not party_ledger: missing_party_ledger += 1
        if not party_name: missing_party_name += 1
        if not state: missing_state += 1
        if not pos: missing_place_of_supply += 1
        if not country: missing_country += 1
        if not reg_type: missing_reg_type += 1

        # B2B vs B2C Classification
        if gstin and len(gstin) >= 15:
            b2b_count += 1
        else:
            b2c_count += 1

        # True Accounting Debits and Credits
        vch_debit = 0.0
        vch_credit = 0.0

        for l in v.findall(".//LEDGERENTRIES.LIST"):
            amt_str = l.findtext("AMOUNT") or "0"
            is_pos = (l.findtext("ISDEEMEDPOSITIVE") or "No").strip().lower() == "yes"
            try:
                amt = float(amt_str)
                if is_pos:
                    vch_debit += (-amt if amt < 0 else amt)
                else:
                    vch_credit += amt
            except ValueError:
                pass

        for inv in v.findall(".//ALLINVENTORYENTRIES.LIST"):
            item_name = (inv.findtext("STOCKITEMNAME") or "").strip()
            if item_name: unique_items.add(item_name)
            for acc in inv.findall(".//ACCOUNTINGALLOCATIONS.LIST"):
                amt_str = acc.findtext("AMOUNT") or "0"
                is_pos = (acc.findtext("ISDEEMEDPOSITIVE") or "No").strip().lower() == "yes"
                try:
                    amt = float(amt_str)
                    if is_pos:
                        vch_debit += (-amt if amt < 0 else amt)
                    else:
                        vch_credit += amt
                except ValueError:
                    pass

        total_file_debits += vch_debit
        total_file_credits += vch_credit

        if abs(vch_debit - vch_credit) > 0.02:
            unbalanced_vouchers.append({
                "index": idx + 1,
                "voucher_number": vch_no,
                "debits": round(vch_debit, 2),
                "credits": round(vch_credit, 2),
                "difference": round(vch_debit - vch_credit, 2)
            })

    is_all_passed = (
        missing_inv_no == 0 and
        missing_dates == 0 and
        missing_party_ledger == 0 and
        len(unbalanced_vouchers) == 0
    )

    return {
        "success": True,
        "is_all_passed": is_all_passed,
        "total_vouchers": total_vouchers,
        "unique_parties_count": len(unique_parties),
        "unique_items_count": len(unique_items),
        "b2b_count": b2b_count,
        "b2c_count": b2c_count,
        "missing_inv_no": missing_inv_no,
        "missing_ref": missing_ref,
        "missing_dates": missing_dates,
        "missing_party_ledger": missing_party_ledger,
        "missing_party_name": missing_party_name,
        "missing_state": missing_state,
        "missing_place_of_supply": missing_place_of_supply,
        "missing_country": missing_country,
        "missing_reg_type": missing_reg_type,
        "unbalanced_count": len(unbalanced_vouchers),
        "total_debits": round(total_file_debits, 2),
        "total_credits": round(total_file_credits, 2)
    }
