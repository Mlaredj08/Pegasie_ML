"""
Tests for iteration routes.
"""
import json
import os
import pytest
from unittest.mock import patch, Mock

from tests.test_utils import (
    create_test_iteration_content, create_test_consolidated_content,
    create_temp_json_file, assert_json_response
)


class TestIterationRoutes:
    """Test cases for iteration routes."""

    @patch('web.routes.iteration_routes.consolidate_iterations_data')
    def test_consolidate_iterations_success(self, mock_consolidate, auth_client):
        """Test POST /consolidate_iterations with valid data."""
        mock_consolidate.return_value = (
            {"success": True, "filename": "test_consolidated.json", "predictions_by_issuetype": {}, "total_issue_keys": 0, "content_changed": True},
            200
        )
        
        response = auth_client.post('/consolidate_iterations',
                                  json={
                                      "project": "TEST_PROJECT",
                                      "output_folder": "TEST_PROJECT_20230501_120000"
                                  })
        
        assert_json_response(response, 200)
        data = json.loads(response.data)
        assert data['success'] is True

    @patch('web.routes.iteration_routes.consolidate_iterations_data')
    def test_consolidate_iterations_with_project_override(self, mock_consolidate, auth_client):
        """Test POST /consolidate_iterations with project override."""
        mock_consolidate.return_value = ({"success": True, "filename": "test.json", "predictions_by_issuetype": {}, "total_issue_keys": 0, "content_changed": True}, 200)
        
        response = auth_client.post('/consolidate_iterations',
                                  json={
                                      "project": "OVERRIDE_PROJECT",
                                      "output_folder": "TEST_PROJECT_20230501_120000"
                                  })
        
        assert_json_response(response, 200)
        mock_consolidate.assert_called_once()
        call_args = mock_consolidate.call_args
        # Check that project_override is passed correctly
        assert call_args.kwargs.get('project_override') == "OVERRIDE_PROJECT"

    @patch('web.routes.iteration_routes.consolidate_iterations_data')
    def test_consolidate_iterations_with_output_folder(self, mock_consolidate, auth_client):
        """Test POST /consolidate_iterations with output_folder parameter."""
        mock_consolidate.return_value = ({"success": True, "filename": "test.json", "predictions_by_issuetype": {}, "total_issue_keys": 0, "content_changed": True}, 200)
        
        response = auth_client.post('/consolidate_iterations',
                                  json={
                                      "project": "TEST_PROJECT",
                                      "output_folder": "TEST_PROJECT_20230501_120000"
                                  })
        
        assert_json_response(response, 200)
        mock_consolidate.assert_called_once()
        call_kwargs = mock_consolidate.call_args[1]
        assert call_kwargs['output_folder'] == "TEST_PROJECT_20230501_120000"

    @patch('web.routes.iteration_routes.consolidate_iterations_data')
    def test_consolidate_iterations_empty_json(self, mock_consolidate, auth_client):
        """Test POST /consolidate_iterations with empty JSON."""
        mock_consolidate.return_value = ({"success": True, "filename": "test.json", "predictions_by_issuetype": {}, "total_issue_keys": 0, "content_changed": True}, 200)
        
        response = auth_client.post('/consolidate_iterations', json={})
        
        assert_json_response(response, 200)
        mock_consolidate.assert_called_once()
        call_kwargs = mock_consolidate.call_args[1]
        assert call_kwargs.get('project_override') is None
        assert call_kwargs.get('output_folder') == ""

    @patch('web.routes.iteration_routes.consolidate_iterations_data')
    def test_consolidate_iterations_with_model_config(self, mock_consolidate, auth_client):
        """Test POST /consolidate_iterations passes model_config."""
        mock_consolidate.return_value = ({"success": True, "filename": "test.json", "predictions_by_issuetype": {}, "total_issue_keys": 0, "content_changed": True}, 200)
        
        response = auth_client.post('/consolidate_iterations',
                                  json={"project": "TEST_PROJECT"})
        
        assert_json_response(response, 200)
        mock_consolidate.assert_called_once()
        call_args = mock_consolidate.call_args
        # First argument should be model_config (may be None in tests)
        assert len(call_args[0]) >= 1

    @patch('os.path.exists')
    @patch('os.remove')
    def test_delete_iteration_file_success(self, mock_remove, mock_exists, auth_client):
        """Test POST /delete_iteration_file with valid file."""
        mock_exists.return_value = True
        
        response = auth_client.post('/delete_iteration_file',
                                  json={"filename": "TEST_PROJECT_iteration_20230501_120000.json"})
        
        assert_json_response(response, 200)
        data = json.loads(response.data)
        assert data['success'] is True
        mock_remove.assert_called_once()

    def test_delete_iteration_file_missing_filename(self, auth_client):
        """Test POST /delete_iteration_file without filename."""
        response = auth_client.post('/delete_iteration_file', json={})
        
        assert_json_response(response, 400)
        data = json.loads(response.data)
        assert 'error' in data
        assert 'filename' in data['error']

    @patch('os.path.exists')
    def test_delete_iteration_file_not_found(self, mock_exists, auth_client):
        """Test POST /delete_iteration_file with non-existent file."""
        mock_exists.return_value = False
        
        response = auth_client.post('/delete_iteration_file',
                                  json={"filename": "nonexistent.json"})
        
        assert_json_response(response, 404)
        data = json.loads(response.data)
        assert 'error' in data

    @patch('os.path.exists')
    @patch('os.remove')
    def test_delete_iteration_file_with_full_path(self, mock_remove, mock_exists, auth_client):
        """Test POST /delete_iteration_file with full path."""
        mock_exists.return_value = True
        
        full_path = "/path/to/iterations/TEST_PROJECT_iteration_20230501_120000.json"
        response = auth_client.post('/delete_iteration_file',
                                  json={"filename": full_path})
        
        # Should return 400 due to security check for path traversal
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    @patch('os.path.exists')
    @patch('os.remove')
    def test_delete_iteration_file_with_timestamp_format(self, mock_remove, mock_exists, auth_client):
        """Test POST /delete_iteration_file with timestamp format filename."""
        mock_exists.return_value = True
        
        response = auth_client.post('/delete_iteration_file',
                                  json={"filename": "TEST_PROJECT_20230501_120000_iteration_20230502_130000.json"})
        
        assert_json_response(response, 200)
        mock_remove.assert_called_once()

    @patch('os.path.exists')
    @patch('os.remove')
    def test_delete_iteration_file_security_check(self, mock_remove, mock_exists, auth_client):
        """Test POST /delete_iteration_file rejects path traversal attempts."""
        mock_exists.return_value = True

        # Route checks for '..' and '/' in filename and returns 400
        response = auth_client.post('/delete_iteration_file',
                                  json={"filename": "../../../etc/passwd"})

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        mock_remove.assert_not_called()

    @patch('web.routes.iteration_routes.consolidate_iterations_data')
    def test_consolidate_iterations_with_special_characters(self, mock_consolidate, auth_client):
        """Test POST /consolidate_iterations with special characters in project name."""
        mock_consolidate.return_value = ({"success": True, "filename": "test.json", "predictions_by_issuetype": {}, "total_issue_keys": 0, "content_changed": True}, 200)
        
        response = auth_client.post('/consolidate_iterations',
                                  json={
                                      "project": "TEST-PROJECT_2023",
                                      "output_folder": "TEST-PROJECT_2023_20230501_120000"
                                  })
        
        assert_json_response(response, 200)
        mock_consolidate.assert_called_once()

    @patch('web.routes.iteration_routes.consolidate_iterations_data')
    def test_consolidate_iterations_very_long_project_name(self, mock_consolidate, auth_client):
        """Test POST /consolidate_iterations with very long project name."""
        mock_consolidate.return_value = ({"success": True, "filename": "test.json", "predictions_by_issuetype": {}, "total_issue_keys": 0, "content_changed": True}, 200)
        
        long_project = "A" * 1000  # Very long project name
        response = auth_client.post('/consolidate_iterations',
                                  json={"project": long_project})
        
        assert_json_response(response, 200)

    @patch('web.routes.iteration_routes.consolidate_iterations_data')
    def test_consolidate_iterations_with_unicode(self, mock_consolidate, auth_client):
        """Test POST /consolidate_iterations with unicode characters."""
        mock_consolidate.return_value = ({"success": True, "filename": "test.json", "predictions_by_issuetype": {}, "total_issue_keys": 0, "content_changed": True}, 200)
        
        response = auth_client.post('/consolidate_iterations',
                                  json={"project": "测试项目"})
        
        assert_json_response(response, 200)

    @patch('web.routes.iteration_routes.consolidate_iterations_data')
    def test_consolidate_iterations_sequential_batch(self, mock_consolidate, auth_client):
        """Test POST /consolidate_iterations handles multiple sequential requests."""
        mock_consolidate.return_value = ({"success": True, "filename": "test.json", "predictions_by_issuetype": {}, "total_issue_keys": 0, "content_changed": True}, 200)

        # Send 5 sequential requests (Flask test client is synchronous)
        responses = []
        for i in range(5):
            response = auth_client.post('/consolidate_iterations',
                                      json={"project": f"PROJECT_{i}"})
            responses.append(response)

        # All should succeed
        for response in responses:
            assert_json_response(response, 200)
        assert mock_consolidate.call_count == 5

    @patch('web.routes.iteration_routes.consolidate_iterations_data')
    def test_consolidate_iterations_empty_output_folder(self, mock_consolidate, auth_client):
        """Test POST /consolidate_iterations with empty output_folder."""
        mock_consolidate.return_value = ({"success": True, "filename": "test.json", "predictions_by_issuetype": {}, "total_issue_keys": 0, "content_changed": True}, 200)
        
        response = auth_client.post('/consolidate_iterations',
                                  json={
                                      "project": "TEST_PROJECT",
                                      "output_folder": ""
                                  })
        
        assert_json_response(response, 200)
        mock_consolidate.assert_called_once()
        call_kwargs = mock_consolidate.call_args[1]
        assert call_kwargs['output_folder'] == ""

    @patch('web.routes.iteration_routes.consolidate_iterations_data')
    def test_consolidate_iterations_null_output_folder(self, mock_consolidate, auth_client):
        """Test POST /consolidate_iterations with null output_folder."""
        mock_consolidate.return_value = ({"success": True, "filename": "test.json", "predictions_by_issuetype": {}, "total_issue_keys": 0, "content_changed": True}, 200)
        
        response = auth_client.post('/consolidate_iterations',
                                  json={
                                      "project": "TEST_PROJECT",
                                      "output_folder": None
                                  })
        
        assert_json_response(response, 200)
        mock_consolidate.assert_called_once()
        call_kwargs = mock_consolidate.call_args[1]
        # JSON null becomes None in Python, but the route converts it to empty string
        assert call_kwargs['output_folder'] == ""
