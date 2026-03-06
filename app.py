from __future__ import annotations

import os
from flask import Flask, Blueprint, jsonify, redirect, render_template

from b5_manual.job_state import get_job
from b5_manual.routes_manual import register_manual_routes


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")

    api = Blueprint("stage_b5_manual_api", __name__, url_prefix="/api/athena")
    register_manual_routes(api)
    app.register_blueprint(api)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/wizard")
    def wizard_alias():
        return redirect("/", code=302)

    @app.get("/api/athena/process/job/<job_id>")
    def process_job(job_id: str):
        return jsonify(get_job(job_id))

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "service": "stage-b5-manual"})

    return app


if __name__ == "__main__":
    app = create_app()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5151"))
    debug = os.environ.get("DEBUG", "1").strip().lower() in ("1", "true", "yes", "on")
    app.run(host=host, port=port, debug=debug)
