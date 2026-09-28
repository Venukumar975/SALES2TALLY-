import os
import uuid
import pandas as pd
from flask import Blueprint, request, jsonify, send_from_directory

from config import UPLOAD_FOLDER, PROCESSED_FOLDER
from accounting_voucher.services.tally_service import (
    get_tally_open_companies,
    get_accounting_saved_companies,
    sync_accounting_ledgers_from_tally,
    get_cached_accounting_ledgers,
    get_cached_accounting_ledger_details,
    get_cached_accounting_company_info
)
from accounting_voucher.services.analysis_service import analyze_spares_excel
from accounting_voucher.services.xml_generator import generate_accounting_vouchers_xml

accounting_bp = Blueprint("accounting_bp", __name__)

@accounting_bp.route("/api/accounting/saved-companies", methods=["GET"])
def api_get_saved_companies():
    """Retrieve saved companies in Accounting Invoice Mode cache without calling Tally."""
    try:
        saved = get_accounting_saved_companies()
        return jsonify({
            "success": True,
            "companies": saved,
            "open_companies": []
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@accounting_bp.route("/api/accounting/load-company", methods=["POST"])
def api_load_company():
    """Load cached ledgers for a saved company in Accounting Invoice Mode."""
    data = request.json or {}
    company_name = (data.get("company_name") or "").strip()
    if not company_name:
        return jsonify({"success": False, "error": "Company Name is required"}), 400
    try:
        co_info = get_cached_accounting_company_info(company_name)
        return jsonify({
            "success": True,
            "company_name": company_name,
            "count": co_info.get("count", 0),
            "last_sync": co_info.get("last_sync", ""),
            "ledgers": co_info.get("ledgers", []),
            "ledger_details": co_info.get("ledger_details", {})
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@accounting_bp.route("/api/accounting/companies", methods=["GET"])
def api_get_companies():
    """Retrieve open companies in Tally."""
    try:
        companies = get_tally_open_companies()
        return jsonify({"success": True, "companies": companies})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@accounting_bp.route("/api/accounting/sync-tally", methods=["POST"])
def api_sync_tally():
    """Sync live ledgers from Tally Prime port 9000 for target company."""
    data = request.json or {}
    company_name = (data.get("company_name") or "").strip()
    if not company_name:
        return jsonify({"success": False, "error": "Tally Company Name is required"}), 400
    try:
        count, co_name, ledgers, details, last_sync = sync_accounting_ledgers_from_tally(company_name)
        return jsonify({
            "success": True,
            "company_name": co_name,
            "count": count,
            "last_sync": last_sync,
            "ledgers": ledgers,
            "ledger_details": details
        })
    except Exception as e:
        # Fall back to local cache if Tally is offline
        co_info = get_cached_accounting_company_info(company_name)
        cached = co_info.get("ledgers", [])
        if cached:
            return jsonify({
                "success": True,
                "company_name": company_name,
                "count": co_info.get("count", len(cached)),
                "last_sync": co_info.get("last_sync", ""),
                "ledgers": cached,
                "ledger_details": co_info.get("ledger_details", {}),
                "warning": f"Could not connect to live Tally ({str(e)}). Loaded {len(cached)} cached ledgers."
            })
        return jsonify({"success": False, "error": f"Failed to sync with Tally: {str(e)}"}), 500

@accounting_bp.route("/api/accounting/upload", methods=["POST"])
def api_upload_excel():
    """Upload spares register Excel workbook."""
    if "excel_file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    file = request.files["excel_file"]
    if file.filename == "":
        return jsonify({"success": False, "error": "No file selected"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".xlsx", ".xls"):
        return jsonify({"success": False, "error": "Please upload an Excel file (.xlsx or .xls)"}), 400

    file_id = str(uuid.uuid4())
    save_path = os.path.join(UPLOAD_FOLDER, f"{file_id}{ext}")
    file.save(save_path)

    try:
        excel_file_obj = pd.ExcelFile(save_path)
        sheets = excel_file_obj.sheet_names
        return jsonify({
            "success": True,
            "file_id": file_id,
            "original_filename": file.filename,
            "sheets": sheets
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to read Excel: {str(e)}"}), 500

@accounting_bp.route("/api/accounting/analyze", methods=["POST"])
def api_analyze_spares():
    """Analyze uploaded Excel sheet to detect HSN codes, rates, taxes, and auto-map ledgers."""
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name", 0)
    company_name = (data.get("company_name") or "").strip()
    column_mappings = data.get("column_mappings")

    if not file_id:
        return jsonify({"success": False, "error": "Missing file_id"}), 400

    file_path = None
    for ext in ('.xlsx', '.xls'):
        p = os.path.join(UPLOAD_FOLDER, f"{file_id}{ext}")
        if os.path.exists(p):
            file_path = p
            break

    if not file_path:
        return jsonify({"success": False, "error": "Uploaded file not found"}), 404

    # Get available ledgers from cache or live
    available_ledgers = get_cached_accounting_ledgers(company_name) if company_name else []

    try:
        analysis_result = analyze_spares_excel(
            file_path=file_path,
            sheet_name=sheet_name,
            column_mappings=column_mappings,
            available_ledgers=available_ledgers
        )
        analysis_result["available_ledgers"] = available_ledgers
        return jsonify(analysis_result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@accounting_bp.route("/api/accounting/generate", methods=["POST"])
def api_generate_xml():
    """Generate Tally Prime Accounting Vouchers XML."""
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name", 0)
    column_mappings = data.get("column_mappings", {})
    original_filename = data.get("original_filename", "spares_register.xlsx")
    company_name = (data.get("company_name") or "").strip()
    voucher_type = (data.get("voucher_type") or "GST SALES").strip()
    party_name = (data.get("party_name") or "Srikara Tuni Branch Service").strip()
    party_details = data.get("party_details", {})
    hsn_ledger_mappings = data.get("hsn_ledger_mappings", {})
    tax_ledger_mappings = data.get("tax_ledger_mappings", {})
    misc_ledger_name = (data.get("misc_ledger_name") or "Misc Exp").strip()
    narration_prefix = data.get("narration_prefix", "GST Invoice Number :: ")

    if not file_id or not column_mappings:
        return jsonify({"success": False, "error": "Missing file parameters"}), 400
    if not company_name:
        return jsonify({"success": False, "error": "Tally Company Name is required"}), 400
    if not party_name:
        return jsonify({"success": False, "error": "Party A/c Name is required"}), 400

    file_path = None
    for ext in ('.xlsx', '.xls'):
        p = os.path.join(UPLOAD_FOLDER, f"{file_id}{ext}")
        if os.path.exists(p):
            file_path = p
            break

    if not file_path:
        return jsonify({"success": False, "error": "Uploaded file not found"}), 404

    try:
        filename, voucher_count, audit_summary = generate_accounting_vouchers_xml(
            file_path=file_path,
            sheet_name=sheet_name,
            column_mappings=column_mappings,
            original_filename=original_filename,
            company_name=company_name,
            voucher_type=voucher_type,
            party_name=party_name,
            party_details=party_details,
            hsn_ledger_mappings=hsn_ledger_mappings,
            tax_ledger_mappings=tax_ledger_mappings,
            misc_ledger_name=misc_ledger_name,
            narration_prefix=narration_prefix,
            from_date=data.get("from_date"),
            to_date=data.get("to_date")
        )
        return jsonify({
            "success": True,
            "filename": filename,
            "voucher_count": voucher_count,
            "download_url": f"/download/{filename}",
            "audit_summary": audit_summary
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@accounting_bp.route("/api/accounting/get-date-range", methods=["POST"])
def api_get_date_range():
    """Retrieve min and max dates for a specified column in the uploaded spares workbook."""
    from accounting_voucher.services.analysis_service import get_spares_date_range
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name", 0)
    date_col = data.get("date_col")

    if not file_id or not date_col:
        return jsonify({"success": False, "error": "Missing parameters"}), 400

    file_path = None
    for ext in ('.xlsx', '.xls'):
        p = os.path.join(UPLOAD_FOLDER, f"{file_id}{ext}")
        if os.path.exists(p):
            file_path = p
            break

    if not file_path:
        return jsonify({"success": False, "error": "File not found"}), 404

    try:
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        min_date, max_date = get_spares_date_range(df, date_col)
        return jsonify({"success": True, "min_date": min_date, "max_date": max_date})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@accounting_bp.route("/api/accounting/generate-excel", methods=["POST"])
def api_generate_excel():
    """Generate formatted 2-sheet summary Excel for Accounting Invoices."""
    from accounting_voucher.services.excel_generator import generate_accounting_formatted_excel
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name", 0)
    column_mappings = data.get("column_mappings", {})
    original_filename = data.get("original_filename", "spares_register.xlsx")
    party_name = (data.get("party_name") or "Srikara Tuni Branch Service").strip()
    hsn_ledger_mappings = data.get("hsn_ledger_mappings", {})
    misc_ledger_name = (data.get("misc_ledger_name") or "Misc Exp").strip()
    from_date = data.get("from_date")
    to_date = data.get("to_date")

    if not file_id or not column_mappings:
        return jsonify({"success": False, "error": "Missing file parameters"}), 400

    file_path = None
    for ext in ('.xlsx', '.xls'):
        p = os.path.join(UPLOAD_FOLDER, f"{file_id}{ext}")
        if os.path.exists(p):
            file_path = p
            break

    if not file_path:
        return jsonify({"success": False, "error": "Uploaded file not found"}), 404

    try:
        filename, row_count = generate_accounting_formatted_excel(
            file_path=file_path,
            sheet_name=sheet_name,
            column_mappings=column_mappings,
            original_filename=original_filename,
            party_name=party_name,
            hsn_ledger_mappings=hsn_ledger_mappings,
            misc_ledger_name=misc_ledger_name,
            from_date=from_date,
            to_date=to_date
        )
        return jsonify({
            "success": True,
            "filename": filename,
            "row_count": row_count,
            "download_url": f"/download/{filename}"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@accounting_bp.route("/api/accounting/save-file-dialog", methods=["POST"])
def api_save_file_dialog():
    """
    Opens native Windows 'Save As' file dialog via DesktopAPI to allow user to pick destination
    folder and custom filename, then copies the generated XML/Excel file there.
    """
    data = request.json or {}
    filename = (data.get("filename") or "").strip()
    if not filename:
        return jsonify({"success": False, "error": "Missing filename parameter"}), 400
        
    src_path = os.path.join(PROCESSED_FOLDER, filename)
    if not os.path.exists(src_path):
        return jsonify({"success": False, "error": f"File '{filename}' not found on server"}), 404
        
    try:
        from app import DesktopAPI
        res = DesktopAPI().save_file_dialog(filename)
        return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


