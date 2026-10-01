"""
Auth guard, session helpers, context processor, error handlers.
Call register_middleware(app) from the app factory to wire everything up.
"""
import json
from flask import Flask, request, session, redirect, url_for, jsonify

VERSION_FILE = "version.json"

# --- Allowed public routes (no login required)
LOGIN_EXEMPT_PREFIXES = (
    "/login",
    "/static/",
    "/favicon.ico",
    "/auth/verify",  # optional
    "/healthz",
)


def is_exempt(path: str) -> bool:
    return any(path.startswith(p) for p in LOGIN_EXEMPT_PREFIXES)


def get_build_metadata() -> dict[str, str | None]:
    """Return build metadata with safe fallbacks."""
    metadata: dict[str, str | None] = {
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


def get_build_version():
    """Read the current build version from version.json."""
    return get_build_metadata()["build"]


def register_middleware(app: Flask) -> None:
    """Register before_request, after_request, context_processor, error handlers."""

    @app.before_request
    def global_login_required():
        if is_exempt(request.path):
            return
        if not session.get("auth"):
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for("auth.login", next=next_url))

    @app.after_request
    def add_no_cache_headers(response):
        """
        Prevent browsers from caching authenticated pages.
        This ensures Back button cannot show protected content after logout.
        """
        if session.get("auth"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    @app.context_processor
    def inject_build_version():
        """Inject build version and user project access into all templates"""
        build_info = get_build_metadata()
        return {
            "build_version": build_info["build"],
            "build_info": build_info,
            "user_projects": session.get("user_projects", []),
        }

    @app.errorhandler(404)
    def page_not_found(e):
        if not session.get("auth"):
            return redirect("/login")
        return redirect("/")
