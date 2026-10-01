
#!/usr/bin/env python3
"""
Decision Tree Engine (backend-driven navigation, OO per node type)
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from config.constants import CCS_OPTIONS_FROM_ANSWER_OF,CCS_OPTIONS,CCS_SPLIT,CCS_USE_ANSWER_FROM,CCS_EFFECTS\
    ,CCS_PROMPT,CCS_TYPE,CCS_ID,CCS_NEXT,CCS_SOURCE,CCS_AFTER,CCS_ITEM_VAR\
    ,DQT_YES_NO,DQT_TEXT,DQT_LIST,DQT_SINGLE_SELECT,DQT_MULTI_SELECT,DQT_BRANCH,DQT_FOR_EACH

def _deep_set(container: dict, path: str, value: Any) -> None:
    parts = path.split('.')
    cur = container
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value

def _deep_get_create_list(container: dict, path: str) -> list:
    parts = path.split('.')
    cur = container
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    if parts[-1] not in cur or not isinstance(cur[parts[-1]], list):
        cur[parts[-1]] = []
    return cur[parts[-1]]

def _deep_get_create_map(container: dict, path: str) -> dict:
    parts = path.split('.')
    cur = container
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    if parts[-1] not in cur or not isinstance(cur[parts[-1]], dict):
        cur[parts[-1]] = {}
    return cur[parts[-1]]

def _render_tmpl(value: Any, node_answer: Any, all_answers: dict) -> Any:
    """Very small template: {{answer}} and {{answers.node}} (|csv for lists)"""
    if isinstance(value, str):
        out = value
        if "{{answer}}" in out:
            rep = node_answer
            if isinstance(rep, list):
                rep = ", ".join(map(str, rep))
            out = out.replace("{{answer}}", "" if rep is None else str(rep))
        def repl(m):
            key = m.group(1); filt = m.group(2)
            rep = all_answers.get(key)
            if rep is None: return ""
            if filt and filt.lower() == "|csv" and isinstance(rep, list):
                return ", ".join(map(str, rep))
            if isinstance(rep, list):
                return ", ".join(map(str, rep))
            return str(rep)
        out = re.sub(r"\{\{\s*answers\.([a-zA-Z0-9_\-\.]+)(\|csv)?\s*\}\}", repl, out)
        return out
    if isinstance(value, list):
        return [_render_tmpl(v, node_answer, all_answers) for v in value]
    if isinstance(value, dict):
        return {k: _render_tmpl(v, node_answer, all_answers) for k, v in value.items()}
    return value

def _apply_effect(profile: dict, effect: dict, node_answer: Any, all_answers: dict) -> None:
    op = effect.get("op"); path = effect.get("path")
    if not op or not path: return

    # existing logic to pick value
    value = node_answer if effect.get("from_answer") else effect.get("value")

    # 🔧 render templates in the value (as before)
    value = _render_tmpl(value, node_answer, all_answers)

    if op == "set":
        _deep_set(profile, path, value)

    elif op == "append":
        _deep_get_create_list(profile, path).append(value)

    elif op == "extend_set":
        lst = _deep_get_create_list(profile, path)
        vals = value if isinstance(value, list) else [value]
        for v in vals:
            if v not in lst: lst.append(v)

    elif op == "merge_map":
        mp = _deep_get_create_map(profile, path)

        if isinstance(value, dict):
            rendered = {
                _render_tmpl(k, node_answer, all_answers): _render_tmpl(v, node_answer, all_answers)
                for k, v in value.items()
            }
            mp.update(rendered)
        else:
            raise TypeError("merge_map expects dict value")

    else:
        raise ValueError(f"Unknown op: {op}")


def _check_condition(answer: Any, cond: dict) -> bool:
    if cond is None: return False
    if "equals" in cond: return answer == cond["equals"]
    if "in" in cond: return answer in cond["in"]
    if "contains_any" in cond:
        if not isinstance(answer, list): return False
        vals = set(cond["contains_any"]); return any(x in vals for x in answer)
    if "contains_all" in cond:
        if not isinstance(answer, list): return False
        vals = set(cond["contains_all"]); return all(x in answer for x in vals)
    if cond.get("is_true"): return bool(answer) is True
    if cond.get("is_false"): return bool(answer) is False
    if cond.get("non_empty"):
        if isinstance(answer, (list, str)): return len(answer) > 0
        return bool(answer)
    return False

def _resolve_next(node: dict, answer: Any) -> Optional[str]:
    nxt = node.get("next")
    if nxt is None: return None
    if isinstance(nxt, str): return nxt
    if isinstance(nxt, list):
        default_target = None
        for rule in nxt:
            if rule.get("default"): default_target = rule.get("goto"); continue
            if _check_condition(answer, rule.get("when", {})): return rule.get("goto")
        return default_target
    return None

def _derive_options(node: dict, all_answers: dict) -> List[str]:
    opts = node.get(CCS_OPTIONS) or []
    if opts: return [_render_tmpl(o, None, all_answers) for o in opts]
    src = node.get(CCS_OPTIONS_FROM_ANSWER_OF)
    if not src: return []
    raw = all_answers.get(src)
    if isinstance(raw, str):
        delim = node.get(CCS_SPLIT, ",")
        return [x.strip() for x in raw.split(delim) if x.strip()]
    if isinstance(raw, list): return raw
    return []

# ------------------------- OO Questions -------------------------

@dataclass
class QuestionBase:
    node: Dict[str, Any]
    answers: Dict[str, Any]
    profile: Dict[str, Any]
    ctx: Dict[str, Any]
    loop_state: Dict[str, Any]

    def render_payload(self) -> Dict[str, Any]:
        """What UI needs to render the question; prompt with templates resolved and dynamic options included."""
        prompt = _render_tmpl(self.node.get(CCS_PROMPT, self.node.get("id", "Question")), None, self.answers)
        payload = {
            "id": self.node.get("id"),
            CCS_TYPE: self.node.get(CCS_TYPE),
            CCS_PROMPT: prompt,
        }
        # options for selects
        if self.node.get(CCS_TYPE) in (DQT_SINGLE_SELECT, DQT_MULTI_SELECT):
            payload[CCS_OPTIONS] = _derive_options(self.node, self.answers)
        return payload

    def apply_effects(self, answer: Any) -> None:
        for eff in self.node.get(CCS_EFFECTS, []):
            _apply_effect(self.profile, eff, answer, self.answers)

    def next_id(self, answer: Any) -> Optional[str]:
        return _resolve_next(self.node, answer)

class YesNoQuestion(QuestionBase): pass
class TextQuestion(QuestionBase): pass
class ListQuestion(QuestionBase): pass
class SingleSelectQuestion(QuestionBase): pass
class MultiSelectQuestion(QuestionBase): pass

class BranchNode(QuestionBase):
    def render_payload(self) -> Dict[str, Any]:
        # branch nodes are invisible to UI: engine immediately jumps
        return {CCS_ID: self.node.get(CCS_ID), CCS_TYPE: DQT_BRANCH}

    def next_id(self, answer: Any) -> Optional[str]:
        prev_id = self.loop_state.get("__last_node_id__")
        branch_answer = self.answers.get(prev_id) if prev_id else None
        src = self.node.get(CCS_USE_ANSWER_FROM)
        if src is not None:
            branch_answer = self.answers.get(src, branch_answer)
        return _resolve_next(self.node, branch_answer)

class ForEachNode(QuestionBase):
    """Iterates sub-flow for each item from a source answer (string -> split or list)."""
    def render_payload(self) -> Dict[str, Any]:
        # invisible control node
        return {CCS_ID: self.node.get(CCS_ID), CCS_TYPE: DQT_FOR_EACH}

    def advance(self) -> Optional[str]:
        node_id = self.node.get(CCS_ID)
        src = self.node.get(CCS_SOURCE)

        # 1) Compute current items from the source answer (string -> split or list)
        items: List[str] = []
        if src and src in self.answers:
            raw = self.answers[src]
            if isinstance(raw, str):
                delim = self.node.get(CCS_SPLIT, ",")
                items = [s.strip() for s in raw.split(delim) if s.strip()]
            elif isinstance(raw, list):
                items = list(raw)

        # 2) Get/create loop state; add a small "phase" flag
        st = self.loop_state.setdefault(node_id, {"idx": 0, "items": items, "phase": "ready"})
        # Refresh the snapshot of items without forcibly resetting idx
        st["items"] = items

        # If we re-enter the controller after the child ran, bump index now
        if st.get("phase") == "child_running":
            st["idx"] += 1
            st["phase"] = "ready"

        idx = st["idx"]

        # 3) If finished, clean and go to "after"
        if idx >= len(items):
            self.loop_state.pop(node_id, None)
            return self.node.get(CCS_AFTER)

        # 4) Expose current item to templates and ctx, then emit child start
        var = self.node.get(CCS_ITEM_VAR, "item")
        cur_val = items[idx]
        self.ctx[var] = cur_val
        self.answers[f"__{node_id}.current"] = cur_val

        # Mark that the child is running; on next re-entry we'll bump idx
        st["phase"] = "child_running"

        return self.node.get(CCS_NEXT)


# Node factory
def make_question(node: dict, answers: dict, profile: dict, ctx: dict, loop_state: dict) -> QuestionBase:
    t = node.get(CCS_TYPE)
    if t == DQT_YES_NO: return YesNoQuestion(node, answers, profile, ctx, loop_state)
    if t == DQT_TEXT: return TextQuestion(node, answers, profile, ctx, loop_state)
    if t == DQT_LIST: return ListQuestion(node, answers, profile, ctx, loop_state)
    if t == DQT_SINGLE_SELECT: return SingleSelectQuestion(node, answers, profile, ctx, loop_state)
    if t == DQT_MULTI_SELECT: return MultiSelectQuestion(node, answers, profile, ctx, loop_state)
    if t == DQT_BRANCH: return BranchNode(node, answers, profile, ctx, loop_state)
    if t == DQT_FOR_EACH: return ForEachNode(node, answers, profile, ctx, loop_state)
    # passthrough for unknown types
    return QuestionBase(node, answers, profile, ctx, loop_state)

# ------------------------- Engine -------------------------

class DecisionTreeEngine:
    def __init__(self, tree: Dict[str, Any]):
        self.tree = tree
        self.nodes = tree.get("nodes", {})
        self.current_id: Optional[str] = tree.get("start")
        self.answers: Dict[str, Any] = {}
        self.ctx: Dict[str, Any] = {}
        self.loop_state: Dict[str, Any] = {}
        self.profile: Dict[str, Any] = (tree.get("profile_seed") or {}).copy()
        if not isinstance(self.profile, dict): self.profile = {}
        self.profile.setdefault("created_at", datetime.utcnow().isoformat() + "Z")

    # ------ public API ------

    def start(self) -> Dict[str, Any]:
        return self._render_current()

    def answer(self, node_id: str, answer: Any) -> Dict[str, Any]:
        # ignore if node mismatch—trust engine current
        node = self.nodes.get(self.current_id or "")
        if not node:
            return {"done": True, "profile": self.profile, "answers": self.answers}
        # If control node types, we don't store answers
        ntype = node.get(CCS_TYPE)
        if ntype in (DQT_BRANCH, DQT_FOR_EACH):
            # shouldn't receive answers here; we auto-advance
            return self._auto_advance(node)

        # store answer, effects, next
        self.answers[node.get(CCS_ID)] = answer
        self.loop_state["__last_node_id__"] = node.get(CCS_ID)

        q = make_question(node, self.answers, self.profile, self.ctx, self.loop_state)
        q.apply_effects(answer)
        nxt = q.next_id(answer)
        if nxt is None or ntype == "end":
            self.current_id = None
            return {"done": True, "profile": self.profile, "answers": self.answers}
        self.current_id = nxt
        return self._render_current()

    # ------ internal helpers ------

    def _render_current(self) -> Dict[str, Any]:
        while self.current_id:
            node = self.nodes.get(self.current_id)
            if not node:
                break
            q = make_question(node, self.answers, self.profile, self.ctx, self.loop_state)

            # for invisible/control nodes we auto-advance
            if node.get(CCS_TYPE) == DQT_BRANCH:
                nxt = q.next_id(None)
                if nxt is None:
                    self.current_id = None
                    break
                self.current_id = nxt
                continue
            if node.get(CCS_TYPE) == DQT_FOR_EACH:
                nxt = q.advance()
                if nxt is None:
                    # loop over, move to after
                    self.current_id = node.get(CCS_AFTER)
                    continue
                # go into subflow
                self.current_id = nxt
                continue

            # normal question to render
            payload = q.render_payload()
            # Attach meta to help UI (optional)
            payload["meta"] = {"node": node.get(CCS_ID)}
            return {"node": payload, "answers": self.answers, "ctx": self.ctx}

        # finished
        self.current_id = None
        return {"done": True, "profile": self.profile, "answers": self.answers}

    def _auto_advance(self, node: dict) -> Dict[str, Any]:
        # called if UI accidentally posts an answer for branch/for_each
        return self._render_current()

# ------------------------- Excel builder (sketch) -------------------------

def build_tree_from_excel(path: str) -> Dict[str, Any]:
    """
    Minimal sketch. Requires pandas & openpyxl installed.
    See module docstring for expected sheets/columns.
    """
    try:
        import pandas as pd  # type: ignore
    except Exception as e:
        raise RuntimeError("pandas is required to build a tree from Excel") from e

    xls = pd.ExcelFile(path)
    meta = {"title": None, "version": None}
    if "meta" in xls.sheet_names:
        m = pd.read_excel(path, sheet_name="meta", header=None).fillna("")
        meta["title"] = str(m.iat[0,0]) if m.shape[0] > 0 else None
        meta["version"] = str(m.iat[1,0]) if m.shape[0] > 1 else None

    nodes_df = pd.read_excel(path, sheet_name="nodes").fillna("")
    nodes: Dict[str, Any] = {}
    for _, row in nodes_df.iterrows():
        nid = str(row.get(CCS_ID) or "").strip()
        if not nid: continue
        node = {
            CCS_ID: nid,
            CCS_TYPE: str(row.get(CCS_TYPE) or DQT_TEXT).strip(),
            CCS_PROMPT: row.get(CCS_PROMPT) or "",
        }
        # next: try parse JSON, else string
        nxt = row.get(CCS_NEXT)
        if isinstance(nxt, str) and nxt.strip():
            try:
                node[CCS_NEXT] = json.loads(nxt)
            except Exception:
                node[CCS_NEXT] = nxt.strip()
        # options
        if str(row.get(CCS_OPTIONS) or "").strip():
            try:
                node[CCS_OPTIONS] = json.loads(row.get(CCS_OPTIONS))
            except Exception:
                node[CCS_OPTIONS] = [s.strip() for s in str(row.get(CCS_OPTIONS)).split(",") if s.strip()]
        if str(row.get(CCS_OPTIONS_FROM_ANSWER_OF) or "").strip():
            node[CCS_OPTIONS_FROM_ANSWER_OF] = str(row.get(CCS_OPTIONS_FROM_ANSWER_OF)).strip()
        if str(row.get(CCS_SPLIT) or "").strip():
            node[CCS_SPLIT] = str(row.get(CCS_SPLIT)).strip()
        if str(row.get(CCS_USE_ANSWER_FROM) or "").strip():
            node[CCS_USE_ANSWER_FROM] = str(row.get(CCS_USE_ANSWER_FROM)).strip()
        if str(row.get(CCS_EFFECTS) or "").strip():
            try:
                node[CCS_EFFECTS] = json.loads(row.get(CCS_EFFECTS))
            except Exception:
                pass
        nodes[nid] = node

    start = nodes_df.iloc[0][CCS_ID] if not nodes_df.empty else None
    tree = {"meta": meta, "start": start, "nodes": nodes}
    return tree


if __name__ == "__main__":
    # tiny smoke test (optional)
    pass
