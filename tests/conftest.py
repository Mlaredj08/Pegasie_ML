"""
Pytest configuration and shared fixtures for testing Flask routes.
"""
import json
import os
import tempfile
import pytest
import shutil
from unittest.mock import Mock, patch
from flask import Flask

from app import app
from web.shared_state import SESSIONS, inference_progress_dict, clustering_progress_dict
from tests.test_constants import (
    TEST_AUTH_SESSION
)


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SECRET_KEY'] = 'test-secret-key'
    
    with app.test_client() as client:
        with app.app_context():
            # Clear shared state before each test
            SESSIONS.clear()
            inference_progress_dict.clear()
            clustering_progress_dict.clear()
            clustering_progress_dict.update({
                "completed": [],
                "total": 0,
                "in_progress": None,
            })
            yield client


@pytest.fixture
def auth_client(client):
    """Create a test client with authenticated session."""
    with client.session_transaction() as sess:
        sess.update(TEST_AUTH_SESSION)
    return client


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_jira_data():
    """Sample Jira data for testing."""
    return {
        "issues": [
            {
                "key": "TEST-1",
                "fields": {
                    "summary": "Test issue 1",
                    "description": "Test description",
                    "priority": {"name": "High"},
                    "components": [{"name": "Backend"}],
                    "labels": ["bug", "urgent"],
                    "issuetype": {"name": "Bug"}
                }
            },
            {
                "key": "TEST-2", 
                "fields": {
                    "summary": "Test issue 2",
                    "description": "Another test description",
                    "priority": {"name": "Medium"},
                    "components": [{"name": "Frontend"}],
                    "labels": ["enhancement"],
                    "issuetype": {"name": "Story"}
                }
            }
        ]
    }


@pytest.fixture
def sample_database_file(temp_dir, sample_jira_data):
    """Create a sample database JSON file."""
    db_path = os.path.join(temp_dir, "TEST_PROJECT.json")
    with open(db_path, 'w') as f:
        json.dump(sample_jira_data, f)
    return db_path


@pytest.fixture
def mock_jira_response():
    """Mock successful Jira API response."""
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "name": "test_user",
        "emailAddress": "test@example.com",
        "displayName": "Test User"
    }
    return mock_resp


@pytest.fixture
def mock_azure_response():
    """Mock successful Azure DevOps API response."""
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "value": [
            {"name": "System.Title", "referenceName": "System.Title"},
            {"name": "System.Description", "referenceName": "System.Description"},
            {"name": "Microsoft.VSTS.Common.Priority", "referenceName": "Microsoft.VSTS.Common.Priority"}
        ]
    }
    return mock_resp


@pytest.fixture
def sample_iteration_data():
    """Sample iteration data for testing."""
    return {
        "TEST_PROJECT": {
            "iterations": [
                {
                    "filename": "TEST_PROJECT_iteration_20230501_120000.json",
                    "timestamp": "20230501_120000",
                    "field": "priority",
                    "predictions": [
                        {"issue_key": "TEST-1", "predicted_value": "High", "confidence": 0.95}
                    ]
                }
            ],
            "totals": {
                "total_predictions": 1,
                "high_confidence": 1
            }
        }
    }


@pytest.fixture
def sample_decision_tree():
    """Sample decision tree data for testing."""
    return {
        "name": "Test Tree",
        "description": "A test decision tree",
        "nodes": [
            {
                "id": "root",
                "type": "question",
                "question": "What is the priority?",
                "options": ["High", "Medium", "Low"]
            }
        ]
    }


@pytest.fixture
def mock_file_manager_data():
    """Mock file manager data for testing."""
    return {
        "current_files": [
            {"name": "test1.json", "size": 1024, "modified": "2023-05-01"},
            {"name": "test2.json", "size": 2048, "modified": "2023-05-02"}
        ],
        "cached_files": {
            "predictions": ["pred1.json", "pred2.json"],
            "ml_models": ["model1.pkl", "model2.pkl"],
            "iterations": ["iter1.json", "iter2.json"]
        },
        "timestamp_folders": ["PROJECT_20230501_120000", "PROJECT_20230502_130000"]
    }


# Mock patches for external dependencies
@pytest.fixture(autouse=True)
def mock_external_dependencies():
    """
    Prevent real HTTP requests during tests.
    Tests that need specific HTTP responses must set up their own mocks
    via @patch decorators (which override these defaults).
    NOTE: os.makedirs is NOT mocked here so directory creation logic is exercised.
    The pytest_sessionfinish cleanup removes any files/dirs created during tests.
    """
    with patch('requests.get') as mock_get, \
         patch('requests.post') as mock_post:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {}
        mock_get.return_value.ok = True
        mock_get.return_value.text = '{}'
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {}
        mock_post.return_value.ok = True
        mock_post.return_value.text = '{}'
        yield


@pytest.fixture
def mock_jira_metadata():
    """
    Mock all jira_client metadata functions at their usage site in jira_routes.
    Returns a dict of mock objects keyed by function name for per-test customization.
    """
    with patch('web.routes.jira_routes.fetch_jira_fields') as m_fields, \
         patch('web.routes.jira_routes.fetch_projects') as m_projects, \
         patch('web.routes.jira_routes.extract_custom_fields_mapping') as m_custom, \
         patch('web.routes.jira_routes.fetch_users') as m_users, \
         patch('web.routes.jira_routes.fetch_components_priorities_labels') as m_comp, \
         patch('web.routes.jira_routes.fetch_issue_types') as m_types:

        # Default return values matching real function signatures
        m_fields.return_value = [
            {"id": "priority", "name": "Priority"},
            {"id": "components", "name": "Components"},
            {"id": "labels", "name": "Labels"},
            {"id": "customfield_10014", "name": "Epic Link"}
        ]
        m_projects.return_value = [{"key": "TEST", "name": "Test Project"}]
        m_custom.return_value = {"customfield_10014": "epic_link"}
        m_users.return_value = None
        m_comp.return_value = None
        m_types.return_value = [{"name": "Bug"}, {"name": "Story"}]

        yield {
            'fetch_jira_fields': m_fields,
            'fetch_projects': m_projects,
            'extract_custom_fields_mapping': m_custom,
            'fetch_users': m_users,
            'fetch_components_priorities_labels': m_comp,
            'fetch_issue_types': m_types,
        }


def pytest_sessionfinish(session, exitstatus):
    """
    Pytest session hook called at the end of test execution.
    Automatically clears all cache files created during testing using the comprehensive cache clearing system.
    """
    print("\n[INFO] Cleaning up test-generated cache files...")
    
    try:
        # Import utils_pkg to access the comprehensive cache clearing functionality
        import utils_pkg as utils
        
        # Get all clearable items using the same system as the file manager
        items = utils.get_all_clearable_items()
        
        if not items:
            print("   No cache items found to clean.")
            return
        
        cleaned_files = 0
        errors = []
        
        # Clear all cache items using the same logic as the /clear_all_cache endpoint
        for item in items:
            target = item.get("path", "")
            is_dir = item.get("is_dir", False)
            
            if not target or not os.path.exists(target):
                continue
                
            try:
                if is_dir:
                    shutil.rmtree(target)
                    print(f"   Removed directory: {item.get('label', target)}")
                else:
                    os.remove(target)
                    print(f"   Removed file: {item.get('label', target)}")
                cleaned_files += 1
            except Exception as e:
                errors.append(f"{target}: {e}")
                print(f"   Error removing {item.get('label', target)}: {e}")
        
        # Also clean up any remaining test artifacts that might not be in the cacheable folders
        test_artifacts = [
            'jira_components_priorities.json',
            'jira_users.json'
        ]
        
        for artifact in test_artifacts:
            artifact_path = os.path.join(os.getcwd(), artifact)
            if os.path.exists(artifact_path):
                try:
                    os.remove(artifact_path)
                    cleaned_files += 1
                    print(f"   Removed artifact: {artifact}")
                except Exception as e:
                    errors.append(f"{artifact}: {e}")
                    print(f"   Error removing artifact {artifact}: {e}")
        
        if errors:
            print(f"[WARN] Cache cleanup completed with {len(errors)} errors.")
            for error in errors:
                print(f"     {error}")
        else:
            print(f"[OK] Cache cleanup completed. Removed {cleaned_files} files/directories.")
            
    except ImportError as e:
        print(f"[WARN] Could not import utils_pkg for cache clearing: {e}")
        print("   Falling back to basic cleanup...")
        # Fallback to basic cleanup if utils_pkg is not available
        _basic_cache_cleanup()
    except Exception as e:
        print(f"[WARN] Cache cleanup failed: {e}")


def _basic_cache_cleanup():
    """
    Fallback basic cache cleanup if the comprehensive system fails.
    """
    cache_dirs = [
        'databases',
        'iterations', 
        'predictions',
        'ml_models',
        'updated',
        'questionnaires',
        'tree_history_logs'
    ]
    
    cleaned_files = 0
    for cache_dir in cache_dirs:
        cache_path = os.path.join(os.getcwd(), cache_dir)
        if os.path.exists(cache_path):
            for item in os.listdir(cache_path):
                item_path = os.path.join(cache_path, item)
                try:
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                        cleaned_files += 1
                        print(f"   Removed: {item}")
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        cleaned_files += 1
                        print(f"   Removed directory: {item}")
                except Exception as e:
                    print(f"   Error removing {item}: {e}")
    
    print(f"[OK] Basic cache cleanup completed. Removed {cleaned_files} files/directories.")


def pytest_sessionstart(session):
    """
    Pytest session hook called at the beginning of test execution.
    """
    print("[INFO] Starting test suite with automatic cache cleanup enabled")
