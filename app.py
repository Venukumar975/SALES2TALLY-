import webbrowser
from threading import Timer
from flask import Flask

from config import TEMPLATE_FOLDER, STATIC_FOLDER
from routes.main_routes import main_bp
from routes.tally_routes import tally_bp
from routes.analysis_routes import analysis_bp
from routes.generator_routes import generator_bp
from routes.licensing_routes import licensing_bp
from services.licensing import get_current_license_status, start_license_heartbeat
from flask import request, redirect, url_for, jsonify

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

if __name__ == "__main__":
    port_no = 5005
    url = f"http://localhost:{port_no}"
    print(f"Starting Excel Header Mapper Flask server on {url}...")

    def open_browser():
        try:
            webbrowser.open_new(url)
        except Exception:
            pass

    Timer(1.5, open_browser).start()
    app.run(host="localhost", port=port_no, debug=False)
