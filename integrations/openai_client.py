import os
import json
from jinja2 import Template
from flask import flash
# openai is imported lazily inside functions that need it

import utils_pkg as utils
from config.constants import DEPENDENCY_MODEL_FOLDER, LOGISTIC_REGRESSION, RANDOM_FOREST, LINEAR_SVC, \
    MULTINOMIAL_NB, SGD_CLASSIFIER, DEFAULT_FIELDS, DATABASES_FOLDER, CFG_PROJECT, CFG_CONFIDENCE_FIELD, \
    CFG_INPUT_FILE, CFG_OUTPUT_FOLDER, CFG_FIELD_MODELS, SKLEARN_VERSION, \
    CFG_EXCLUDE_CLOSED_ISSUES, PROMPTS_FOLDER


def ask_chatgpt(prompt, system_prompt="You are an AI assistant that outputs JSON only."):
    settings = utils.load_prompt_settings()
    gpt_temperature = settings.get("gpt_temperature")
    gpt_model = settings.get("gpt_model")
    open_ai_api_key = settings.get("open_ai_api_key")
    from openai import OpenAI
    client = OpenAI(api_key=open_ai_api_key)

    response = client.chat.completions.create(
        model= gpt_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature = gpt_temperature
    )
    return response.choices[0].message.content

def build_prompt_from_json_answers(json_path, field_name, source_fields):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            question_dict = json.load(f)
    except Exception as e:
        print(f"Error reading JSON file: {e}")
        return None

    field_data = question_dict.get(field_name)
    if not field_data:
        print(f"Field '{field_name}' not found in the file.")
        return None

    depends_on_answers = field_data.get("depends_on_questions", [])
    strategy_answers = field_data.get("strategy_questions", [])

    # Load settings to know which template to use
    settings = utils.load_prompt_settings()
    template_filename = settings.get("prompt_template")
    if not template_filename:
        print("No 'prompt_template' defined in settings.json")
        raise ValueError("No 'prompt_template' defined in settings.json")

    template_path = os.path.join(PROMPTS_FOLDER, template_filename)
    if not os.path.isfile(template_path):
        print(f"Template file not found: {template_path}")
        raise FileNotFoundError(f"Template file not found: {template_path}")

    # Read template
    with open(template_path, "r", encoding="utf-8") as tf:
        template_text = tf.read()

    # Helper to create Q/A block
    def to_block(items):
        return "\n".join(
            f"{i}. Q: {qa.get('question','')}\n   A: {qa.get('answer','')}"
            for i, qa in enumerate(items, 1)
        ) or "(none)"

    # Constants you already have in code
    constants = {
        "LOGISTIC_REGRESSION": LOGISTIC_REGRESSION,
        "RANDOM_FOREST": RANDOM_FOREST,
        "LINEAR_SVC": LINEAR_SVC,
        "MULTINOMIAL_NB": MULTINOMIAL_NB,
        "SGD_CLASSIFIER": SGD_CLASSIFIER,
        "SKLEARN_VERSION": SKLEARN_VERSION,
    }

    # Render template
    prompt_text = Template(template_text).render(
        field_name=field_name,
        source_fields=source_fields,
        depends_block=to_block(depends_on_answers),
        strategy_block=to_block(strategy_answers),
        **constants
    )

    print("\n▶ Sending responses to ChatGPT for analysis...\n")
    result = ask_chatgpt(prompt_text)
    print("\n--- ChatGPT Response (JSON) ---\n")
    return result

def build_config(
        project: str,
        input_file: str,
        output_folder: str,
        field_list: list,
        confidence: str,
        is_exclude_closed: bool
) -> str:

    formatted_list = []
    for raw in field_list:
        formatted_list.append(raw.strip()[1:-1].strip())

    all_fields = ", ".join(formatted_list)

    config_str = f"""{{
      "{CFG_PROJECT}": "{project}",
      "{CFG_CONFIDENCE_FIELD}": {confidence},
      "{CFG_INPUT_FILE}": "{DATABASES_FOLDER}/{input_file}",
      "{CFG_OUTPUT_FOLDER}": "{output_folder}",
      "{CFG_FIELD_MODELS}": {{
        {all_fields}
      }}
    }}"""

    os.makedirs(DEPENDENCY_MODEL_FOLDER, exist_ok=True)
    timestamp = "_".join(os.path.splitext(input_file)[0].rsplit("_", 2)[1:])
    filename = f"{project}_model_{timestamp}.json"
    output_path = os.path.join(DEPENDENCY_MODEL_FOLDER, filename)

    with open(output_path, 'w', encoding="utf-8") as f:
        data = json.loads(config_str)
        data[CFG_EXCLUDE_CLOSED_ISSUES] = is_exclude_closed
        json.dump(data, f, indent=4)

    flash(f"ML configuration created successfully: {filename}", "success")

    return config_str


def build_config_chatgpt(
        project: str,
        input_file: str,
        output_folder: str,
        fields_to_infer_list: list,
        questionnaire_file: str,
        source_fields: str,
        confidence: str,
        is_exclude_closed: bool = False
):

    extracted_json = []

    for field in fields_to_infer_list:
        result = build_prompt_from_json_answers(questionnaire_file, field, source_fields)
        extracted_json.append(result.replace("```json", "").replace("```", "").strip()) # type: ignore

    cfg = build_config(
        project = project,
        input_file = input_file,
        output_folder = output_folder,
        field_list = extracted_json,
        confidence = confidence,
        is_exclude_closed = is_exclude_closed
    )

    print(json.dumps(cfg, indent=2))

#
# if __name__ == "__main__":
#     fields_to_infer = ["components","priority"]
#     questions_and_answers_json = "C:\\Users\\Armando\\Downloads\\questions_and_aswer.json"
#
#     outcome = ""
#     extracted_json = []
#     for field in fields_to_infer:
#         result = build_prompt_from_json_answers(questions_and_answers_json,field, DEFAULT_FIELDS)
#         extracted_json.append(result.replace("```json", "").replace("```", "").strip()) # type: ignore
#
#
#     cfg = build_config(
#         project="CIA",
#         input_file= DATABASES_FOLDER + "/CIA_20250618_132641.json",
#         output_folder="CIA_20250618_132641",
#         field_list=extracted_json
#     ) # type: ignore
#
#     print(json.dumps(cfg, indent=2))
