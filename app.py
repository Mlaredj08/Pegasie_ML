import os
from flask import Flask
# -- testing pipeline integration
from config.constants import (
    DEPENDENCY_MODEL_FOLDER, QUESTIONNAIRES_FOLDER, UPDATED_DATABASE_FOLDER,
    ITERATION_FOLDER, PROMPTS_FOLDER
)
from config.logger import Logger
from web.middleware import register_middleware
from web.routes import register_blueprints

app = Flask(__name__)
app.secret_key = os.getenv("DiErxDfZl6Sj22oO3ktfxSn", os.urandom(24))
# === Limit upload size (20 MB) ===
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
app.config['JSON_SORT_KEYS'] = False
app.json.sort_keys = False

# --- Ensure required directories exist ---
os.makedirs(DEPENDENCY_MODEL_FOLDER, exist_ok=True)
os.makedirs(QUESTIONNAIRES_FOLDER, exist_ok=True)
os.makedirs(UPDATED_DATABASE_FOLDER, exist_ok=True)
os.makedirs(ITERATION_FOLDER, exist_ok=True)
os.makedirs(PROMPTS_FOLDER, exist_ok=True)

# --- Wire up middleware (auth guard, no-cache headers, context processor, 404) ---
register_middleware(app)

# --- Register all route blueprints ---
register_blueprints(app)


if __name__ == "__main__":
    Logger.print_levels = ["WARNING", "ERROR", "INFO"]
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
