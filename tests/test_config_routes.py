"""
Tests for configuration and data analysis routes.
"""
import json
import os
import pytest
from unittest.mock import patch, Mock

from tests.test_utils import (
    create_test_file_content, create_temp_json_file, 
    assert_json_response, assert_template_response
)
from tests.test_constants import (
    TEST_PROJECT, TEST_FILENAME, TEST_OUTPUT_FOLDER,
    HTTP_OK,
    TEST_REPORT_BLOCKER_BLOCKED, TEST_REPORT_PARENT_CHILD_PRIORITY,
    TEST_REPORT_PARENT_CHILD_COMPONENTS, TEST_REPORT_INHERITANCE_RULES
)


class TestConfigRoutes:
    """Test cases for configuration and data analysis routes."""

    @patch('os.listdir')
    def test_data_analysis_route(self, mock_listdir, auth_client):
        """Test GET /data_analysis route."""
        mock_listdir.return_value = ['test1.json', 'test2.json', 'non_json.txt']
        
        response = auth_client.get('/data_analysis')
        assert_template_response(response, HTTP_OK)
        assert b'test1.json' in response.data
        assert b'test2.json' in response.data

    @patch('os.listdir')
    def test_data_analysis_empty_folder(self, mock_listdir, auth_client):
        """Test GET /data_analysis with empty folder."""
        mock_listdir.return_value = []
        
        response = auth_client.get('/data_analysis')
        assert_template_response(response, HTTP_OK)

    @patch('os.path.exists')
    @patch('builtins.open')
    def test_get_iterations_by_project_success(self, mock_open, mock_exists, auth_client):
        """Test POST /get_iterations_by_project with valid project."""
        mock_exists.return_value = True
        
        # Mock file content
        mock_file = Mock()
        mock_file.read.return_value = json.dumps({
            TEST_PROJECT: {
                "iterations": [
                    {"filename": "iter1.json", "timestamp": "20230501_120000"},
                    {"filename": "iter2.json", "timestamp": "20230502_130000"}
                ],
                "totals": {"total_predictions": 10, "high_confidence": 8}
            }
        })
        mock_open.return_value.__enter__.return_value = mock_file
        
        response = auth_client.post('/get_iterations_by_project',
                                  json={"project": TEST_PROJECT})
        
        assert_json_response(response, HTTP_OK)
        data = json.loads(response.data)
        assert len(data['iterations']) == 2
        assert data['totals']['total_predictions'] == 10

    @patch('os.path.exists')
    def test_get_iterations_by_project_no_file(self, mock_exists, auth_client):
        """Test POST /get_iterations_by_project when traceability file doesn't exist."""
        mock_exists.return_value = False
        
        response = auth_client.post('/get_iterations_by_project',
                             json={"project": TEST_PROJECT})
        
        assert_json_response(response, HTTP_OK)
        data = json.loads(response.data)
        assert data['iterations'] == []
        assert data['totals'] == {}

    @patch('os.path.exists')
    @patch('builtins.open')
    def test_get_iterations_by_project_not_found(self, mock_open, mock_exists, auth_client):
        """Test POST /get_iterations_by_project for non-existent project."""
        mock_exists.return_value = True
        
        mock_file = Mock()
        mock_file.read.return_value = json.dumps({"OTHER_PROJECT": {}})
        mock_open.return_value.__enter__.return_value = mock_file
        
        response = auth_client.post('/get_iterations_by_project',
                             json={"project": TEST_PROJECT})
        
        assert_json_response(response, HTTP_OK)
        data = json.loads(response.data)
        assert data['iterations'] == []
        assert data['totals'] == {}

    @patch('analysis.data_pre_analysis.generate_blocker_blocked_priority_data')
    def test_run_data_analysis_blocker_blocked(self, mock_generate, auth_client, temp_dir):
        """Test POST /run_data_analysis for blocker_blocked_priority report."""
        mock_generate.return_value = "/path/to/output.json"
        
        # Create test database file with correct format
        db_content = create_test_file_content()
        test_filename = f"{TEST_PROJECT}_20230501_120000.json"
        db_path = create_temp_json_file(temp_dir, test_filename, db_content)
        
        with patch('os.path.join', return_value=db_path):
            response = auth_client.post('/run_data_analysis', data={
                'report_type': TEST_REPORT_BLOCKER_BLOCKED,
                'filename': test_filename
            })
        
        assert_template_response(response, HTTP_OK)

    @patch('analysis.data_pre_analysis.generate_parent_children_priority_data')
    def test_run_data_analysis_parent_child_priority(self, mock_generate, auth_client, temp_dir):
        """Test POST /run_data_analysis for parent_child_priority report."""
        mock_generate.return_value = "/path/to/output.json"
        
        db_content = create_test_file_content()
        test_filename = f"{TEST_PROJECT}_20230501_120000.json"
        db_path = create_temp_json_file(temp_dir, test_filename, db_content)
        
        with patch('os.path.join', return_value=db_path):
            response = auth_client.post('/run_data_analysis', data={
                'report_type': TEST_REPORT_PARENT_CHILD_PRIORITY,
                'filename': test_filename
            })
        
        assert_template_response(response, HTTP_OK)

#     @pytest.mark.skip(reason="Test requires complex mocking of analysis functions")
#     def test_run_data_analysis_parent_child_components(self, auth_client, temp_dir):
#         """Test POST /run_data_analysis for parent_child_components report."""
#         # This test is skipped due to complex mocking requirements
#         pass
# 
    @patch('web.routes.config_routes.render_template')
    def test_run_data_analysis_inheritance_rules(self, mock_render, auth_client, temp_dir):
        """Test POST /run_data_analysis for inheritance_rules report."""
        mock_render.return_value = "<html>Mocked template response</html>"
        
        test_filename = f"{TEST_PROJECT}_20230501_120000.json"
        
        response = auth_client.post('/run_data_analysis', data={
            'report_type': TEST_REPORT_INHERITANCE_RULES,
            'filename': test_filename
        })
        
        assert response.status_code == HTTP_OK

#     @pytest.mark.skip(reason="Test requires complex mocking of analysis functions")
#     def test_run_data_analysis_invalid_report_type(self, auth_client):
#         """Test POST /run_data_analysis with invalid report type."""
#         # This test is skipped due to complex mocking requirements
#         pass
# 
#     def test_view_inferred_nonexistent_template(self, auth_client):
#         """Test GET /view/<filename> returns 404 for non-existent template."""
#         response = auth_client.get('/view/nonexistent_template_xyz')
#         assert response.status_code == HTTP_NOT_FOUND
#         # Route appends .html automatically
#         assert b'nonexistent_template_xyz.html' in response.data
# 
#     def test_view_inferred_adds_extension(self, auth_client):
#         """Test GET /view/<filename> adds .html extension and returns 404 for missing template."""
#         response = auth_client.get('/view/definitely_not_a_real_template')
#         assert response.status_code == HTTP_NOT_FOUND
#         assert b'.html' in response.data
# 
    @patch('builtins.open')
    def test_get_json_data_success(self, mock_open, auth_client, temp_dir):
        """Test GET /data/<folder> with valid JSON file."""
        mock_file = Mock()
        mock_file.read.return_value = json.dumps({"key": "value"})
        mock_open.return_value.__enter__.return_value = mock_file
        
        response = auth_client.get(f'/data/test_folder?project={TEST_PROJECT}')
        
        assert_json_response(response, HTTP_OK)
        data = json.loads(response.data)
        assert data['key'] == 'value'

    @patch('builtins.open')
    def test_get_audit_json_data_success(self, mock_open, auth_client):
        """Test GET /audit/<folder> with valid audit JSON file."""
        mock_file = Mock()
        mock_file.read.return_value = json.dumps({"audit_data": "test"})
        mock_open.return_value.__enter__.return_value = mock_file
        
        response = auth_client.get('/audit/test_folder?project=TEST_PROJECT')
        
        assert_json_response(response, HTTP_OK)
        data = json.loads(response.data)
        assert data['audit_data'] == 'test'

    @patch('builtins.open')
    def test_load_json_success(self, mock_open, auth_client):
        """Test GET /load_json with valid JSON file."""
        mock_file = Mock()
        mock_file.read.return_value = json.dumps({"test": "data"})
        mock_open.return_value.__enter__.return_value = mock_file
        
        response = auth_client.get('/load_json?path=/path/to/test.json')
        assert_json_response(response, HTTP_OK)
        data = json.loads(response.data)
        assert data['test'] == 'data'

    @patch('builtins.open')
    @patch('analysis.data_pre_analysis.compare_files_and_get_diff')
    def test_load_json_database_processing(self, mock_diff, mock_open, auth_client):
        """Test GET /load_json processes database files correctly."""
        # Mock database file content
        db_content = [
            {
                "key": "TEST-1",
                "description": "Original description",
                "generated_description": "Generated description",
                "generated_description_confidence": 0.9
            }
        ]
        
        mock_file = Mock()
        mock_file.read.return_value = json.dumps(db_content)
        mock_open.return_value.__enter__.return_value = mock_file
        
        mock_diff.return_value = ["+added line", "-removed line", "? context line"]
        
        response = auth_client.get('/load_json?path=/databases/test.json')
        
        assert_json_response(response, HTTP_OK)
        data = json.loads(response.data)
        assert 'data' in data
        assert len(data['data']) == 1
        assert data['data'][0]['llm_conf'] == 0.9
        assert 'llm_diff' in data['data'][0]

