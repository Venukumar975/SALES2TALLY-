from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from services.licensing import (
    get_machine_hwid,
    decode_and_verify_key,
    save_license_file,
    get_current_license_status,
    start_license_heartbeat
)

licensing_bp = Blueprint("licensing_bp", __name__)

@licensing_bp.route("/login")
def login_page():
    """Render the License Registration & Login page."""
    status = get_current_license_status()
    # If already valid, redirect directly to dashboard
    if status.get("is_valid"):
        return redirect(url_for("main_bp.index"))
    return render_template("login.html", hwid=status.get("hwid"))

@licensing_bp.route("/api/license/status", methods=["GET"])
def api_license_status():
    """API endpoint to get current machine HWID and license status."""
    status = get_current_license_status()
    return jsonify(status)

@licensing_bp.route("/api/license/activate", methods=["POST"])
def api_license_activate():
    """API endpoint to activate app by decoding and validating a license key."""
    data = request.json or {}
    key_str = data.get("license_key", "").strip()

    if not key_str:
        return jsonify({"success": False, "error": "Please enter a license key."}), 400

    hwid = get_machine_hwid()
    is_valid, msg, payload, sig = decode_and_verify_key(key_str, hwid)

    if not is_valid:
        return jsonify({"success": False, "error": msg}), 400

    # Save to localappdata .lic file
    try:
        save_license_file(payload, sig)
        # Update in-memory status
        new_status = get_current_license_status()
        return jsonify({
            "success": True,
            "message": "License activated successfully!",
            "status": new_status
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to save license file: {e}"}), 500

@licensing_bp.route("/api/license/verify-login", methods=["POST"])
def api_verify_login():
    """Verify existing .lic file and proceed if valid."""
    status = get_current_license_status()
    if status.get("is_valid"):
        return jsonify({"success": True, "redirect": url_for("main_bp.index")})
    else:
        return jsonify({"success": False, "error": status.get("message", "No valid license found.")}), 400
