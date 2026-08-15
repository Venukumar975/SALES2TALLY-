import webbrowser
from threading import Timer
from flask import Flask

from config import TEMPLATE_FOLDER, STATIC_FOLDER
from routes.main_routes import main_bp
from routes.tally_routes import tally_bp
from routes.analysis_routes import analysis_bp
from routes.generator_routes import generator_bp

def create_app():
    """Application factory for Sales & Purchase Registers Suite."""
    app = Flask(
        __name__,
        template_folder=TEMPLATE_FOLDER,
        static_folder=STATIC_FOLDER
    )
    
    # Register Modular Blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(tally_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(generator_bp)
    
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
