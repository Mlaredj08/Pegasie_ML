"""
Test utilities and helper functions for route testing.
"""
import json
import os
from unittest.mock import Mock


def create_mock_session(auth=True, jira_url="https://test.atlassian.net", 
                       username="test_user", password="test_pass"):
    """Create a mock session object."""
    session = {}
    if auth:
        session.update({
            'auth': True,
            'jira_url': jira_url,
            'jira_username': username,
            'jira_password': password
        })
    return session


def create_test_file_content():
    """Create test content for JSON files."""
    return {
        "issues": [
            {
                "key": "TEST-1",
                "fields": {
                    "summary": "Test Issue 1",
                    "description": "Test description",
                    "priority": {"name": "High"},
                    "components": [{"name": "Backend"}],
                    "labels": ["bug"],
                    "issuetype": {"name": "Bug"}
                }
            }
        ]
    }


def create_test_iteration_content():
    """Create test iteration file content."""
    return {
        "project": "TEST_PROJECT",
        "timestamp": "20230501_120000",
        "field": "priority",
        "predictions": [
            {
                "issue_key": "TEST-1",
                "predicted_value": "High",
                "confidence": 0.95,
                "original_value": "Medium"
            }
        ],
        "metadata": {
            "model_used": "random_forest",
            "accuracy": 0.85
        }
    }


def create_test_consolidated_content():
    """Create test consolidated iteration content."""
    return {
        "project": "TEST_PROJECT",
        "output_folder": "TEST_PROJECT_20230501_120000",
        "timestamp": "20230501_120000",
        "predictions_by_issuetype": {
            "Bug": [
                {
                    "field": "priority",
                    "new_value": "High",
                    "issue_keys": ["TEST-1"],
                    "confidence": 0.95
                }
            ]
        },
        "summary": {
            "total_predictions": 1,
            "total_issues": 1,
            "affected_fields": ["priority"]
        }
    }


def create_test_decision_tree():
    """Create test decision tree content."""
    return {
        "name": "Test Priority Tree",
        "description": "Test tree for priority assignment",
        "nodes": [
            {
                "id": "root",
                "type": "question",
                "question": "What is the impact?",
                "question_type": "single_select",
                "options": ["High", "Medium", "Low"],
                "children": {
                    "High": {
                        "id": "high_node",
                        "type": "answer",
                        "answer": {"priority": "High"}
                    },
                    "Medium": {
                        "id": "medium_node", 
                        "type": "answer",
                        "answer": {"priority": "Medium"}
                    },
                    "Low": {
                        "id": "low_node",
                        "type": "answer", 
                        "answer": {"priority": "Low"}
                    }
                }
            }
        ]
    }


def mock_jira_client_functions():
    """Mock Jira client functions."""
    return {
        'export_jira_issues': Mock(return_value={"issues": []}),
        'fetch_issue_fields': Mock(return_value={"fields": []}),
        'fetch_jira_fields': Mock(return_value={"fields": []}),
        'fetch_projects': Mock(return_value={"projects": []}),
        'fetch_users': Mock(return_value={"users": []}),
        'fetch_components_priorities_labels': Mock(return_value={}),
        'fetch_issue_types': Mock(return_value={"issueTypes": []}),
        'apply_prediction_json_to_jira': Mock(return_value={"success": True})
    }


def mock_azure_client_functions():
    """Mock Azure client functions."""
    return {
        'export_azure_work_items': Mock(return_value={"workItems": []}),
        '_build_headers': Mock(return_value={"Authorization": "Bearer test-token"})
    }


def create_test_form_data():
    """Create test form data for POST requests."""
    return {
        'jira_url': 'https://test.atlassian.net',
        'username': 'test_user',
        'password': 'test_password',
        'project': 'TEST_PROJECT',
        'filename': 'test_file.json',
        'report_type': 'blocker_blocked_priority'
    }


def create_test_json_data():
    """Create test JSON data for API endpoints."""
    return {
        'project': 'TEST_PROJECT',
        'output_folder': 'TEST_PROJECT_20230501_120000',
        'field': 'priority',
        'predictions': [
            {'issue_key': 'TEST-1', 'predicted_value': 'High', 'confidence': 0.95}
        ]
    }


def assert_json_response(response, expected_status=200, expected_data=None):
    """Helper to assert JSON response format."""
    assert response.status_code == expected_status
    assert response.content_type == 'application/json'
    if expected_data is not None:
        assert json.loads(response.data) == expected_data


def assert_template_response(response, expected_status=200, expected_template=None):
    """Helper to assert template response format."""
    assert response.status_code == expected_status
    assert 'text/html' in response.content_type
    if expected_template:
        assert expected_template.encode() in response.data


def create_temp_json_file(temp_dir, filename, content):
    """Create a temporary JSON file with given content."""
    file_path = os.path.join(temp_dir, filename)
    with open(file_path, 'w') as f:
        json.dump(content, f)
    return file_path
