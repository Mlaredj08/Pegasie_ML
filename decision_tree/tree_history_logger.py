"""
Tree History Logger - Logs all actions performed during tree execution.

Each tree has its own history log file: <tree_name>_history_log.json
Actions logged: start_session, answer_question, rewind, add_user, assign_role
"""
import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

# Folder where history logs are stored
HISTORY_LOGS_FOLDER = os.path.join(os.path.dirname(__file__), "Tree_history_logs")

# Ensure folder exists
os.makedirs(HISTORY_LOGS_FOLDER, exist_ok=True)


def _get_history_file_path(tree_name: str) -> str:
    """Get the path to the history log file for a given tree."""
    # Remove .json extension if present to avoid double extension
    base_name = tree_name.replace(".json", "")
    return os.path.join(HISTORY_LOGS_FOLDER, f"{base_name}_history_log.json")


def _load_history(tree_name: str) -> Dict[str, Any]:
    """Load existing history or create a new structure."""
    file_path = _get_history_file_path(tree_name)
    if os.path.isfile(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    # Return new history structure
    return {
        "tree_name": tree_name,
        "created_at": datetime.now().isoformat(),
        "actions": []
    }


def _save_history(tree_name: str, history: Dict[str, Any]) -> None:
    """Save history to file."""
    file_path = _get_history_file_path(tree_name)
    history["last_updated"] = datetime.now().isoformat()
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def log_action(
    tree_name: str,
    action_type: str,
    user: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log an action to the tree's history file.
    
    Args:
        tree_name: Name of the tree (e.g., "my_tree.json")
        action_type: Type of action (start_session, answer_question, rewind, add_user, assign_role)
        user: The user who performed the action
        details: Additional details about the action
    """
    history = _load_history(tree_name)
    
    action_entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action_type,
        "user": user,
        "details": details or {}
    }
    
    history["actions"].append(action_entry)
    _save_history(tree_name, history)


def log_start_session(tree_name: str, session_id: str, user: Optional[str] = None) -> None:
    """Log when a tree session is started."""
    log_action(
        tree_name=tree_name,
        action_type="start_session",
        user=user,
        details={"session_id": session_id}
    )


def log_answer(
    tree_name: str,
    session_id: str,
    node_id: str,
    answer: Any,
    answering_user: Optional[str] = None,
    user_role: Optional[str] = None
) -> None:
    """Log when a question is answered."""
    log_action(
        tree_name=tree_name,
        action_type="answer_question",
        user=answering_user,
        details={
            "session_id": session_id,
            "node_id": node_id,
            "answer": answer,
            "user_role": user_role
        }
    )


def log_rewind(
    tree_name: str,
    session_id: str,
    user: Optional[str] = None,
    answers_count: int = 0
) -> None:
    """Log when a user rewinds (clicks back)."""
    log_action(
        tree_name=tree_name,
        action_type="rewind",
        user=user,
        details={
            "session_id": session_id,
            "remaining_answers_count": answers_count
        }
    )


def log_add_user(
    tree_name: str,
    new_user_name: str,
    new_user_role: str,
    added_by: Optional[str] = None
) -> None:
    """Log when a new user is added."""
    log_action(
        tree_name=tree_name,
        action_type="add_user",
        user=added_by,
        details={
            "new_user_name": new_user_name,
            "new_user_role": new_user_role
        }
    )


def log_assign_role(
    tree_name: str,
    target_user: str,
    role: str,
    assigned_by: Optional[str] = None
) -> None:
    """Log when a role is assigned to a user."""
    log_action(
        tree_name=tree_name,
        action_type="assign_role",
        user=assigned_by,
        details={
            "target_user": target_user,
            "role": role
        }
    )
