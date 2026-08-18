import os
from flask import Blueprint, request, jsonify

from config import UPLOAD_FOLDER
from services.tally_ledger_service import sync_ledgers_from_tally, get_cached_ledgers, get_all_cached_companies
from services.tally_stock_service import sync_stock_from_tally
from services.master_creator import create_missing_ledgers_in_tally, create_missing_stock_items_in_tally

tally_bp = Blueprint("tally_bp", __name__)

@tally_bp.route("/api/tally/sync", methods=["POST"])
def api_tally_sync_ledgers():
    data = request.json or {}
    company_name = data.get("company_name", "").strip()
    if not company_name:
        return jsonify({"success": False, "error": "Company Name is required"}), 400
    try:
        count, co_name = sync_ledgers_from_tally(company_name)
        return jsonify({
            "success": True,
            "count": count,
            "company_name": co_name
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@tally_bp.route("/api/tally/sync-stock", methods=["POST"])
def api_tally_sync_stock():
    data = request.json or {}
    company_name = data.get("company_name", "").strip()
    if not company_name:
        return jsonify({"success": False, "error": "Company Name is required"}), 400
    try:
        count, co_name = sync_stock_from_tally(company_name)
        return jsonify({
            "success": True,
            "count": count,
            "company_name": co_name
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@tally_bp.route("/api/tally/companies", methods=["GET"])
def api_tally_companies():
    try:
        companies = get_all_cached_companies()
        return jsonify({"success": True, "companies": companies})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@tally_bp.route("/api/tally/ledgers", methods=["POST"])
def get_tally_ledgers_endpoint():
    data = request.json or {}
    company_name = data.get("company_name", "").strip()
    if not company_name:
        return jsonify({"success": False, "error": "Company name is required"}), 400
    ledgers = get_cached_ledgers(company_name)
    return jsonify({"success": True, "ledgers": ledgers})

@tally_bp.route("/api/tally/create-missing-ledgers", methods=["POST"])
def api_tally_create_missing_ledgers():
    data = request.json or {}
    ledger_company = data.get("ledger_company", "").strip()
    parties = data.get("parties", [])
    if not ledger_company:
        return jsonify({"success": False, "error": "Ledger company is required"}), 400
    if not parties:
        return jsonify({"success": False, "error": "Parties list is required"}), 400
    try:
        created_count = create_missing_ledgers_in_tally(ledger_company, parties)
        return jsonify({"success": True, "created_count": created_count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@tally_bp.route("/api/tally/create-missing-items", methods=["POST"])
@tally_bp.route("/api/tally/create-missing-stock-items", methods=["POST"])
def api_tally_create_missing_items():
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name")
    mappings = data.get("mappings", {})
    header_row = data.get("header_row", 1)
    company_name = (data.get("company_name") or data.get("stock_company") or "").strip()
    under = (data.get("under") or data.get("stock_group") or "Primary").strip()
    units = (data.get("units") or data.get("detected_units") or "Nos").strip()
    supply_type = (data.get("supply_type") or "Goods").strip()
    products = data.get("products") or data.get("items") or []

    if not company_name:
        return jsonify({"success": False, "error": "Company Name is required"}), 400
    if not products:
        return jsonify({"success": False, "error": "Products list is required"}), 400

    file_path = None
    if file_id:
        for ext in ('.xlsx', '.xls'):
            p = os.path.join(UPLOAD_FOLDER, f"{file_id}{ext}")
            if os.path.exists(p):
                file_path = p
                break

    if not file_path:
        return jsonify({"success": False, "error": "Source Excel file not found. Please upload again."}), 404

    try:
        created_count, ignored_count = create_missing_stock_items_in_tally(
            file_path=file_path,
            sheet_name=sheet_name,
            mappings=mappings,
            header_row=header_row,
            company_name=company_name,
            under=under,
            units=units,
            supply_type=supply_type,
            products=products
        )
        return jsonify({
            "success": True,
            "created_count": created_count,
            "ignored_count": ignored_count
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
