# utils_pkg/text_utils.py
"""Text/string utilities: issue key extraction, CSV tree building, prompt construction."""
import json
import csv
import re

from config.constants import (
    CCS_OPTIONS_FROM_ANSWER_OF, CCS_OPTIONS, CCS_SPLIT, CCS_USE_ANSWER_FROM,
    CCS_EFFECTS, CCS_PROMPT, CCS_TYPE, CCS_ID, CCS_NEXT, CCS_SOURCE,
    CCS_AFTER, CCS_ITEM_VAR, DQT_TEXT
)

_ISSUE_KEY_RE = re.compile(r'^([A-Z][A-Z0-9]+-\d+)')


def extract_issue_key(s: str) -> str:
    m = _ISSUE_KEY_RE.match(s.strip())
    if m:
        return m.group(1)
    return s.split(":", 1)[0].strip()

def extract_question_id_and_issue_key(s: str):
    question_id_issue_key_separator = "|"
    m = _ISSUE_KEY_RE.match(s.strip())
    if m:
        l = m.group(1).split(question_id_issue_key_separator)
    l = s.split(":", 1)[0].strip().split(question_id_issue_key_separator)
    return l[0], l[1]


def _maybe_json(value: str):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return s


def _parse_options(cell: str):
    if not cell: return None
    s = cell.strip()
    if not s: return None
    maybe = _maybe_json(s)
    if isinstance(maybe, list):
        return maybe
    # comma-separated fallback
    return [x.strip() for x in s.split(",") if x.strip()]


def build_tree_from_csv_text(text: str, start_id=None):
    reader = csv.DictReader(text.splitlines())
    nodes = {}
    first_id = None
    for row in reader:
        nid = (row.get(CCS_ID,"") or "").strip()
        if not nid: continue
        if first_id is None: first_id = nid
        node = {
            CCS_ID: nid,
            CCS_TYPE: (row.get(CCS_TYPE,DQT_TEXT) or DQT_TEXT).strip(),
            CCS_PROMPT: row.get(CCS_PROMPT,"") or ""
        }
        # next
        node_next = (row.get(CCS_NEXT,"") or "").strip()
        if node_next:
            node[CCS_NEXT] = _maybe_json(node_next) or node_next
        # options
        opts = _parse_options(row.get(CCS_OPTIONS,"") or "")
        if opts: node[CCS_OPTIONS] = opts
        # simple pass-throughs
        for k in (CCS_OPTIONS_FROM_ANSWER_OF,CCS_SPLIT,CCS_USE_ANSWER_FROM,CCS_SOURCE,CCS_ITEM_VAR,CCS_AFTER):
            v = (row.get(k,"") or "").strip()
            if v: node[k] = v
        # effects
        effs = (row.get(CCS_EFFECTS,"") or "").strip()
        if effs:
            maybe = _maybe_json(effs)
            if isinstance(maybe, list):
                node[CCS_EFFECTS] = maybe
        nodes[nid] = node
    tree = {
        "start": start_id or first_id,
        "nodes": nodes
    }
    return tree


def _build_suggestion_prompt(profile: dict, answers: dict) -> str:
    return (
        "You are an assistant that designs JSON decision trees for a questionnaire engine.\n"
        "The engine uses JSON in this shape:\n"
        "{\n"
        '  "start": "<node_id>",\n'
        '  "meta": {\n'
        '    "name": "string",\n'
        '    "version": "1.0.0",\n'
        '    "objective": "what this tree is trying to deepen"\n'
        "  },\n"
        '  "nodes": {\n'
        '    "<node_id>": {\n'
        '       "id": "...",\n'
        '       "type": "text|list|yes_no|single_select|multi_select|branch|for_each",\n'
        '       "prompt": "...",\n'
        '       "next": "next_node_id" or list of {when, goto} rules,\n'
        '       "options": ["opt1", "opt2"]\n'
        "    }\n"
        "  }\n"
        "}\n\n"
        "We already ran a first decision tree. Below is the PROFILE (what was built from the answers) "
        "and the RAW ANSWERS (per node). Based on this, propose 2-3 complementary trees that go deeper into missing or unclear parts "
        "of a Jira/Test Management data structure (components, labels, links, templates, test-case derivation, severity/priorities, etc.).\n"
        "Each suggestion must be a JSON object with: file_name, objective, tree.\n"
        "Return strictly a JSON object with key 'suggestions'.\n\n"
        f"PROFILE:\n{json.dumps(profile, indent=2)}\n\n"
        f"ANSWERS:\n{json.dumps(answers, indent=2)}\n"
    )


if __name__ == "__main__":
    s1 = "FBEZ-222_development : Manage user communication and consent preference settings"
    s2 = "q-11_FBEZ-222"
    print(extract_question_id_and_issue_key(s1))
    print(extract_question_id_and_issue_key(s2))