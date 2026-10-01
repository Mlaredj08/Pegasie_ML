# utils_pkg/file_utils.py
"""File system utilities: folder paths, file listing, validation, saving."""
import csv
import json
import os
import re
from pathlib import Path

from werkzeug.utils import secure_filename

from analysis.data_pre_analysis import get_saved_target_fields_matrix_per_project
from config import FIELD_COMPLETION_FOLDER
from config.constants import (
    DATABASES_FOLDER, DEPENDENCY_MODEL_FOLDER, PREDICTIONS_FOLDER,
    ITERATION_FOLDER, QUESTIONNAIRES_FOLDER, UPDATED_DATABASE_FOLDER,
    DATABASES_SETTINGS_FOLDER, DECISION_TREE_FOLDER, BASE_DIR
)
from config.logger import Logger


def extract_project_key_from_filename(path_or_filename: str) -> str:
    # Remove quotes and normalize path
    cleaned = path_or_filename.strip("'\"")

    # Get only the filename (handles cases with or without folder)
    filename = os.path.basename(cleaned)

    # Remove extension if present
    name, _ = os.path.splitext(filename)

    # Extract the project key (part before first '_')
    parts = name.split("_", 1)
    if len(parts) != 2:
        raise ValueError("Expected format: PROJECTKEY_TIMESTAMP.json")

    return parts[0]


def get_file_names_by_extension(folder_path, extension):
    file_names = []
    try:
        for filename in os.listdir(folder_path):
            if filename.endswith(extension) and os.path.isfile(os.path.join(folder_path, filename)):
                file_names.append(filename)
    except FileNotFoundError:
        print(f"Error: Folder '{folder_path}' not found.")
        return -1
    return file_names


def extract_filename(path: str, include_extension: bool = False) -> str:
    # Remove any surrounding quotes
    cleaned = path.strip("'\"")

    # Get just the filename (e.g., J03X_20250807_112419.json)
    filename = os.path.basename(cleaned)

    if include_extension:
        return filename
    else:
        name, _ = os.path.splitext(filename)
        return name


def get_folder_paths():
    """
    Returns a dictionary with the base paths for all JFIP folders.
    """
    return {
        "databases": DATABASES_FOLDER,
        "dependency_model": DEPENDENCY_MODEL_FOLDER,
        "field_completion": FIELD_COMPLETION_FOLDER
    }


# ---------------------------------------------------------------------------
# Cache-aware helpers
# ---------------------------------------------------------------------------

# Folders that hold generated/cached content and can be cleared
CACHEABLE_FOLDERS = {
    "databases":         DATABASES_FOLDER,
    "dependency_model":  DEPENDENCY_MODEL_FOLDER,
    "predictions":       PREDICTIONS_FOLDER,
    "ml_models":         os.path.join(BASE_DIR, "ml_models"),
    "iterations":        ITERATION_FOLDER,
    "updated_databases": UPDATED_DATABASE_FOLDER,
    "database_settings": DATABASES_SETTINGS_FOLDER,
    "questionnaires":    QUESTIONNAIRES_FOLDER,
    "tree_history_logs": os.path.join(DECISION_TREE_FOLDER, "Tree_history_logs"),
}

# Regex that matches PROJECT_YYYYMMDD_HHMMSS style folder/file names at root
_TIMESTAMP_DIR_RE = re.compile(r"^[A-Za-z0-9]+_\d{8}_\d{6}$")


def get_cacheable_folder_paths():
    """Return the dict of logical-name -> absolute-path for cacheable folders."""
    return dict(CACHEABLE_FOLDERS)


def _list_entries(folder_path, include_dirs=False):
    """List files (and optionally directories) inside *folder_path*, recursively."""
    items = []
    if not os.path.isdir(folder_path):
        return items
    for root, dirs, files in os.walk(folder_path):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), folder_path)
            items.append(rel)
        if include_dirs:
            for d in dirs:
                rel = os.path.relpath(os.path.join(root, d), folder_path)
                items.append(rel + "/")
    return items


# Folders that already have dedicated tabs with upload/download in the UI
_CORE_FOLDERS = {"databases", "dependency_model"}


def get_cached_files():
    """
    Return a dict  { logical_name: [relative_file_paths] }
    for every cacheable folder that contains at least one file.
    Excludes core folders (databases, dependency_model) which have their own tabs.
    """
    result = {}
    for name, path in CACHEABLE_FOLDERS.items():
        if name in _CORE_FOLDERS:
            continue
        files = _list_entries(path)
        if files:
            result[name] = sorted(files)
    return result


def get_timestamp_root_folders():
    """
    Return a list of folder names at the project root that look like
    generated output directories (PROJECT_YYYYMMDD_HHMMSS).
    """
    folders = []
    for entry in os.listdir(BASE_DIR):
        full = os.path.join(BASE_DIR, entry)
        if os.path.isdir(full) and _TIMESTAMP_DIR_RE.match(entry):
            folders.append(entry)
    return sorted(folders)


def get_all_clearable_items():
    """
    Build a flat list of dicts suitable for the 'Clear All Cache' modal.
    Each dict: {"category", "label", "path", "is_dir", "size"}.
    """
    items = []

    # 1. Cacheable folders (exclude core folders — user data, not generated cache)
    for name, base in CACHEABLE_FOLDERS.items():
        if name in _CORE_FOLDERS:
            continue
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, BASE_DIR)
                items.append({
                    "category": name,
                    "label": rel.replace("\\", "/"),
                    "path": full,
                    "is_dir": False,
                    "size": os.path.getsize(full),
                })

    # 2. Timestamp root folders
    for folder_name in get_timestamp_root_folders():
        full = os.path.join(BASE_DIR, folder_name)
        total_size = sum(
            os.path.getsize(os.path.join(r, f))
            for r, _, fs in os.walk(full) for f in fs
        )
        items.append({
            "category": "output_folders",
            "label": folder_name + "/",
            "path": full,
            "is_dir": True,
            "size": total_size,
        })

    return items


def get_current_files():
    """
    Returns a dictionary listing all files (ignores folders)
    in each JFIP-related folder.
    """
    def list_files(folder_path):
        if not os.path.isdir(folder_path):
            return []
        return [
            f for f in os.listdir(folder_path)
            if os.path.isfile(os.path.join(folder_path, f))
        ]

    return {
        "databases": list_files(DATABASES_FOLDER),
        "dependency_model": list_files(DEPENDENCY_MODEL_FOLDER),
        "field_completion": list_files(FIELD_COMPLETION_FOLDER)
    }


def validate_json_file(file):
    """
    Validates if the uploaded file is a proper JSON file.
    Returns the parsed data if valid, otherwise raises ValueError.
    """
    filename = secure_filename(file.filename)

    if not filename.lower().endswith(".json"):
        raise ValueError("Invalid file type. Only JSON files are allowed.")

    try:
        data = json.load(file)
    except json.JSONDecodeError:
        raise ValueError("Uploaded file is not a valid JSON.")

    return filename, data


def save_json_file(filename, data, destination_key):
    """
    Saves the uploaded JSON file. If a file with the same name already exists,
    automatically appends '_copy_1', '_copy_2', etc., to avoid overwriting.
    Returns the final filename and whether it was renamed.
    """
    folders = get_folder_paths()
    if destination_key not in folders:
        raise ValueError("Invalid destination folder.")

    save_dir = folders[destination_key]
    name, ext = os.path.splitext(filename)

    counter = 1
    new_filename = filename
    renamed = False
    while os.path.exists(os.path.join(save_dir, new_filename)):
        new_filename = f"{name}_copy_{counter}{ext}"
        counter += 1
        renamed = True

    save_path = os.path.join(save_dir, new_filename)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return new_filename, renamed
