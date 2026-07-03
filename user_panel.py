# user_panel.py
"""User-facing SPA served at /app (built from smc-frontend/)."""
import os

from flask import Blueprint, send_from_directory  # type: ignore

user_bp = Blueprint("user", __name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__)))
APP_DIST = os.path.join(PROJECT_ROOT, "static", "app")


@user_bp.route("/app")
@user_bp.route("/app/")
@user_bp.route("/app/<path:path>")
def user_app(path=""):
    """Serve the React user SPA; fallback message if not built yet."""
    index = os.path.join(APP_DIST, "index.html")
    if not os.path.isdir(APP_DIST) or not os.path.exists(index):
        return (
            "<h1>User app not built</h1>"
            "<p>Run <code>python run.py</code> (builds automatically) or "
            "<code>npm run build</code> in <code>smc-frontend/</code>.</p>"
            "<p>Dev mode: Vite on "
            "<a href='http://127.0.0.1:5173/'>http://127.0.0.1:5173/</a></p>",
            503,
        )
    if path and os.path.isfile(os.path.join(APP_DIST, path)):
        return send_from_directory(APP_DIST, path)
    return send_from_directory(APP_DIST, "index.html")
