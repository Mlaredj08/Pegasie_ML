# config/app_config.py
"""
Application-level configuration: Flask settings, folder initialization,
session constants, and login-exempt routes.
"""
import os
import json
from config.constants import (
    DEPENDENCY_MODEL_FOLDER, QUESTIONNAIRES_FOLDER, UPDATED_DATABASE_FOLDER,
    ITERATION_FOLDER, PROMPTS_FOLDER, DECISION_TREE_FOLDER
)

VERSION_FILE = "version.json"

# --- Users persistence for questionnaire answering ---
USERS_FILE = os.path.join(DECISION_TREE_FOLDER, "users.json")

# --- Allowed public routes (no login required)
LOGIN_EXEMPT_PREFIXES = (
    "/login",
    "/static/",
    "/favicon.ico",
    "/auth/verify",
    "/healthz",
)


class AppConfig:
    """Centralized application configuration."""

    SECRET_KEY = os.getenv("DiErxDfZl6Sj22oO3ktfxSn", os.urandom(24))
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB

    @staticmethod
    def ensure_folders():
        """Create required application folders if they don't exist."""
        for folder in (
            DEPENDENCY_MODEL_FOLDER,
            QUESTIONNAIRES_FOLDER,
            UPDATED_DATABASE_FOLDER,
            ITERATION_FOLDER,
            PROMPTS_FOLDER,
        ):
            os.makedirs(folder, exist_ok=True)

    @staticmethod
    def get_build_metadata() -> dict:
        """Return build metadata with safe fallbacks."""
        metadata = {
            "build": "dev",
            "last_commit": "unknown",
            "last_updated": None,
        }
        try:
            with open(VERSION_FILE) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return metadata

        metadata["build"] = str(data.get("build") or metadata["build"])
        metadata["last_commit"] = data.get("last_commit") or metadata["last_commit"]

        raw_last_updated = data.get("last_updated")
        if raw_last_updated is not None:
            metadata["last_updated"] = str(raw_last_updated)

        return metadata

    @staticmethod
    def get_build_version() -> str:
        """Read the current build version from version.json."""
        return AppConfig.get_build_metadata()["build"]
