import os
from flask import Blueprint, request, jsonify

from config import UPLOAD_FOLDER, PROCESSED_FOLDER
from services.xml_generator import generate_tally_vouchers_xml
from services.excel_generator import generate_formatted_excel
from services.xml_verifier import audit_generated_xml_file

generator_bp = Blueprint("generator_bp", __name__)

@generator_bp.route("/generate", methods=["POST"])
def generate():
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name")
    mappings = data.get("mappings", {})
    original_filename = data.get("original_filename", "register.xlsx")
    ledger_company = data.get("ledger_company", "").strip()
    xml_company_name = data.get("xml_company_name", "").strip()
    sales_ledger_name = data.get("sales_ledger_name", "").strip()
    sales_ledger_mappings = data.get("sales_ledger_mappings", {})
    misc_ledger_name = data.get("misc_ledger_name", "").strip()
    header_row = data.get("header_row")
    tax_ledger_mappings = data.get("tax_ledger_mappings", {})
    
    from_date = data.get("from_date")
    to_date = data.get("to_date")
    
    if not file_id or not sheet_name or not mappings:
        return jsonify({"success": False, "error": "Missing parameters for file mapping"}), 400
    if not xml_company_name:
        return jsonify({"success": False, "error": "Tally Company Name for XML Import is required"}), 400
        
    file_path = None
    for ext in ('.xlsx', '.xls'):
        p = os.path.join(UPLOAD_FOLDER, f"{file_id}{ext}")
        if os.path.exists(p):
            file_path = p
            break
            
    if not file_path:
        return jsonify({"success": False, "error": "File not found"}), 404
        
    try:
        filename, row_count = generate_tally_vouchers_xml(
            file_path=file_path,
            sheet_name=sheet_name,
            mappings=mappings,
            original_filename=original_filename,
            ledger_company=ledger_company,
            xml_company_name=xml_company_name,
            sales_ledger_name=sales_ledger_name,
            misc_ledger_name=misc_ledger_name,
            header_row=header_row,
            from_date=from_date,
            to_date=to_date,
            tax_ledger_mappings=tax_ledger_mappings,
            sales_ledger_mappings=sales_ledger_mappings
        )
        xml_path = os.path.join(PROCESSED_FOLDER, filename)
        audit_report = audit_generated_xml_file(xml_path)
        return jsonify({
            "success": True,
            "filename": filename,
            "row_count": row_count,
            "download_url": f"/download/{filename}",
            "audit_report": audit_report
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@generator_bp.route("/generate_excel", methods=["POST"])
def generate_excel():
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name")
    mappings = data.get("mappings", {})
    original_filename = data.get("original_filename", "register.xlsx")
    header_row = data.get("header_row")
    from_date = data.get("from_date")
    to_date = data.get("to_date")
    
    if not file_id or not sheet_name or not mappings:
        return jsonify({"success": False, "error": "Missing parameters for file mapping"}), 400
        
    file_path = None
    for ext in ('.xlsx', '.xls'):
        p = os.path.join(UPLOAD_FOLDER, f"{file_id}{ext}")
        if os.path.exists(p):
            file_path = p
            break
            
    if not file_path:
        return jsonify({"success": False, "error": "File not found"}), 404
        
    try:
        filename, row_count = generate_formatted_excel(
            file_path=file_path,
            sheet_name=sheet_name,
            mappings=mappings,
            original_filename=original_filename,
            header_row=header_row,
            from_date=from_date,
            to_date=to_date
        )
        return jsonify({
            "success": True,
            "filename": filename,
            "row_count": row_count
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
