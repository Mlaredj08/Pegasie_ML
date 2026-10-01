"""
Auth routes: /login, /logout, /api/me, /auth/verify
"""
import requests
from flask import Blueprint, request, jsonify, redirect, render_template, flash, session, url_for
from requests.auth import HTTPBasicAuth

from auth.credentials import verify_jira_credentials, normalize_jira_url
from auth.user_registry import update_user_registry

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")  # you already have this template

    # POST
    jira_url = (request.form.get("jira_url") or "").strip()
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    remember = bool(request.form.get("remember"))

    if not jira_url or not username or not password:
        flash("Please enter Jira URL, username and password.", "danger")
        return redirect(url_for("auth.login"))

    ok = verify_jira_credentials(jira_url, username, password)
    if not ok:
        flash("Invalid Jira credentials or Jira is unreachable.", "danger")
        return redirect(url_for("auth.login"))

    # --- SUCCESS ---
    session.clear()
    session.permanent = remember
    normalized_url = normalize_jira_url(jira_url)
    is_cloud = ".atlassian.net" in normalized_url.lower()
    session["auth"] = True
    session["jira_url"] = normalized_url
    session["jira_username"] = username     # For UI display
    session["jira_password"] = password     # For Jira API calls
    session["jira_type"] = "jira_cloud" if is_cloud else "jira_server"

    # Update the persistent user registry (projects, timestamp, users cache)
    try:
        user_projects = update_user_registry(normalized_url, username, password)
        session["user_projects"] = user_projects
    except Exception as e:
        print(f"[WARNING] Failed to update user registry: {e}")
        session["user_projects"] = []

    next_url = request.args.get("next")
    if next_url and next_url.startswith("/"):
        return redirect(next_url)

    return redirect("/")


@bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@bp.get("/api/me")
def api_me():
    if not session.get("auth"):
        return jsonify({"error": "Not authenticated"}), 401

    return jsonify({
        "authenticated": True,
        "jira_username": session.get("jira_username"),
        "jira_url": session.get("jira_url"),
        "jira_type": session.get("jira_type"),
        "user_projects": session.get("user_projects", [])
    })


@bp.post("/auth/verify")
def auth_verify():
    data = request.get_json(silent=True) or {}
    jira_url = (data.get("jira_url") or "").rstrip("/")
    full_username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    username = full_username.split("[", 1)[0].strip()

    if not (jira_url and username and password):
        return jsonify(ok=False, error="Missing jira_url, username, or password/token"), 400

    endpoints = [f"{jira_url}/rest/api/latest/myself"]

    try:
      for url in endpoints:
          resp = requests.get(url, auth=HTTPBasicAuth(username, password), timeout=10)
          if resp.status_code == 200:
              return jsonify(ok=True, message="User verified")

      return jsonify(ok=False, error=f"JIRA auth failed (last status {resp.status_code})"), 401
    except requests.RequestException as e:
      return jsonify(ok=False, error=str(e)), 502
