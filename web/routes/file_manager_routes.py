"""
File manager routes: /file_manager, /download_file, /delete_file, /preview_file,
                     /delete_cached_item, /clear_all_cache, /api/clearable_items
"""
import json
import os
import shutil
from pathlib import Path

from flask import Blueprint, request, render_template, flash, redirect, send_from_directory, jsonify, session

import utils_pkg as utils
from auth.user_registry import filter_files_by_user_projects
from config.constants import BASE_DIR

bp = Blueprint("file_manager", __name__)


@bp.route("/file_manager", methods=["GET", "POST"])
def file_manager():
    if request.method == "GET":
        file_data = utils.get_current_files()
        # Filter files by user's accessible projects
        jira_url = session.get("jira_url", "")
        username = session.get("jira_username", "")
        if jira_url and username:
            for folder_key in file_data:
                file_data[folder_key] = filter_files_by_user_projects(
                    file_data[folder_key], jira_url, username
                )
        cached_files = utils.get_cached_files()
        timestamp_folders = utils.get_timestamp_root_folders()
        return render_template(
            "file_manager.html",
            file_data=file_data,
            cached_files=cached_files,
            timestamp_folders=timestamp_folders,
        )

    elif request.method == "POST":
        try:
            file = request.files.get("json_file")
            destination = request.form.get("destination")

            if not file or file.filename == "":
                flash("No file selected.", "danger")
                return redirect("/file_manager")

            filename, data = utils.validate_json_file(file)
            saved_filename, renamed = utils.save_json_file(filename, data, destination)

            if renamed:
                flash(
                    f"File '{saved_filename}' uploaded successfully (renamed due to duplicate).",
                    "warning"
                )
            else:
                flash(f"File '{saved_filename}' uploaded successfully to {destination}.", "success")

            return redirect("/file_manager")

        except ValueError as ve:
            flash(str(ve), "danger")
            return redirect("/file_manager")
        except Exception as e:
            flash(f"Upload failed: {str(e)}", "danger")
            return redirect("/file_manager")


@bp.route("/download_file/<folder>/<filename>")
def download_file(folder, filename):
    """
    Allows downloading of a specific JSON file from the selected folder.
    """
    folders = utils.get_folder_paths()
    if folder not in folders:
        flash("Invalid folder name.", "danger")
        return redirect("/file_manager")

    directory = folders[folder]
    file_path = os.path.join(directory, filename)

    if not os.path.exists(file_path):
        flash("File not found.", "danger")
        return redirect("/file_manager")

    return send_from_directory(directory, filename, as_attachment=True)

@bp.route("/delete_file/<folder>/<filename>", methods=["POST"])
def delete_file(folder, filename):
    """
    Deletes a specific file from the given folder.
    """
    folders = utils.get_folder_paths()
    if folder not in folders:
        flash("Invalid folder name.", "danger")
        return redirect("/file_manager")

    directory = folders[folder]
    file_path = os.path.join(directory, filename)

    if not os.path.exists(file_path):
        flash("File not found.", "danger")
        return redirect("/file_manager")

    try:
        os.remove(file_path)
        flash(f"File '{filename}' deleted successfully from {folder}.", "success")
    except Exception as e:
        flash(f"Error deleting file: {str(e)}", "danger")

    return redirect("/file_manager")


@bp.route("/preview_file/<folder>/<filename>")
def preview_file(folder, filename):
    """
    Returns a JSON preview (up to 100 rows) for display in the UI.
    If the file is not a JSON, returns a message indicating no preview is available.
    """
    folders = utils.get_folder_paths()
    if folder not in folders:
        return {"error": "Invalid folder name."}, 400

    directory = folders[folder]
    file_path = os.path.join(directory, filename)

    if not os.path.exists(file_path):
        return {"error": "File not found."}, 404

    # 🧩 Allow preview only for JSON files
    if not filename.lower().endswith(".json"):
        return {
            "filename": filename,
            "limited": False,
            "content": f"No preview available for this type of file: '{filename}'."
        }

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Limit preview for large arrays
        if isinstance(data, list) and len(data) > 100:
            data = data[:100]
            limited = True
        else:
            limited = False

        return {
            "filename": filename,
            "limited": limited,
            "content": data
        }

    except json.JSONDecodeError:
        return {
            "filename": filename,
            "limited": False,
            "content": f"File '{filename}' could not be parsed as JSON."
        }

    except Exception as e:
        return {"error": str(e)}, 500


# ------------------------------------------------------------------
# Cache management endpoints
# ------------------------------------------------------------------

@bp.route("/delete_cached_item/<category>/<path:filepath>", methods=["POST"])
def delete_cached_item(category, filepath):
    """
    Delete a single file from a cacheable folder, or a timestamp root folder.
    """
    cacheable = utils.get_cacheable_folder_paths()

    if category == "output_folders":
        target = os.path.join(BASE_DIR, filepath)
        if not os.path.isdir(target):
            flash("Folder not found.", "danger")
            return redirect("/file_manager")
        try:
            shutil.rmtree(target)
            flash(f"Folder '{filepath}' deleted successfully.", "success")
        except Exception as e:
            flash(f"Error deleting folder: {e}", "danger")
    elif category in cacheable:
        base = cacheable[category]
        target = os.path.join(base, filepath)
        if not os.path.exists(target):
            flash("File not found.", "danger")
            return redirect("/file_manager")
        try:
            os.remove(target)
            flash(f"File '{filepath}' deleted from {category}.", "success")
        except Exception as e:
            flash(f"Error deleting file: {e}", "danger")
    else:
        flash("Invalid category.", "danger")

    return redirect("/file_manager")


@bp.route("/api/clearable_items")
def api_clearable_items():
    """
    JSON endpoint returning every item that would be deleted by 'Clear All Cache'.
    """
    items = utils.get_all_clearable_items()
    return jsonify(items)


@bp.route("/clear_all_cache", methods=["POST"])
def clear_all_cache():
    """
    Delete all selected cached items. Expects JSON body:
    { "items": [ {"path": "...", "is_dir": true/false}, ... ] }
    """
    data = request.get_json(force=True) or {}
    items = data.get("items", [])
    deleted = 0
    errors = []

    for item in items:
        target = item.get("path", "")
        is_dir = item.get("is_dir", False)
        if not target or not os.path.exists(target):
            continue
        try:
            if is_dir:
                shutil.rmtree(target)
            else:
                os.remove(target)
            deleted += 1
        except Exception as e:
            errors.append(f"{target}: {e}")

    return jsonify({"deleted": deleted, "errors": errors})
