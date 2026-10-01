# utils_pkg package
# Named utils_pkg to avoid collision with the existing utils.py module
from utils_pkg.file_utils import (
    extract_project_key_from_filename, get_file_names_by_extension,
    extract_filename, get_folder_paths, get_current_files,
    validate_json_file, save_json_file,
    get_cacheable_folder_paths, get_cached_files,
    get_timestamp_root_folders, get_all_clearable_items
)
from utils_pkg.text_utils import (
    extract_issue_key, build_tree_from_csv_text,
    _build_suggestion_prompt, _maybe_json, _parse_options
)
from utils_pkg.config_utils import (
    load_config, load_prompt_settings, list_chatgpt_models,
    extract_fields, get_issuetype_lookup
)

# Mutable module-level state — kept here so `import utils_pkg; utils_pkg.model_config` works
model_config = None
