# config/constants.py
# All constants migrated from the original constants.py - no logic changes
import os

# Base directory where the project root is located
BASE_DIR = os.path.dirname(os.path.dirname(__file__))

#parameter to set the confirmation questions clustering (4,3,5,3,5 Values to balanced clustering)
CQ_DEFAULT_WEIGHT_SCALE = 4
CQ_DEFAULT_MAX_REP = 3
CQ_DEFAULT_TOP_K = 5
CQ_DEFAULT_MIN_SHARED_TOKENS = 3
CQ_DEFAULT_MIN_ISSUE_COUNT_PER_CLUSTER = 5
CQ_CONFIDENCE_DEFAULT = 0.5

# Folders constants
DEPENDENCY_MODEL_FOLDER = "dependency_model"
DATABASES_FOLDER = "databases"
PREDICTIONS_FOLDER = "predictions"
TEMPLATES_FOLDER = "templates"
QUESTIONNAIRES_FOLDER = "questionnaires"
UPDATED_DATABASE_FOLDER = os.path.join(DATABASES_FOLDER, "updated")
DATABASES_SETTINGS_FOLDER = os.path.join(DATABASES_FOLDER, "settings")
ITERATION_FOLDER = os.path.join(BASE_DIR, "iterations")
ITERATION_READY_TO_SEND = os.path.join(BASE_DIR, "iterations/ready_to_send")
SAVED_ITERATION_FOLDER = os.path.join(BASE_DIR, "saved_iterations")
PERFORMANCE_FOLDER = os.path.join(BASE_DIR, "performances")
PROMPTS_FOLDER = "prompts"
TREES_FOLDER = os.path.join(BASE_DIR, "decision_tree/trees")
DECISION_TREE_FOLDER = os.path.join(BASE_DIR, "decision_tree/")
INFERABILITY_ANALYSIS = "inferability_analysis"
FIELD_COMPLETION_FOLDER = os.path.join(BASE_DIR, "field_completion")

#CSV Columns Structure: Decision tree variables
CCS_OPTIONS_FROM_ANSWER_OF = "options_from_answer_of"
CCS_OPTIONS = "options"
CCS_SPLIT = "split"
CCS_USE_ANSWER_FROM = "use_answer_from"
CCS_EFFECTS = "effects"
CCS_PROMPT = "prompt"
CCS_TYPE = "type"
CCS_ID = "id"
CCS_NEXT = "next"
CCS_SOURCE = "source"
CCS_AFTER = "after"
CCS_ITEM_VAR = "item_var"

#Decision tree question types
DQT_YES_NO = "yes_no"
DQT_TEXT = "text"
DQT_LIST = "list"
DQT_SINGLE_SELECT = "single_select"
DQT_MULTI_SELECT = "multi_select"
DQT_BRANCH = "branch"
DQT_FOR_EACH = "for_each"

# Files
# ITERATION_FILE = "iteration"
TRACEABILITY_ITERATION_TABLE_FILE = "iteration_traceability"
UPDATED_DATABASE_FILE = "updated_db.json"
JIRA_USERS_FILE = "jira_users.json"
JIRA_USER_REGISTRY_FILE = os.path.join(BASE_DIR, "auth", "jira_user_registry.json")
JIRA_COMPONENTS_PRIORITIES_FILE = "jira_components_priorities.json"

#Default JIRA fields
DEFAULT_FIELDS = [
    "key", "summary", "description", "issuetype", "status", "project",
    "priority", "components", "labels", "fixVersions", "parent", "subtasks",
    "issuelinks", "reporter", "creator", "resolution", "assignee", "created",
    "updated", "resolutiondate", "epic_link"
]

#confirmation page
WORDS_TO_IGNORE_CONFIRMATION_QUESTIONS = [
    "the", "and", "is", "in", "to", "of", "a", "with", "on", "for","no", "by", "an", "not", "when", "should", "can",
    "this", "that", "be", "or", "are", "from", "it", "as", "at", "if", "we"
]

# Model name constants
SKLEARN_VERSION  = "1.7.0"
LOGISTIC_REGRESSION = "logisticregression"
RANDOM_FOREST      = "randomforest"
LINEAR_SVC         = "linearsvc"
MULTINOMIAL_NB     = "multinomialnb"
SGD_CLASSIFIER     = "sgd"

# Default model if none matches
DEFAULT_MODEL      = RANDOM_FOREST
DEFAULT_SOURCE_FIELDS = ["summary", "description"]

# Configuration dictionary keys
CFG_PROJECT       = "project"
CFG_CONFIDENCE       = "confidence"
CFG_INPUT_FILE    = "input_file"
CFG_OUTPUT_FOLDER = "output_folder"
CFG_FIELD_MODELS  = "field_models"
CFG_MODEL  = "model"
CFG_SOURCE_FIELDS  = "source_fields"
CFG_CONFIDENCE_FIELD  = "confidence"
CFG_MODEL_PARAMS  = "model_params"
CFG_EXCLUDE_CLOSED_ISSUES = "is_exclude_closed_issues"

# Full summary json
FQS_PREDICTED_VALUE = "predicted_value"
FQS_FIELD_NAME = "field_name"
FQS_SHARED_FEATURES = "shared_features"
FQS_CLUSTER_ISSUES_COUNT = "cluster_issues_count"
FQS_LIST_OF_ISSUES = "list_of_issues"
FQS_LISTS_OF_CONFIDENCE = "lists_of_confidence"

# Iteration report object
IRO_ITERATION = "iteration"
IRO_TIME_STAMP = "time_stamp"
IRO_PREDICTIONS = "predictions"
IRO_CONFIDENCE = "confidence"
IRO_APPROVED = "approved"
IRO_REJECTED = "rejected"
IRO_PUSHED = "pushed"
IRO_QUESTIONS = "questions"
IRO_FIELD = "field"
IRO_CUMULATIVE_APPROVED = "cumulative_approved"
IRO_REMAINING = "remaining"
IRO_QUESTIONS_NUMBER = "questions_number"
IRO_COMPLETION = "completion"
IRO_USER = "user"

# Per field iteration data
FID_ISSUE_COUNT = "issue_count"
FID_TOTAL_ISSUE_COUNT = "total_issue_count"
FID_AVG_ACCURACY = "avg_accuracy"
FID_APPROVED = "approved"
FID_TOTAL_CONFIDENCE = "confidence_avg"
FID_ORPHAN_COUNT = "orphan_count"
FID_QUESTION_COUNT = "question_count"
FID_AVAILABLE_ISSUES = "available_issue_count"

#Iteration file convention
IFC_TIME_STAMP = "time_stamp"
IFC_USER = "user"
IFC_TARGET_FIELDS = "target_fields"
IFC_VALUE = "value"
IFC_QUESTION_INDEX = "question_index"
IFC_ISSUE_KEYS = "issue_keys"
IFC_TAGGED_ISSUE_KEYS = "tagged_issue_keys"
IFC_KEYWORDS = "keywords"
IFC_FIELD_NAME = "field_name"
IFC_STATUS = "status"
IFC_PREDICTIONS = "predictions"
IFC_NEW_KEYWORDS = "new_keywords"
IFC_ORIGINAL_VALUE = "original_prediction_value"
IFC_CHANGED_KEYWORDS_LIST = "changed_keywords_list"

#audit report object
ARO_INCOMPLETE = "incomplete"

# Inference
PREDICTION_PREFIX = "predicted_"
CONFIDENCE_SUFFIX = "_confidence"
CSV_FIELD_NAMES = [
    "key",
    "summary",
    "field",
    "predicted",
    "confidence",
    "text_map",
    "top_tokens",
    "contribution_range",
    "issuetype"
]
INFERENCE_OUT_FILE_SUFFIX = "_inferred"
AUDIT_OUT_FILE_SUFFIX = "_audit"
AUDIT_OUT_FILE = "audit.html"
ITERATION_PREFIX = "iteration_"

PRIMITIVE_SCHEMA_TYPES = {
    "string",
    "number",
    "long",
    "float",
    "double",
    "date",
    "datetime",
    "boolean",
    "int",
    "integer",
}

# TODO: add proper descriptions
TOOLTIP_DICT = {
    "import": "Connect to Jira and import a project's data as a JSON file",
    "import_azure": "Connect to Azure and import a project's data as a JSON file",
    "completion": "Show completion per field for a given Jira project",
    "profile": "Convert Excel questionnaire into a JSON file",
    "config": "Generate configuration file",
    "infer": "Run inference using configuration file",
    "analysis": "Run data pre-analysis",
    "jira_viewer": "View a Jira JSON file and run ML inference"
}

KEYWORDS_TO_IGNORE = [r'{color.*?}']
TEST_JSON_FILE = "inference_tests.json"
TEST_RESULTS_JSON_FILE = "inference_test_results.json"
RAND_TEST_JSON_FILE ="inference_rand_tests.json"


# azure API VERSION
AZURE_API_VERSION = "5.1"

DEFAULT_AZURE_FIELDS = [
    "System.Id",
    "System.Title",
    "System.Description",
    "System.WorkItemType",
    "System.State",
    "System.TeamProject",
    "Microsoft.VSTS.Common.Priority",
    "System.Tags",
    "System.AreaPath",
    "System.IterationPath",
    "System.AssignedTo",
    "System.CreatedDate",
    "System.ChangedDate",
    "System.Reason",
    "System.CreatedBy",
    "System.ChangedBy"
]

UNPREDICTABLE_FIELDS = [
            "description",
            "subtasks",
            "issuelinks",
            "parent",
            "fixVersions",
            "comments",
            "resolution",
            "resolutiondate"
]

IMPOSSIBLE_LINKS = {"epic_link": ["Epic", "Sub-task"]}

STATUSES_TO_EXCLUDE = ["Closed", "Resolved"]