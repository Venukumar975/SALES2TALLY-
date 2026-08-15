import os
import uuid
import pandas as pd
from flask import Blueprint, request, jsonify, render_template, send_from_directory

from config import UPLOAD_FOLDER, PROCESSED_FOLDER
from utils.helpers import find_headers_and_df

main_bp = Blueprint("main_bp", __name__)

@main_bp.route("/")
def index():
    return render_template("index.html")

@main_bp.route("/upload", methods=["POST"])
def upload_file():
    if "excel_file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file = request.files["excel_file"]
    if file.filename == "":
        return jsonify({"success": False, "error": "No file selected"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".xlsx", ".xls"):
        return jsonify({"success": False, "error": "Please upload a valid Excel file (.xlsx or .xls)"}), 400

    file_id = str(uuid.uuid4())
    save_path = os.path.join(UPLOAD_FOLDER, f"{file_id}{ext}")
    file.save(save_path)

    try:
        excel_file_obj = pd.ExcelFile(save_path)
        sheets = excel_file_obj.sheet_names
        return jsonify({
            "success": True,
            "file_id": file_id,
            "sheets": sheets
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to read sheets: {str(e)}"}), 500

@main_bp.route("/get-headers", methods=["POST"])
def get_headers():
    data = request.json or {}
    file_id = data.get("file_id")
    sheet_name = data.get("sheet_name")
    header_row = data.get("header_row")

    if not file_id or not sheet_name:
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
        headers, _ = find_headers_and_df(file_path, sheet_name, header_row=header_row)
        return jsonify({
            "success": True,
            "headers": headers
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to parse headers: {str(e)}"}), 500

@main_bp.route("/download/<path:filename>", methods=["GET"])
def download_file(filename):
    return send_from_directory(PROCESSED_FOLDER, filename, as_attachment=True)
