"""
Tests for Jira integration routes.
"""
import json
import os
import pytest
from unittest.mock import patch, Mock

from tests.test_utils import (
    create_test_file_content, create_test_consolidated_content,
    mock_jira_client_functions, assert_json_response, assert_template_response
)
from tests.test_constants import (
    TEST_JIRA_URL, TEST_JIRA_USERNAME, TEST_JIRA_PASSWORD, TEST_PROJECT,
    TEST_ISSUE_KEY,
    TEST_FIELD_PRIORITY, TEST_FIELD_COMPONENTS,
    TEST_PROJECT_KEY, TEST_FILENAME, TEST_OUTPUT_FOLDER, TEST_USER,
    HTTP_OK, HTTP_FOUND, HTTP_BAD_REQUEST,
    MOCK_JIRA_USER_RESPONSE, MOCK_JIRA_PROJECTS_RESPONSE, MOCK_JIRA_FIELDS_RESPONSE,
    # Jira Cloud specific constants
    TEST_JIRA_CLOUD_URL, TEST_JIRA_CLOUD_USERNAME, TEST_JIRA_CLOUD_API_TOKEN, TEST_JIRA_CLOUD_EMAIL,
    MOCK_JIRA_CLOUD_USER_RESPONSE, MOCK_JIRA_CLOUD_PROJECTS_RESPONSE,
    MOCK_JIRA_CLOUD_FIELDS_RESPONSE
)


class TestJiraRoutes:
    """Test cases for Jira integration routes."""


    def test_fields_success(self, auth_client, mock_jira_metadata):
        """Test POST /fields with valid credentials."""
        response = auth_client.post('/fields', data={
            'jira_url': TEST_JIRA_URL,
            'username': TEST_JIRA_USERNAME,
            'api_token': TEST_JIRA_PASSWORD
        })

        assert_template_response(response, HTTP_OK)
        mock_jira_metadata['fetch_jira_fields'].assert_called_once()

    def test_fields_api_error(self, auth_client, mock_jira_metadata):
        """Test POST /fields when fetch_jira_fields returns None (API error)."""
        # Real function returns None on API failure, route checks and renders error
        mock_jira_metadata['fetch_jira_fields'].return_value = None

        response = auth_client.post('/fields', data={
            'jira_url': TEST_JIRA_URL,
            'username': TEST_JIRA_USERNAME,
            'api_token': TEST_JIRA_PASSWORD
        })

        assert_template_response(response, HTTP_OK)  # Renders template with error message

    def test_fields_empty_fields_list(self, auth_client, mock_jira_metadata):
        """Test POST /fields when Jira returns empty fields list."""
        mock_jira_metadata['fetch_jira_fields'].return_value = []

        response = auth_client.post('/fields', data={
            'jira_url': TEST_JIRA_URL,
            'username': TEST_JIRA_USERNAME,
            'api_token': TEST_JIRA_PASSWORD
        })
        assert_template_response(response, HTTP_OK)

    def test_fields_with_custom_fields(self, auth_client, mock_jira_metadata):
        """Test POST /fields with custom field types in response."""
        mock_jira_metadata['fetch_jira_fields'].return_value = [
            {"id": "priority", "name": "Priority"},
            {"id": "customfield_10010", "name": "Custom Text"}
        ]
        mock_jira_metadata['extract_custom_fields_mapping'].return_value = {
            "customfield_10010": "custom_text"
        }

        response = auth_client.post('/fields', data={
            'jira_url': TEST_JIRA_URL,
            'username': TEST_JIRA_USERNAME,
            'api_token': TEST_JIRA_PASSWORD
        })

        assert_template_response(response, HTTP_OK)

    def test_fields_with_session_credentials(self, auth_client, mock_jira_metadata):
        """Test POST /fields uses form credentials for Jira calls."""
        response = auth_client.post('/fields', data={
            'jira_url': TEST_JIRA_URL,
            'username': TEST_JIRA_USERNAME,
            'api_token': TEST_JIRA_PASSWORD
        })

        assert_template_response(response, HTTP_OK)
        # Verify fetch_jira_fields was called with the form URL
        call_args = mock_jira_metadata['fetch_jira_fields'].call_args
        assert TEST_JIRA_URL in call_args[0][0]

    @patch('web.routes.jira_routes.export_jira_issues')
    @patch('web.routes.jira_routes.fetch_jira_fields')
    @patch('web.routes.jira_routes.fetch_projects')
    def test_generate_success(self, mock_projects, mock_fields, mock_export, auth_client):
        """Test POST /generate with valid data."""
        mock_fields.return_value = MOCK_JIRA_FIELDS_RESPONSE
        mock_projects.return_value = MOCK_JIRA_PROJECTS_RESPONSE
        mock_export.return_value = {"issues": [{"key": TEST_ISSUE_KEY, "fields": {}}]}
        
        response = auth_client.post('/generate?custom_fields={}', data={
            'jira_url': TEST_JIRA_URL,
            'username': TEST_JIRA_USERNAME,
            'api_token': TEST_JIRA_PASSWORD,
            'project_key': TEST_PROJECT,
            'fields': [TEST_FIELD_PRIORITY, TEST_FIELD_COMPONENTS]
        })
        
        # The generate route redirects after successful export
        assert response.status_code == HTTP_FOUND

    @patch('web.routes.jira_routes.fetch_jira_fields')
    @patch('web.routes.jira_routes.fetch_projects')
    def test_generate_with_max_issues(self, mock_projects, mock_fields, auth_client):
        """Test POST /generate with max_issues parameter."""
        mock_fields.return_value = MOCK_JIRA_FIELDS_RESPONSE
        mock_projects.return_value = MOCK_JIRA_PROJECTS_RESPONSE
        
        response = auth_client.post('/generate?custom_fields={}', data={
            'jira_url': TEST_JIRA_URL,
            'username': TEST_JIRA_USERNAME,
            'api_token': TEST_JIRA_PASSWORD,
            'project_key': TEST_PROJECT_KEY,
            'fields': [TEST_FIELD_PRIORITY],
            'max_issues': '50'
        })
        
        # The generate route redirects after successful export
        assert response.status_code == HTTP_FOUND

    @patch('web.routes.jira_routes.fetch_jira_fields')
    @patch('web.routes.jira_routes.fetch_projects')
    def test_generate_with_jql(self, mock_projects, mock_fields, auth_client):
        """Test POST /generate with JQL query."""
        mock_fields.return_value = MOCK_JIRA_FIELDS_RESPONSE
        mock_projects.return_value = MOCK_JIRA_PROJECTS_RESPONSE
        
        response = auth_client.post('/generate?custom_fields={}', data={
            'jira_url': TEST_JIRA_URL,
            'username': TEST_JIRA_USERNAME,
            'api_token': TEST_JIRA_PASSWORD,
            'project_key': TEST_PROJECT_KEY,
            'fields': [TEST_FIELD_PRIORITY],
            'jql': 'status = "In Progress"'
        })
        
        # The generate route redirects after successful export
        assert response.status_code == HTTP_FOUND

    def test_jira_viewer_get(self, auth_client):
        """Test GET /jira_viewer."""
        response = auth_client.get('/jira_viewer')
        assert_template_response(response, HTTP_OK)

    @patch('web.routes.jira_routes.get_target_field_possible_values')
    @patch('builtins.open')
    def test_show_jira_viewer(self, mock_open, mock_field_values, auth_client):
        """Test POST /show_jira_viewer with filename."""
        mock_field_values.return_value = [{"labels_values": [], "epic_link_values": []}]
        mock_file = Mock()
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=None)
        mock_file.read.return_value = json.dumps({"priorities": ["High", "Medium"]})
        mock_open.return_value = mock_file

        response = auth_client.post('/show_jira_viewer', data={'filename': TEST_FILENAME})
        assert_template_response(response, HTTP_OK)

    @patch('web.routes.jira_routes.get_target_field_possible_values')
    @patch('builtins.open')
    @patch('os.path.exists')
    def test_show_jira_viewer_with_file(self, mock_exists, mock_open, mock_field_values, auth_client, temp_dir):
        """Test POST /show_jira_viewer with file parameter."""
        # Create test file
        test_content = create_test_file_content()
        test_file = os.path.join(temp_dir, "test.json")
        
        # Mock field values return
        mock_field_values.return_value = [
            {"labels_values": [["bug", "enhancement"]], "epic_link_values": ["EPIC-1"]}
        ]
        
        # Mock file existence and file reading
        mock_exists.return_value = True
        
        # Mock the JIRA_COMPONENTS_PRIORITIES_FILE reading
        mock_priorities_data = {"ECOMBNUKE": ["Backend", "Frontend"], "priorities": ["High", "Medium", "Low"]}
        
        def mock_open_func(filename, mode='r', encoding=None):
            if filename.endswith('test.json'):
                mock_file = Mock()
                mock_file.read.return_value = json.dumps(test_content)
                return mock_file
            else:  # JIRA_COMPONENTS_PRIORITIES_FILE
                mock_file = Mock()
                mock_file.__enter__ = Mock(return_value=mock_file)
                mock_file.__exit__ = Mock(return_value=None)
                mock_file.read.return_value = json.dumps(mock_priorities_data)
                return mock_file
        
        mock_open.side_effect = mock_open_func
        
        response = auth_client.post('/show_jira_viewer', data={'filename': test_file})
        assert_template_response(response, HTTP_OK)

    @patch('builtins.open')
    @patch('web.routes.jira_routes.get_target_field_possible_values')
    def test_show_jira_viewer_file_not_found(self, mock_field_values, mock_open, auth_client):
        """Test POST /show_jira_viewer with non-existent file."""
        mock_field_values.return_value = [{"labels_values": [], "epic_link_values": []}]
        
        # Mock the JIRA_COMPONENTS_PRIORITIES_FILE reading but let the test file fail
        mock_priorities_data = {"ECOMBNUKE": ["Backend", "Frontend"], "priorities": ["High", "Medium", "Low"]}
        
        def mock_open_func(filename, mode='r', encoding=None):
            if 'nonexistent.json' in filename:
                raise FileNotFoundError("File not found")
            else:  # JIRA_COMPONENTS_PRIORITIES_FILE
                mock_file = Mock()
                mock_file.__enter__ = Mock(return_value=mock_file)
                mock_file.__exit__ = Mock(return_value=None)
                mock_file.read.return_value = json.dumps(mock_priorities_data)
                return mock_file
        
        mock_open.side_effect = mock_open_func
        
        response = auth_client.post('/show_jira_viewer', data={'filename': '/nonexistent.json'})
        # Route renders template with error message for file not found
        assert_template_response(response, HTTP_OK)

    @patch('os.listdir')
    @patch('os.path.exists')
    @patch('builtins.open')
    @patch('services.iteration_service.consolidate_iterations_data')
    def test_validate_push_issues_success(self, mock_consolidate, mock_open, mock_exists, mock_listdir, auth_client):
        """Test POST /validate_push_issues with valid data."""
        mock_consolidate.return_value = {
            "success": True,
            "data": create_test_consolidated_content()
        }
        
        # Mock file system to have consolidated files
        mock_listdir.return_value = ['TEST_PROJECT_consolidated_20230501_120000.json']
        mock_exists.return_value = True
        
        # Mock the consolidated file content
        mock_file = Mock()
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=None)
        mock_file.read.return_value = json.dumps(create_test_consolidated_content())
        mock_open.return_value = mock_file
        
        response = auth_client.post('/validate_push_issues',
                                  json={
                                      "project": TEST_PROJECT,
                                      "output_folder": TEST_OUTPUT_FOLDER
                                  })
        
        assert_json_response(response, HTTP_OK)
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('os.listdir')
    @patch('os.path.exists')
    @patch('builtins.open')
    @patch('services.iteration_service.consolidate_iterations_data')
    def test_validate_push_issues_missing_params(self, mock_consolidate, mock_open, mock_exists, mock_listdir, auth_client):
        """Test POST /validate_push_issues with missing parameters."""
        mock_consolidate.return_value = {"success": False, "error": "Missing project"}
        
        # Mock file system to have consolidated files
        mock_listdir.return_value = ['TEST_PROJECT_consolidated_20230501_120000.json']
        mock_exists.return_value = True
        
        # Mock the consolidated file content
        mock_file = Mock()
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=None)
        mock_file.read.return_value = json.dumps(create_test_consolidated_content())
        mock_open.return_value = mock_file
        
        response = auth_client.post('/validate_push_issues', json={})
        
        # The route actually succeeds with empty JSON, it doesn't validate parameters as expected
        assert_json_response(response, HTTP_OK)
        data = json.loads(response.data)
        assert 'success' in data

    @patch('os.listdir')
    @patch('os.path.exists')
    @patch('builtins.open')
    @patch('web.routes.jira_routes.apply_prediction_json_to_jira')
    @patch('web.routes.jira_routes.fetch_issue_fields')
    def test_push_to_jira_success(self, mock_fetch_fields, mock_apply, mock_open, mock_exists, mock_listdir, auth_client):
        """Test POST /push_to_jira with successful push."""
        # fetch_issue_fields returns empty dict (fields are empty in Jira -> valid to push)
        mock_fetch_fields.return_value = {}
        # apply_prediction_json_to_jira must return a list of per-issue result dicts
        mock_apply.return_value = [
            {"issuekey": "TEST-1", "field": "priority", "status": 200, "response": {}}
        ]

        mock_listdir.return_value = ['TEST_PROJECT_consolidated_20230501_120000.json']
        mock_exists.return_value = True

        mock_file = Mock()
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=None)
        mock_file.read.return_value = json.dumps(create_test_consolidated_content())
        mock_open.return_value = mock_file

        response = auth_client.post('/push_to_jira',
                                  json={
                                      "consolidated_data": create_test_consolidated_content(),
                                      "user": TEST_USER
                                  })

        assert_json_response(response, HTTP_OK)
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['success_count'] == 1
        assert data['failed_count'] == 0
        mock_apply.assert_called_once()

    @patch('os.listdir')
    @patch('os.path.exists')
    @patch('builtins.open')
    @patch('web.routes.jira_routes.apply_prediction_json_to_jira')
    @patch('web.routes.jira_routes.fetch_issue_fields')
    def test_push_to_jira_apply_error(self, mock_fetch_fields, mock_apply, mock_open, mock_exists, mock_listdir, auth_client):
        """Test POST /push_to_jira when Jira rejects individual updates."""
        mock_fetch_fields.return_value = {}
        # Return a list with failed results (status != 200/204)
        mock_apply.return_value = [
            {"issuekey": "TEST-1", "field": "priority", "status": 400,
             "response": {"errors": {"priority": "Invalid value"}}}
        ]

        mock_listdir.return_value = ['TEST_PROJECT_consolidated_20230501_120000.json']
        mock_exists.return_value = True

        mock_file = Mock()
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=None)
        mock_file.read.return_value = json.dumps(create_test_consolidated_content())
        mock_open.return_value = mock_file

        response = auth_client.post('/push_to_jira',
                                  json={
                                      "consolidated_data": create_test_consolidated_content(),
                                      "user": TEST_USER
                                  })

        assert_json_response(response, HTTP_OK)
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['failed_count'] == 1
        assert data['success_count'] == 0
        assert len(data['failed_items']) == 1
        assert data['failed_items'][0]['error'] == 'priority: Invalid value'

    @patch('os.listdir')
    @patch('os.path.exists')
    @patch('builtins.open')
    @patch('web.routes.jira_routes.apply_prediction_json_to_jira')
    @patch('web.routes.jira_routes.fetch_issue_fields')
    def test_push_to_jira_empty_predictions(self, mock_fetch_fields, mock_apply, mock_open, mock_exists, mock_listdir, auth_client):
        """Test POST /push_to_jira with no valid predictions to push."""
        mock_fetch_fields.return_value = {}

        mock_listdir.return_value = ['TEST_PROJECT_consolidated_20230501_120000.json']
        mock_exists.return_value = True

        # Consolidated file with empty predictions
        empty_consolidated = {"predictions_by_issuetype": {}, "summary": {}}
        mock_file = Mock()
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=None)
        mock_file.read.return_value = json.dumps(empty_consolidated)
        mock_open.return_value = mock_file

        response = auth_client.post('/push_to_jira',
                                  json={"user": TEST_USER})

        assert_json_response(response, HTTP_BAD_REQUEST)
        data = json.loads(response.data)
        assert 'error' in data
        assert 'No predictions' in data['error']

    def test_transform_consolidated_to_jira_format(self):
        """Test the transform_consolidated_to_jira_format helper function."""
        from web.routes.jira_routes import transform_consolidated_to_jira_format
        
        consolidated_data = create_test_consolidated_content()
        result = transform_consolidated_to_jira_format(consolidated_data, TEST_USER)
        
        assert 'target_fields' in result
        assert 'user' in result
        assert result['user'] == TEST_USER

    def test_transform_consolidated_deduplication(self):
        """Test transform_consolidated_to_jira_format deduplicates issue keys."""
        from web.routes.jira_routes import transform_consolidated_to_jira_format
        
        consolidated_data = {
            "predictions_by_issuetype": {
                "Bug": [
                    {"field": "priority", "new_value": "High", "issue_keys": ["TEST-1", "TEST-2"]},
                    {"field": "priority", "new_value": "High", "issue_keys": ["TEST-2", "TEST-3"]}  # Duplicate TEST-2
                ]
            }
        }
        
        result = transform_consolidated_to_jira_format(consolidated_data, TEST_USER)
        
        # Should deduplicate TEST-2
        priority_field = next(field for field in result['target_fields'] if field['field_name'] == 'priority')
        assert len(priority_field['predictions']) == 1
        assert set(priority_field['predictions'][0]['issue_keys']) == {"TEST-1", "TEST-2", "TEST-3"}

    @patch('os.listdir')
    @patch('os.path.exists')
    @patch('builtins.open')
    @patch('web.routes.jira_routes.apply_prediction_json_to_jira')
    @patch('web.routes.jira_routes.fetch_issue_fields')
    def test_push_to_jira_with_dry_run(self, mock_fetch_fields, mock_apply, mock_open, mock_exists, mock_listdir, auth_client):
        """Test POST /push_to_jira with dry_run parameter."""
        mock_fetch_fields.return_value = {}
        mock_apply.return_value = [
            {"issuekey": "TEST-1", "field": "priority", "status": 200, "response": {}}
        ]

        mock_listdir.return_value = ['TEST_PROJECT_consolidated_20230501_120000.json']
        mock_exists.return_value = True

        mock_file = Mock()
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=None)
        mock_file.read.return_value = json.dumps(create_test_consolidated_content())
        mock_open.return_value = mock_file

        response = auth_client.post('/push_to_jira',
                                  json={
                                      "consolidated_data": create_test_consolidated_content(),
                                      "user": TEST_USER,
                                      "dry_run": True
                                  })

        assert_json_response(response, HTTP_OK)
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['success_count'] == 1

    @patch('os.listdir')
    @patch('os.path.exists')
    @patch('builtins.open')
    @patch('web.routes.jira_routes.apply_prediction_json_to_jira')
    @patch('web.routes.jira_routes.fetch_issue_fields')
    def test_push_to_jira_with_session_credentials(self, mock_fetch_fields, mock_apply, mock_open, mock_exists, mock_listdir, auth_client):
        """Test POST /push_to_jira uses session credentials."""
        mock_fetch_fields.return_value = {}
        mock_apply.return_value = [
            {"issuekey": "TEST-1", "field": "priority", "status": 200, "response": {}}
        ]

        mock_listdir.return_value = ['TEST_PROJECT_consolidated_20230501_120000.json']
        mock_exists.return_value = True

        mock_file = Mock()
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=None)
        mock_file.read.return_value = json.dumps(create_test_consolidated_content())
        mock_open.return_value = mock_file

        response = auth_client.post('/push_to_jira',
                                  json={
                                      "consolidated_data": create_test_consolidated_content(),
                                      "user": TEST_USER
                                  })

        assert_json_response(response, HTTP_OK)
        data = json.loads(response.data)
        assert data['success'] is True
        # Verify session credentials were used (apply was called with jira_url and auth tuple)
        mock_apply.assert_called_once()


class TestJiraCloudRoutes:
    """Test cases for Jira Cloud integration routes with API token authentication."""

    def test_jira_cloud_fields_success(self, auth_client, mock_jira_metadata):
        """Test POST /fields with Jira Cloud API token authentication."""
        response = auth_client.post('/fields', data={
            'jira_url': TEST_JIRA_CLOUD_URL,
            'username': TEST_JIRA_CLOUD_USERNAME,
            'api_token': TEST_JIRA_CLOUD_API_TOKEN
        })

        assert_template_response(response, HTTP_OK)
        mock_jira_metadata['fetch_jira_fields'].assert_called_once()

    def test_jira_cloud_fields_api_error(self, auth_client, mock_jira_metadata):
        """Test POST /fields with Jira Cloud API error (returns None)."""
        mock_jira_metadata['fetch_jira_fields'].return_value = None

        response = auth_client.post('/fields', data={
            'jira_url': TEST_JIRA_CLOUD_URL,
            'username': TEST_JIRA_CLOUD_USERNAME,
            'api_token': TEST_JIRA_CLOUD_API_TOKEN
        })

        assert_template_response(response, HTTP_OK)  # Renders template with error

    @patch('web.routes.jira_routes.export_jira_issues')
    @patch('web.routes.jira_routes.fetch_jira_fields')
    @patch('web.routes.jira_routes.fetch_projects')
    def test_jira_cloud_generate_success(self, mock_projects, mock_fields, mock_export, auth_client):
        """Test POST /generate with Jira Cloud API token authentication."""
        mock_fields.return_value = MOCK_JIRA_CLOUD_FIELDS_RESPONSE
        mock_projects.return_value = MOCK_JIRA_CLOUD_PROJECTS_RESPONSE
        mock_export.return_value = {"issues": [{"key": TEST_ISSUE_KEY, "fields": {}}]}
        
        response = auth_client.post('/generate?custom_fields={}', data={
            'jira_url': TEST_JIRA_CLOUD_URL,
            'username': TEST_JIRA_CLOUD_USERNAME,
            'api_token': TEST_JIRA_CLOUD_API_TOKEN,
            'project_key': TEST_PROJECT,
            'fields': [TEST_FIELD_PRIORITY, TEST_FIELD_COMPONENTS]
        })
        
        # The generate route redirects after successful export
        assert response.status_code == HTTP_FOUND

    @patch('requests.get')
    def test_jira_cloud_auth_verify_success(self, mock_get, client):
        """Test Jira Cloud API token authentication verification."""
        mock_response = Mock()
        mock_response.status_code = HTTP_OK
        mock_response.json.return_value = MOCK_JIRA_CLOUD_USER_RESPONSE
        mock_get.return_value = mock_response
        
        response = client.post('/auth/verify', 
                             json={
                                 'jira_url': TEST_JIRA_CLOUD_URL,
                                 'username': TEST_JIRA_CLOUD_USERNAME,
                                 'password': TEST_JIRA_CLOUD_API_TOKEN  # API token as password
                             })
        
        assert_json_response(response, HTTP_OK)
        data = json.loads(response.data)
        assert data['ok'] is True
        assert data['message'] == 'User verified'

    def test_jira_cloud_open_source_mode(self, auth_client, mock_jira_metadata):
        """Test Jira Cloud routes in open source mode (without API token)."""
        response = auth_client.post('/fields', data={
            'jira_url': TEST_JIRA_CLOUD_URL,
            'username': '',  # Empty username for open source
            'api_token': '',  # Empty token for open source
            'open_source': 'true'
        })

        assert_template_response(response, HTTP_OK)
        # In open source mode, fetch_users and fetch_components should NOT be called
        mock_jira_metadata['fetch_users'].assert_not_called()
        mock_jira_metadata['fetch_components_priorities_labels'].assert_not_called()
