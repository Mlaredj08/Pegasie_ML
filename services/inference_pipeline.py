import simplejson
import os
import sys
import argparse
import pandas as pd
from flask import redirect, current_app

import services.iteration_service as iteration_manager
from config import FIELD_COMPLETION_FOLDER
from services.iteration_service import apply_iterations_to_db
from reporting.audit_generator import generate_audit_json_file
from ml.field_inference import infer_fields
from config.constants import TEMPLATES_FOLDER, CFG_PROJECT, CFG_INPUT_FILE, CFG_OUTPUT_FOLDER, CFG_FIELD_MODELS, \
    AUDIT_OUT_FILE_SUFFIX, UPDATED_DATABASE_FOLDER, UPDATED_DATABASE_FILE, ITERATION_FOLDER, CFG_EXCLUDE_CLOSED_ISSUES, \
    DATABASES_FOLDER, DEPENDENCY_MODEL_FOLDER, AUDIT_OUT_FILE
from config.constants import PREDICTION_PREFIX, CONFIDENCE_SUFFIX, CSV_FIELD_NAMES, INFERENCE_OUT_FILE_SUFFIX
import reporting.html_report_generator as html_generator
from utils_pkg.config_utils import load_config
import utils_pkg as utils

def get_config_filename_path(filename: str) -> str:
    if not filename.endswith(".json"):
        raise ValueError("Filename must end with .json")

    base = filename[:-5]
    parts = base.split("_", 1)
    if len(parts) != 2:
        raise ValueError("Filename format must be PREFIX_DATE_TIME.json")

    new_name = f"{parts[0]}_model_{parts[1]}.json"
    new_name = new_name.replace(DATABASES_FOLDER, DEPENDENCY_MODEL_FOLDER)
    return new_name

def run_field_completion(input_file, is_previous_iterations=True, iteration_to_include="", is_exclude_closed=False):
    config_path = get_config_filename_path(input_file)
    config = load_config(config_path)
    if config is None:
        project = utils.extract_project_key_from_filename(input_file)
        # is_exclude_closed = False
        output_folder = utils.extract_filename(input_file)
    else:
        project = config.get(CFG_PROJECT, CFG_PROJECT)
        output_folder = config.get(CFG_OUTPUT_FOLDER, project)
        # is_exclude_closed = config.get(CFG_EXCLUDE_CLOSED_ISSUES, False)

    output_html = os.path.join(TEMPLATES_FOLDER, AUDIT_OUT_FILE)

    # Generate HTML page
    html_generator.generate_audit_report_from_json(
        output_folder,
        output_html,
        project=project
    )

    # Generate Audit data JSON file
    generate_audit_json_file(
        input_file,
        output_folder,
        project,
        is_exclude_closed,
        is_previous_iterations=is_previous_iterations,
        iteration_to_include=iteration_to_include,

    )

    return redirect(f"/view/{AUDIT_OUT_FILE}")

def main():
    parser = argparse.ArgumentParser(
        description="Run inference pipeline for a given config file."
    )
    parser.add_argument(
        '--config',
        type=str,
        required=True,
        help="Path to JSON config file."
    )
    args = parser.parse_args()
    config_path = args.config

    config = load_config(config_path)
    utils.model_config = config

    project = config.get(CFG_PROJECT, CFG_PROJECT) # type: ignore
    input_file = config[CFG_INPUT_FILE] # type: ignore
    output_folder = config.get(CFG_OUTPUT_FOLDER, project) # type: ignore
    os.makedirs(output_folder, exist_ok=True)
    is_exclude_closed = config.get(CFG_EXCLUDE_CLOSED_ISSUES, False) # type: ignore
    updated_db_file = f"{UPDATED_DATABASE_FOLDER}\\{project}_{UPDATED_DATABASE_FILE}"
    # audit_file = [f for f in os.listdir(output_folder) if f.startswith(f'{project}{AUDIT_OUT_FILE_SUFFIX}')]
    audit_file = [f for f in os.listdir(FIELD_COMPLETION_FOLDER) if f.startswith(output_folder)]

    if len(audit_file) == 0:
        generate_audit_json_file(input_file, output_folder, project, is_exclude_closed)

    #This method won't do anything if the iterations folder is empty
    apply_iterations_to_db(input_file,ITERATION_FOLDER,updated_db_file)

    updated_database_folder = [f for f in os.listdir(UPDATED_DATABASE_FOLDER) if f.endswith(f'{project}_{UPDATED_DATABASE_FILE}')]
    if len(updated_database_folder) > 0:
        input_file = updated_db_file

    # 1) Load the input JSON into a DataFrame
    print(f"input_file >> {input_file}")
    df = pd.read_json(input_file)

    # 2) Perform field inference
    df_final, report_fields = infer_fields(
        df.copy(),
        config.get(CFG_FIELD_MODELS, {}), # type: ignore
        feedback_keywords=None,
        is_exclude_closed=config.get(CFG_EXCLUDE_CLOSED_ISSUES, False) # type: ignore
    )

    # 3) Select only the columns we want: key + original target fields +
    #    predicted_<field> + predicted_<field>_confidence
    field_models   = config.get(CFG_FIELD_MODELS, {}) # type: ignore
    targets        = list(field_models.keys())
    predicted_cols = [f"{PREDICTION_PREFIX}{t}" for t in targets]
    confidence_cols= [f"{col}{CONFIDENCE_SUFFIX}" for col in predicted_cols]
    cols_to_keep   = ["key"] + ["summary"] + targets + predicted_cols + confidence_cols + ["issuetype"]
    print(f"cols_to_keep >>> {cols_to_keep}")
    print(f"df_final >>> {df_final}")
    #df_filtered = df_final[cols_to_keep]
    df_filtered = df_final[list(filter(lambda x: x in df_final.keys(), cols_to_keep))]


    # 4) Save the filtered results to CSV and generate dataTables JSON data file
    output_json = os.path.join(output_folder, f"{project}{INFERENCE_OUT_FILE_SUFFIX}.json")
    output_csv = os.path.join(output_folder, f"{project}{INFERENCE_OUT_FILE_SUFFIX}.csv")
    json_rows = []
    dt_json_rows = []
    data = df_filtered.to_dict(orient='records')
    target_fields = [item for item in data[0].keys() if item.endswith(CONFIDENCE_SUFFIX)] # type: ignore
    for row in data:
        for field in target_fields:
            field_name = field.replace(PREDICTION_PREFIX, "").replace(CONFIDENCE_SUFFIX, "")  # type: ignore
            issue_key = row[CSV_FIELD_NAMES[0]]
            row_values = [issue_key, row[CSV_FIELD_NAMES[1]]]
            dt_row_values = {
                "key": issue_key,
                "summary": row[CSV_FIELD_NAMES[1]],
                # "issuetype": row[CSV_FIELD_NAMES[-1]]
            }

            prediction_key = f"{PREDICTION_PREFIX}{field_name}"
            accuracy_key = f"{prediction_key}{CONFIDENCE_SUFFIX}"
            if row[prediction_key]:

                text_map = (
                    report_fields.get(field_name, {})
                    .get("text_map", {})
                    .get(issue_key, "")
                )

                top_tokens = (
                    report_fields.get(field_name, {})
                    .get('explanations', {})
                    .get('per_issue', {})
                    .get(issue_key, {})
                    .get('top_tokens', [])
                )

                contribution_range = report_fields[field_name]['explanations']['contribution_range']
                row_values.extend([field_name, row[prediction_key], f"{row[accuracy_key]:.2f}", text_map, top_tokens, contribution_range, row[CSV_FIELD_NAMES[-1]]])
                dt_row_values.update({
                    "field": field_name,
                    "prediction": row[prediction_key],
                    "accuracy": f"{row[accuracy_key]:.2f}",
                    "text": text_map,
                    "top_keywords": top_tokens,
                    "contribution_range": contribution_range,
                    "issuetype": row[CSV_FIELD_NAMES[-1]]
                })
                json_rows.append(row_values)
                dt_json_rows.append(dt_row_values)

    df = pd.DataFrame(json_rows, columns=CSV_FIELD_NAMES)
    df.to_csv(output_csv, index=False)
    print(f"Inference completed. CSV written to {output_csv}")
    # dataTables JSON data source
    with open(output_json, 'w') as f:
        simplejson.dump({"data": dt_json_rows}, f, ignore_nan=True, indent=4)
    print(f"DataTable JSON written to {output_json}")

    return output_json

# ✅ Callable from app.py or CLI
def run_pipeline(config_path: str):
    sys.argv = ["run_inference_pipeline.py", "--config", config_path]
    return main()

if __name__ == "__main__":
    main()
