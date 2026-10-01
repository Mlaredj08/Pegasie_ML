"""
Test constants for authentication and test data.
Central place to update authentication credentials for all tests.
"""

# Authentication Constants
TEST_JIRA_URL = "https://test.atlassian.net"
TEST_JIRA_USERNAME = "Frank"
TEST_JIRA_PASSWORD = "pegasie123"
TEST_JIRA_REMEMBER = False

# Jira Cloud API Token Authentication (for Jira Cloud routes)
TEST_JIRA_CLOUD_URL = "https://test.atlassian.net"
TEST_JIRA_CLOUD_USERNAME = "fmulett@pegasie.com"
TEST_JIRA_CLOUD_API_TOKEN = "api-token-test"
TEST_JIRA_CLOUD_EMAIL = "fmulett@pegasie.com"  # Jira Cloud uses email for API token auth

# Session Authentication Data
TEST_AUTH_SESSION = {
    "auth": True,
    "jira_url": TEST_JIRA_URL,
    "jira_username": TEST_JIRA_USERNAME,
    "jira_password": TEST_JIRA_PASSWORD,
    "permanent": TEST_JIRA_REMEMBER
}

# Jira Cloud Session Authentication Data
TEST_JIRA_CLOUD_SESSION = {
    "auth": True,
    "jira_url": TEST_JIRA_CLOUD_URL,
    "jira_username": TEST_JIRA_CLOUD_USERNAME,
    "jira_password": TEST_JIRA_CLOUD_API_TOKEN,  # API token stored as password for session
    "jira_email": TEST_JIRA_CLOUD_EMAIL,
    "permanent": False
}

# Azure DevOps Test Constants
TEST_AZURE_ORG_URL = "https://dev.azure.com/testorg"
TEST_AZURE_PROJECT = "TestProject"
TEST_AZURE_PAT = "test_pat_token"

# Project and File Constants
TEST_PROJECT = "ECOMBNUKE"
TEST_PROJECT_KEY = "ECOMBNUKE"
TEST_FILENAME = "test_file.json"
TEST_OUTPUT_FOLDER = "TEST_PROJECT_20230501_120000"

# Test Data Constants
TEST_ISSUE_KEY = "AURCRQ-6215"
TEST_ISSUE_SUMMARY = "Aurora-Finances - Généraliser le concept Employee/NewFeed"
TEST_ISSUE_DESCRIPTION = """Iteration Path: Aurora\Foundation Forces\2023.Q3
Value Area: Business
Created by: Eric Bernier <EBernier@pgsolutions.com>"""

# Field Constants
TEST_FIELD_PRIORITY = "priority"
TEST_FIELD_COMPONENTS = "components"
TEST_FIELD_LABELS = "labels"
TEST_FIELD_EPIC_LINK = "customfield_10014"
TEST_FIELD_TEAM = "customfield_10020"

# Test Values
TEST_PRIORITY_HIGH = "High"
TEST_PRIORITY_MEDIUM = "Medium"
TEST_PRIORITY_LOW = "Low"
TEST_COMPONENT_BACKEND = "Backend"
TEST_COMPONENT_FRONTEND = "Frontend"
TEST_LABEL_BUG = "bug"
TEST_LABEL_ENHANCEMENT = "enhancement"

# Decision Tree Constants
TEST_TREE_NAME = "test_tree.json"
TEST_SESSION_ID = "test_session_123"
TEST_NODE_ID_ROOT = "root"
TEST_NODE_ID_NEXT = "next_node"

# Test User Constants
TEST_USER = "Frank"

# File Manager Constants
TEST_CATEGORY_PREDICTIONS = "predictions"
TEST_CATEGORY_ML_MODELS = "ml_models"
TEST_CATEGORY_ITERATIONS = "iterations"

# HTTP Status Codes
HTTP_OK = 200
HTTP_CREATED = 201
HTTP_FOUND = 302
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_METHOD_NOT_ALLOWED = 405
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE_ENTITY = 422
HTTP_INTERNAL_SERVER_ERROR = 500
HTTP_BAD_GATEWAY = 502

# Response Messages
ERROR_NOT_AUTHENTICATED = "Not authenticated"
ERROR_JSON_NOT_FOUND = "JSON file not found"
ERROR_JSON_DECODE = "Error decoding JSON"
ERROR_MISSING_FIELDS = "Missing jira_url, username, or password/token"
ERROR_JIRA_AUTH_FAILED = "JIRA auth failed"
ERROR_CONNECTION_ERROR = "Connection error"

# Mock Response Templates
MOCK_JIRA_USER_RESPONSE = {
    "name": TEST_JIRA_USERNAME,
    "emailAddress": "test@example.com",
    "displayName": "Test User"
}

MOCK_JIRA_PROJECTS_RESPONSE = {
    "projects": [
        {"key": TEST_PROJECT_KEY, "name": "Test Project"}
    ]
}

MOCK_JIRA_FIELDS_RESPONSE = {
    "fields": [
        {"name": "priority", "schema": {"type": "priority"}},
        {"name": "components", "schema": {"type": "array"}},
        {"name": "labels", "schema": {"type": "array"}},
        {"name": "epic_link", "schema": {"type": "string"}}
    ]
}

# Jira Cloud Specific Mock Responses
MOCK_JIRA_CLOUD_USER_RESPONSE = {
    "accountId": "1234567890abcdef",
    "accountType": "atlassian",
    "active": True,
    "displayName": "Frank",
    "emailAddress": TEST_JIRA_CLOUD_EMAIL,
    "name": TEST_JIRA_CLOUD_USERNAME
}

MOCK_JIRA_CLOUD_PROJECTS_RESPONSE = {
    "values": [
        {
            "id": "10000",
            "key": TEST_PROJECT_KEY,
            "name": "Test Project",
            "projectTypeKey": "software",
            "simplified": False
        }
    ],
    "maxResults": 50,
    "startAt": 0,
    "total": 1
}

MOCK_JIRA_CLOUD_FIELDS_RESPONSE = {
    "fields": [
        {
            "id": "priority",
            "name": "Priority",
            "schema": {"type": "priority", "system": "priority"}
        },
        {
            "id": "components",
            "name": "Components",
            "schema": {"type": "array", "items": "component", "system": "components"}
        },
        {
            "id": "labels",
            "name": "Labels", 
            "schema": {"type": "array", "items": "string", "system": "labels"}
        },
        {
            "id": "customfield_10014",
            "name": "Epic Link",
            "schema": {"type": "string", "custom": "com.pyxis.greenhopper.jira:gh-epic-link", "customId": 10014}
        }
    ]
}

MOCK_AZURE_WORK_ITEM_TYPES = [
    {"name": "Bug", "description": "Bug work item type"},
    {"name": "User Story", "description": "User story work item type"},
    {"name": "Task", "description": "Task work item type"}
]

MOCK_AZURE_FIELDS = [
    {"name": "System.Title", "referenceName": "System.Title", "type": "String"},
    {"name": "System.Description", "referenceName": "System.Description", "type": "String"},
    {"name": "Microsoft.VSTS.Common.Priority", "referenceName": "Microsoft.VSTS.Common.Priority", "type": "Integer"}
]

# Test File Paths
TEST_DATABASE_PATH = f"databases/{TEST_PROJECT}.json"
TEST_ITERATION_PATH = f"iterations/{TEST_PROJECT}_iteration_20230501_120000.json"
TEST_CONSOLIDATED_PATH = f"ready_to_send/{TEST_PROJECT}_consolidated_20230501_120000.json"

# Pagination and Limits
TEST_MAX_ISSUES = 100
TEST_PAGE_SIZE = 50

# Timeout Constants
TEST_TIMEOUT_SECONDS = 10
TEST_REQUEST_TIMEOUT = 30

# Confidence Thresholds
TEST_MIN_CONFIDENCE = 75
TEST_HIGH_CONFIDENCE = 90
TEST_LOW_CONFIDENCE = 50

# Model Types
TEST_MODEL_RANDOM_FOREST = "random_forest"
TEST_MODEL_MLP = "MLP"
TEST_MODEL_MULTI_MODEL = "multi_model"

# Report Types
TEST_REPORT_BLOCKER_BLOCKED = "blocker_blocked_priority"
TEST_REPORT_PARENT_CHILD_PRIORITY = "parent_child_priority"
TEST_REPORT_PARENT_CHILD_COMPONENTS = "parent_children_components"
TEST_REPORT_INHERITANCE_RULES = "inheritance_rules"

# Validation Constants
VALID_JIRA_URLS = [
    "https://test.atlassian.net",
    "https://company.atlassian.net",
    "https://jira.company.com"
]

INVALID_JIRA_URLS = [
    "not-a-url",
    "ftp://invalid-protocol.com",
    "https://not-jira.com"
]

VALID_FIELD_TYPES = [
    "priority",
    "components", 
    "labels",
    "epic_link",
    "customfield_10010"
]

INVALID_FIELD_TYPES = [
    "invalid_field",
    "",
    "field with spaces"
]
