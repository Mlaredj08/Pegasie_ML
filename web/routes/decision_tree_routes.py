"""
Decision-tree routes:
  /questionnarie_decision_tree, /tree_editor, /trees, /get_tree,
  /dt/* endpoints, /trees/upload_csv, /trees/<name> DELETE
"""
import json
import os
import uuid
from copy import deepcopy
from datetime import datetime

from flask import Blueprint, request, jsonify, render_template, session

import utils_pkg as utils
from integrations.openai_client import ask_chatgpt
from decision_tree.question_nodes_interpreter import DecisionTreeEngine, _render_tmpl
from decision_tree.tree_history_logger import (
    log_start_session, log_answer, log_rewind, log_add_user
)
from config.constants import (
    TREES_FOLDER, DECISION_TREE_FOLDER,
    DQT_YES_NO, DQT_TEXT, DQT_LIST, DQT_SINGLE_SELECT, DQT_MULTI_SELECT, CCS_TYPE, CCS_PROMPT
)
from web.shared_state import SESSIONS, _load_users, _save_users

bp = Blueprint("decision_tree", __name__)


@bp.route("/questionnarie_decision_tree")
def questionnarie_decision_tree():
    return render_template("questionnarie_profile.html")


@bp.route("/tree_editor")
def tree_editor():
    return render_template("tree_editor.html")


@bp.route("/trees")
def trees():
    file_names = utils.get_file_names_by_extension(TREES_FOLDER, ".json")
    return jsonify(file_names)


@bp.route("/get_tree")
def get_tree():
    tree_data = ""
    file_name_selected = request.args.get("name")
    tree_path = f"{TREES_FOLDER}/{file_name_selected}"

    with open(tree_path, "r", encoding="utf-8") as f:
        tree_data = json.load(f)
    return tree_data


@bp.post("/dt/start")
def dt_start():
    data = request.get_json(silent=True) or {}
    tree_name = data.get("tree_name")
    if not tree_name:
        return jsonify({"error": "tree_name is required"}), 400
    path = os.path.join(TREES_FOLDER, tree_name)
    if not os.path.isfile(path):
        return jsonify({"error": f"Tree {tree_name} not found"}), 404

    with open(path, "r", encoding="utf-8") as f:
        tree = json.load(f)

    engine = DecisionTreeEngine(tree)
    sid = str(uuid.uuid4())
    SESSIONS[sid] = engine
    # Store tree_name in engine for history logging
    engine.tree_name = tree_name
    payload = engine.start()
    
    # Log session start
    current_user = session.get("jira_username")
    log_start_session(tree_name, sid, user=current_user)
    
    return jsonify({"session_id": sid, **payload})


# --- Users management for questionnaire answering ---
@bp.get("/dt/users")
def dt_get_users():
    try:
        return jsonify({"users": _load_users()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.post("/dt/users")
def dt_add_user():
    data = request.get_json(silent=True) or {}
    # Accept either separate fields or a single combined string "Name, Role"
    raw_name = (data.get("name") or "").strip()
    role = (data.get("role") or "").strip()
    tree_name = (data.get("tree_name") or "").strip()  # Optional for history logging
    name = raw_name
    if raw_name and not role and "," in raw_name:
        parts = [p.strip() for p in raw_name.split(",", 1)]
        name = parts[0]
        role = parts[1] if len(parts) > 1 else ""
    if not name or not role:
        return jsonify({"error": "Both name and role are required (format: 'Name, Role')."}), 400

    users = _load_users()
    # update if exists, else append
    found = False
    for u in users:
        if u.get("name") == name:
            u["role"] = role
            found = True
            break
    if not found:
        users.append({"name": name, "role": role})
    try:
        _save_users(users)
    except Exception as e:
        return jsonify({"error": f"Failed to save users: {e}"}), 500
    
    # Log add_user action if tree_name is provided
    if tree_name:
        current_user = session.get("jira_username")
        log_add_user(
            tree_name=tree_name,
            new_user_name=name,
            new_user_role=role,
            added_by=current_user
        )
    
    return jsonify({"ok": True, "users": users})


@bp.post('/trees/upload_csv')
def upload_csv():
    if "file" not in request.files:
        return jsonify({"error": "CSV file is required"}), 400
    f = request.files["file"]
    file_name_selected = (request.form.get("file_name") or "").strip()
    if not file_name_selected:
        return jsonify({"error": "file_name is required (e.g., my_tree.json)"}), 400
    if not file_name_selected.lower().endswith(".json"):
        file_name_selected += ".json"

    start_id = (request.form.get("start_id") or "").strip() or None
    csv_text = f.read().decode("utf-8", errors="replace")

    try:
        tree = utils.build_tree_from_csv_text(csv_text, start_id=start_id)
    except Exception as e:
        return jsonify({"error": f"CSV parse failed: {e}"}), 400
    tree_path = f"{TREES_FOLDER}/{file_name_selected}"
    try:
        with open(tree_path, "w", encoding="utf-8") as out:
            json.dump(tree, out, ensure_ascii=False, indent=2)
    except Exception as e:
        return jsonify({"error": f"Failed to save JSON: {e}"}), 500

    return jsonify({"ok": True, "saved_name": file_name_selected, "tree": tree})

@bp.post("/dt/rewind")
def dt_rewind():
    """Reset the engine and replay the provided answers in order."""
    data = request.get_json(silent=True) or {}
    sid = data.get("session_id")
    if not sid or sid not in SESSIONS:
        return jsonify({"error":"invalid session_id"}), 400
    engine_old = SESSIONS[sid]
    tree = engine_old.tree
    tree_name = getattr(engine_old, 'tree_name', None)
    engine = DecisionTreeEngine(tree)     # fresh engine
    # Preserve tree_name for history logging
    if tree_name:
        engine.tree_name = tree_name
    # Preserve per-question metadata across rewind so earlier answers keep user/role/timestamp
    try:
        old_qmeta = engine_old.profile.get("question_meta") or {}
        if isinstance(old_qmeta, dict):
            engine.profile["question_meta"] = deepcopy(old_qmeta)
    except Exception:
        pass
    SESSIONS[sid] = engine
    _ = engine.start()                    # position at first node
    incoming = data.get("answers") or []  # [{id, answer}, ...]
    for item in incoming:
        engine.answer(item.get("id"), item.get("answer"))
    payload = engine._render_current()    # render current node after replay
    
    # Log the rewind action
    if tree_name:
        current_user = session.get("jira_username")
        log_rewind(
            tree_name=tree_name,
            session_id=sid,
            user=current_user,
            answers_count=len(incoming)
        )
    
    return jsonify({"session_id": sid, **payload})

@bp.post("/dt/answer")
def dt_answer():
    data = request.get_json(silent=True) or {}
    sid = data.get("session_id")
    node_id = data.get("node_id")
    answer = data.get("answer")
    answering_user = (data.get("answering_user") or "").strip()
    user_role = (data.get("user_role") or "").strip()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not sid or sid not in SESSIONS:
        return jsonify({"error": "invalid session_id"}), 400

    engine = SESSIONS[sid]
    # Record per-question metadata in profile (kept in-memory only; stripped on save)
    try:
        qmeta = engine.profile.setdefault("question_meta", {})
        if node_id:
            # Attempt to resolve role from users file if not provided
            if not user_role and answering_user:
                for u in _load_users():
                    if u.get("name") == answering_user:
                        user_role = u.get("role", "")
                        break
            qmeta[node_id] = {
                "answering_user": answering_user or None,
                "user_role": user_role or None,
                "timestamp": (timestamp or datetime.now().isoformat())
            }
    except Exception:
        pass

    res = engine.answer(node_id, answer)
    
    # Log the answer action
    tree_name = getattr(engine, 'tree_name', None)
    if tree_name and node_id:
        log_answer(
            tree_name=tree_name,
            session_id=sid,
            node_id=node_id,
            answer=answer,
            answering_user=answering_user or None,
            user_role=user_role or None
        )
    
    # If loop is active, engine may need to auto-advance when sub-loop finishes; it already handles it.
    return jsonify(res | {"session_id": sid})

@bp.get("/dt/profile/<sid>")
def dt_profile(sid: str):
    engine = SESSIONS.get(sid)
    if not engine:
        return jsonify({"error": "invalid session_id"}), 404
    qmeta = engine.profile.get("question_meta") or {}
    nodes = (engine.tree or {}).get("nodes", {}) or {}
    answers_with_meta = {}
    for k, v in (engine.answers or {}).items():
        m = qmeta.get(k) or {}
        node = nodes.get(k) or {}
        raw_prompt = node.get(CCS_PROMPT, "")
        resolved_prompt = _render_tmpl(raw_prompt, v, engine.answers) if raw_prompt else ""
        answers_with_meta[k] = {
            "value": v,
            "answering_user": m.get("answering_user"),
            "user_role": m.get("user_role"),
            "timestamp": m.get("timestamp"),
            "prompt": resolved_prompt,
        }
    # Compute skipped questions 
    try:
        answered_ids = set((engine.answers or {}).keys())
        real_types = {DQT_YES_NO, DQT_TEXT, DQT_LIST, DQT_SINGLE_SELECT, DQT_MULTI_SELECT}
        skipped = [nid for nid, node in nodes.items() if isinstance(node, dict) and node.get(CCS_TYPE) in real_types and nid not in answered_ids]
    except Exception:
        skipped = []
    return jsonify({"profile": engine.profile, "answers": answers_with_meta, "skipped_questions": skipped})

@bp.get("/dt/save_profile/<sid>")
def dt_save_profile(sid: str):

    engine = SESSIONS.get(sid)
    if not engine:
        return jsonify({"error": "invalid session_id"}), 404
    file_name_selected = f"{str(engine.profile.get('created_at')).replace('.','-').replace(':','-')}_profile.json"
    # Build answers with per-question metadata embedded
    qmeta = engine.profile.get("question_meta") or {}
    nodes = (engine.tree or {}).get("nodes", {}) or {}
    answers_with_meta = {}
    for k, v in (engine.answers or {}).items():
        m = qmeta.get(k) or {}
        node = nodes.get(k) or {}
        raw_prompt = node.get(CCS_PROMPT, "")
        resolved_prompt = _render_tmpl(raw_prompt, v, engine.answers) if raw_prompt else ""
        answers_with_meta[k] = {
            "value": v,
            "answering_user": m.get("answering_user"),
            "user_role": m.get("user_role"),
            "timestamp": m.get("timestamp"),
            "prompt": resolved_prompt,
        }
    # Strip question_meta from saved profile
    try:
        profile_out = dict(engine.profile)
        if "question_meta" in profile_out:
            profile_out.pop("question_meta", None)
    except Exception:
        profile_out = engine.profile
    # Add current session username into profile
    try:
        profile_out["jira_username"] = session.get("jira_username")
    except Exception:
        pass
    # Compute skipped questions (real questions only)
    try:
        nodes = (engine.tree or {}).get("nodes", {}) or {}
        answered_ids = set((engine.answers or {}).keys())
        real_types = {DQT_YES_NO, DQT_TEXT, DQT_LIST, DQT_SINGLE_SELECT, DQT_MULTI_SELECT}
        skipped = [nid for nid, node in nodes.items() if isinstance(node, dict) and node.get(CCS_TYPE) in real_types and nid not in answered_ids]
    except Exception:
        skipped = []
    json_to_save = {"profile": profile_out, "answers": answers_with_meta, "skipped_questions": skipped}
    saving_file = f"{DECISION_TREE_FOLDER}/{file_name_selected}"
    try:
        with open(saving_file, "w", encoding="utf-8") as out:
            json.dump(json_to_save, out, ensure_ascii=False, indent=2)
    except Exception as e:
        return jsonify({"error": f"Failed to save JSON: {e}"}), 500
    return jsonify({"OK": "Profile saved"}), 200


@bp.delete('/trees/<name>')
def delete_tree(name):
    try:
        path = os.path.join(f"{TREES_FOLDER}/{name}")
        if not os.path.isfile(path):
            return jsonify({"error": "Tree not found"}), 404
        os.remove(path)
        return jsonify({"ok": True, "deleted": name})
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Delete failed: {e}"}), 500


@bp.post("/dt/suggest_trees/<sid>")
def dt_suggest_trees(sid: str):
    engine = SESSIONS.get(sid)
    if not engine:
        return jsonify({"error": "invalid session_id"}), 404

    profile = engine.profile
    answers = engine.answers

    prompt = utils._build_suggestion_prompt(profile, answers)
    system_prompt = "You return only JSON. No prose."
    ai_resp = ask_chatgpt(prompt, system_prompt)

    # if AI responded properly
    return jsonify(ai_resp), 200

@bp.post("/dt/save_suggested_tree")
def dt_save_suggested_tree():
    data = request.get_json(silent=True) or {}
    file_name = (data.get("file_name") or "").strip()
    tree = data.get("tree")

    if not file_name:
        return jsonify({"error": "file_name is required"}), 400
    if not isinstance(tree, dict):
        return jsonify({"error": "tree must be a JSON object"}), 400

    if not file_name.lower().endswith(".json"):
        file_name += ".json"

    save_path = os.path.join(TREES_FOLDER, file_name)
    try:
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(tree, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return jsonify({"error": f"Failed to save file: {e}"}), 500

    return jsonify({"ok": True, "saved": file_name}), 200
