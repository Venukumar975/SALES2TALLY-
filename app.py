import os
import sys
import threading
import time
import webview
from flask import Flask, request, redirect, url_for, jsonify
from werkzeug.serving import make_server
from datetime import datetime

from config import TEMPLATE_FOLDER, STATIC_FOLDER, cleanup_temp_files
from routes.main_routes import main_bp
from routes.tally_routes import tally_bp
from routes.analysis_routes import analysis_bp
from routes.generator_routes import generator_bp
from routes.licensing_routes import licensing_bp
from services.licensing import get_current_license_status, start_license_heartbeat

def create_app():
    """Application factory for Sales & Purchase Registers Suite."""
    app = Flask(
        __name__,
        template_folder=TEMPLATE_FOLDER,
        static_folder=STATIC_FOLDER
    )
    
    # Start background license heartbeat thread
    start_license_heartbeat()
    
    # Register Modular Blueprints
    app.register_blueprint(licensing_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(tally_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(generator_bp)

    @app.before_request
    def check_license_access():
        # Allow static files and license activation endpoints without restriction
        path = request.path
        if path.startswith("/static") or path.startswith("/login") or path.startswith("/api/license") or path == "/favicon.ico":
            return None

        status = get_current_license_status()
        if not status.get("is_valid"):
            if request.is_json or path.startswith("/api/"):
                return jsonify({
                    "success": False,
                    "error": "License is inactive or expired. Please activate your license.",
                    "license_status": status.get("status")
                }), 403
            return redirect(url_for("licensing_bp.login_page"))
    
    return app

app = create_app()

def _log_app(msg: str, level: str = "INFO"):
    from config import APP_DATA_DIR
    try:
        os.makedirs(APP_DATA_DIR, exist_ok=True)
        log_path = os.path.join(APP_DATA_DIR, "app.log")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{level.upper()}] [APP_CORE] {msg}\n")
    except Exception:
        pass

def find_available_port(start_port=5005, max_attempts=20):
    import socket
    for p in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', p))
                return p
        except OSError:
            continue
    return start_port

def start_flask(port):
    """Run Flask inside background thread using Werkzeug Server."""
    try:
        _log_app(f"Werkzeug HTTP server starting on http://127.0.0.1:{port}...")
        server = make_server("127.0.0.1", port, app)
        server.serve_forever()
    except Exception as e:
        _log_app(f"Flask server error: {e}", level="ERROR")

class DesktopAPI:
    def save_file_dialog(self, filename):
        """Open native Windows Save File Dialog and copy the processed file to chosen path."""
        import shutil
        from config import PROCESSED_FOLDER
        src_path = os.path.join(PROCESSED_FOLDER, filename)
        if not os.path.exists(src_path):
            return {"success": False, "error": f"File {filename} not found"}

        try:
            default_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            if not os.path.exists(default_dir):
                default_dir = os.path.expanduser("~")

            if filename.endswith(".xml"):
                file_types = ("XML Files (*.xml)", "All files (*.*)")
            elif filename.endswith(".xlsx") or filename.endswith(".xls"):
                file_types = ("Excel Files (*.xlsx)", "All files (*.*)")
            else:
                file_types = ("All files (*.*)",)

            window = webview.windows[0] if webview.windows else None
            if window:
                dest_path = window.create_file_dialog(
                    webview.SAVE_DIALOG,
                    directory=default_dir,
                    save_filename=filename,
                    file_types=file_types
                )
                if dest_path:
                    if isinstance(dest_path, (list, tuple)):
                        dest_path = dest_path[0]
                    if dest_path:
                        shutil.copyfile(src_path, dest_path)
                        _log_app(f"Saved file to: {dest_path}")
                        return {"success": True, "saved_to": dest_path}
                return {"success": False, "cancelled": True}
            else:
                dest_path = os.path.join(default_dir, filename)
                shutil.copyfile(src_path, dest_path)
                return {"success": True, "saved_to": dest_path}
        except Exception as e:
            _log_app(f"save_file_dialog exception: {e}", level="ERROR")
            dest_path = os.path.join(os.path.expanduser("~"), "Downloads", filename)
            shutil.copyfile(src_path, dest_path)
            return {"success": True, "saved_to": dest_path}

def main():
    """Launch Flask server and native Desktop UI window."""
    from config import APP_DATA_DIR
    # Reset log file on app startup if running directly
    try:
        log_path = os.path.join(APP_DATA_DIR, "app.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("")
    except Exception:
        pass
    _log_app("app.main() invoked. Performing initial temp cleanup...")
    cleanup_temp_files()
    port_no = find_available_port(5005)
    url = f"http://127.0.0.1:{port_no}/login"
    _log_app(f"Selected port {port_no} -> URL: {url}")

    # Start Flask server in background daemon thread
    flask_thread = threading.Thread(target=start_flask, args=(port_no,), daemon=True)
    flask_thread.start()
    time.sleep(0.6)

    _log_app("Creating pywebview native window for SALES2TALLY...")
    # Launch native Desktop window via pywebview with DesktopAPI bridge
    api = DesktopAPI()
    window = webview.create_window(
        title="SALES2TALLY",
        url=url,
        width=1320,
        height=880,
        min_size=(1024, 700),
        background_color="#09090b",
        js_api=api
    )

    try:
        _log_app("Calling webview.start()...")
        webview.start()
    except Exception as e:
        _log_app(f"webview.start() encountered error: {e}", level="ERROR")
    finally:
        _log_app("Application window closed. Cleaning up temp files...")
        cleanup_temp_files()

if __name__ == "__main__":
    main()

