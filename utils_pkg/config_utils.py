# utils_pkg/config_utils.py
"""Configuration and data loading utilities: config files, prompt settings, field extraction."""
import json
import os

from config.constants import PROMPTS_FOLDER


def load_prompt_settings():
    try:
        file = os.path.join(PROMPTS_FOLDER, "settings.json")
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"ERROR: Prompt settings file not found: {e}")


def list_chatgpt_models():
    from openai import OpenAI
    settings = load_prompt_settings()
    open_ai_api_key = settings.get("open_ai_api_key")
    client = OpenAI(api_key=open_ai_api_key)
    response = client.models.list()
    for model in response.data:
        print(model.id)


def load_config(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config
    except Exception:
        return None


def extract_fields(json_path):
    """Return all keys (field names) in the first record of the JSON array."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not isinstance(data, list) or not data:
        return []

    # Return every key in the first issue
    return list(data[0].keys())


def get_issuetype_lookup(db_path):
    """
    Loads the database JSON file and creates a lookup dictionary mapping issue key to issue type.
    """
    if not db_path or not os.path.exists(db_path):
        return {}
    
    try:
        with open(db_path, 'r', encoding='utf-8') as f:
            issues = json.load(f)
        
        lookup = {}
        for issue in issues:
            key = issue.get("key", "")
            issuetype = issue.get("issuetype", "Unknown")
            if key:
                lookup[key] = issuetype
        return lookup
    except Exception as e:
        print(f"Error loading database for issuetype lookup: {e}")
        return {}
