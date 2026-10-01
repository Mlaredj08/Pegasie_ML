"""
Mutable shared state used across multiple route blueprints.
"""
import copy
import os
import json

from decision_tree.question_nodes_interpreter import DecisionTreeEngine
from config.constants import DECISION_TREE_FOLDER

# --- Decision-tree session store (sid → engine) ---
SESSIONS: dict[str, DecisionTreeEngine] = {}

csv_path = "not assigned"

# --- Inference / clustering progress tracking ---
inference_progress_dict = {
    "ml": "",
    "value_count": 0,
    "done": [],
    "ml_progress": None,
    "in_progress": None,
    "elapsed_time": 0,
    "is_multi": False,
    "is_abort": False
}
inference_threads_progress_dict = copy.deepcopy(inference_progress_dict)

# clustering_progress_dict = {"total": 0, "completed": [], "in_progress": None, "elapsed_time": 0}
clustering_progress_dict = {}
iteration_progress_dict = {}

# --- Jira export progress tracking ---
jira_export_progress = {
    "status": "idle",        # idle | running | done | error | cancelled
    "total": 0,
    "fetched": 0,
    "message": "",
    "phase": "",             # issues | comments | saving
    "error": None,
    "result_filename": None,
    "result_count": 0,
    "cancelled": False,
}


# --- Users persistence for questionnaire answering ---
USERS_FILE = os.path.join(DECISION_TREE_FOLDER, "users.json")


def _load_users() -> list[dict]:
    """Load users as a list of {name, role} objects. Backward compatible with list of strings."""
    try:
        if os.path.isfile(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    users: list[dict] = []
                    for x in data:
                        if isinstance(x, dict):
                            name = str(x.get("name", "")).strip()
                            role = str(x.get("role", "")).strip()
                            if name:
                                users.append({"name": name, "role": role})
                        elif isinstance(x, (str, int)):
                            name = str(x).strip()
                            if name:
                                users.append({"name": name, "role": ""})
                    # dedupe by name, last one wins
                    dedup = {}
                    for u in users:
                        dedup[u["name"]] = u
                    return list(dedup.values())
    except Exception:
        pass
    return []


def _save_users(users: list[dict]) -> None:
    """Save users as list of {name, role} objects."""
    cleaned: list[dict] = []
    for u in users:
        if isinstance(u, dict):
            name = str(u.get("name", "")).strip()
            role = str(u.get("role", "")).strip()
            if name:
                cleaned.append({"name": name, "role": role})
        elif isinstance(u, (str, int)):
            name = str(u).strip()
            if name:
                cleaned.append({"name": name, "role": ""})
    dedup = {}
    for u in cleaned:
        dedup[u["name"]] = u
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(dedup.values()), f, ensure_ascii=False, indent=2)
