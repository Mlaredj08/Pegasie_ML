#!/usr/bin/env python3
import pandas as pd
import json
import os

from flask import flash

from config.constants import QUESTIONNAIRES_FOLDER

EXCEL_PATH = os.path.join(QUESTIONNAIRES_FOLDER, "qa_questionaire.xlsx")
JSON_PATH = os.path.join(QUESTIONNAIRES_FOLDER, "qa_questionaire.json")

def generate_qa_json(excel_path: str, json_path: str):
    """
    Reads an Excel with columns: [field, question_type, question, answer]
    where 'field' is actually the target field name (e.g. "components" or "priority"),
    and 'question_type' is either "depends_on_questions" or "strategy_questions".
    Outputs a JSON with structure:
    {
      "components": {
        "depends_on_questions": [ {question, answer}, … ],
        "strategy_questions":   [ {question, answer}, … ]
      },
      "priority": { … }
    }
    """
    # 1) Load the sheet into a DataFrame
    df = pd.read_excel(excel_path, dtype=str)

    # 2) Validate expected columns
    expected = {"field", "question_type", "question", "answer"}
    if not expected.issubset(df.columns):
        raise RuntimeError(f"Expected columns {expected} in Excel, got {df.columns.tolist()}")

    # 3) Build the nested dict
    result = {}
    # df['components'] holds the field name
    for field_name, group in df.groupby("field"):
        # initialize substructure
        result[field_name] = {
            "depends_on_questions": [],
            "strategy_questions": []
        }
        # for each row, append to the proper list
        for _, row in group.iterrows():
            qtype = row["question_type"]
            qa = {
                "question": row["question"],
                "answer":   row["answer"]
            }
            # sanity check
            if qtype not in result[field_name]:
                raise RuntimeError(f"Unknown question_type '{qtype}' in row: {row.to_dict()}")
            result[field_name][qtype].append(qa)

    # 4) Write out as pretty JSON
    os.makedirs(os.path.dirname(json_path) or ".", exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Profile JSON file to: {json_path}")
    flash(f"Profile file generated successfully: {json_path}", "success")

if __name__ == "__main__":
    generate_qa_json(EXCEL_PATH, JSON_PATH)
