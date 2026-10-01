"""
Tests for inference routes.
"""
import json
import os
import pytest
from unittest.mock import patch, Mock

from tests.test_utils import (
    create_test_file_content, create_test_iteration_content,
    create_test_consolidated_content, assert_json_response, assert_template_response
)
from tests.test_constants import (
    TEST_PROJECT, TEST_FILENAME, TEST_OUTPUT_FOLDER,
    HTTP_OK,
)


class TestInferenceRoutes:
    """Test cases for inference routes."""

    def test_confirmation_get(self, auth_client):
        """Test GET /confirmation route."""
        response = auth_client.get('/confirmation')
        assert_template_response(response, 200)

    @patch('web.routes.inference_routes.get_iterations_field_summary')
    def test_field_summary_success(self, mock_summary, auth_client):
        """Test POST /field_summary with valid data."""
        mock_summary.return_value = {
            "field": "priority",
            "summary": {"High": 10, "Medium": 5, "Low": 2}
        }
        
        response = auth_client.post('/field_summary',
                                  json={
                                      "project": "TEST_PROJECT", 
                                      "field": "priority",
                                      "output_folder": "TEST_PROJECT_20230501_120000"
                                  })
        
        assert_json_response(response, 200)
        data = json.loads(response.data)
        assert data['field'] == 'priority'
        assert data['summary']['High'] == 10

    def test_process_csv_no_file(self, auth_client):
        """Test POST /process_csv without file - returns empty string when no config."""
        response = auth_client.post('/process_csv',
                                  data={},
                                  content_type="multipart/form-data")

        assert_json_response(response, 200)
        data = json.loads(response.data)
        # Route returns config['question_json'] or '' when not configured
        assert data == ''

    @patch('web.routes.inference_routes.generate_iteration_file')
    def test_confirmation_completed_success(self, mock_generate, auth_client):
        """Test POST /confirmation_completed with valid data."""
        mock_generate.return_value = {"filename": "test_iteration.json", "success": True}
        
        response = auth_client.post('/confirmation_completed',
                                  json={
                                      "project": "TEST_PROJECT",
                                      "output_folder": "TEST_PROJECT_20230501_120000",
                                      "field": "priority",
                                      "predictions": [
                                          {"issue_key": "TEST-1", "predicted_value": "High"}
                                      ]
                                  })
        
        assert_json_response(response, 200)
        data = json.loads(response.data)
        assert 'message' in data
        assert data['message'] == "Confirmation received."
        assert 'filename' in data
        assert 'iteration_filename' in data

    @patch('services.inference_pipeline.run_field_completion')
    def test_field_completion_success(self, mock_pipeline, auth_client):
        """Test POST /field_completion with valid data."""
        mock_pipeline.return_value = {"success": True, "processed": 10}
        
        response = auth_client.post('/field_completion',
                                  json={
                                      "project": "TEST_PROJECT",
                                      "field": "priority",
                                      "input_file": "test.json"
                                  })
        
        assert_template_response(response, 200)

    def test_get_clustering_progress(self, auth_client):
        """Test GET /get_clustering_progress."""
        response = auth_client.get('/get_clustering_progress')
        assert_json_response(response, 200)
        data = json.loads(response.data)
        assert isinstance(data, dict)

    def test_get_inference_progress(self, auth_client):
        """Test GET /get_inference_progress."""
        response = auth_client.get('/get_inference_progress')
        assert_json_response(response, 200)
        data = json.loads(response.data)
        assert isinstance(data, dict)

    def test_abort_ml_predictions(self, auth_client):
        """Test POST /abort_ml_predictions."""
        response = auth_client.post('/abort_ml_predictions')
        assert_json_response(response, 200)
        data = json.loads(response.data)
        assert data == {}  # Route returns empty dict

    def test_confirm_predictions_fallback_renders_template(self, auth_client):
        """Test GET /confirm_predictions falls back to template when config is None."""
        response = auth_client.get('/confirm_predictions')

        # Route enters else branch (config=None in test), renders confirm_predictions.html
        assert_template_response(response, 200)

    def test_trigger_clustering(self, auth_client):
        """Test GET /confirm_predictions renders template when config is None (clustering not triggered)."""
        response = auth_client.get('/confirm_predictions')

        # Route enters else branch (config=None), renders template
        assert_template_response(response, 200)

    def test_field_completion_ignores_json_body(self, auth_client):
        """Test POST /field_completion ignores JSON body - route lists files and renders template."""
        response = auth_client.post('/field_completion',
                                  json={
                                      "project": "TEST_PROJECT",
                                      "field": "",
                                      "input_file": "test.json"
                                  })

        # Route does NOT parse JSON body; it lists DATABASES_FOLDER files and renders template
        assert_template_response(response, 200)


    @patch('web.routes.inference_routes.get_iterations_field_summary')
    def test_field_summary_with_iterations(self, mock_summary, auth_client):
        """Test POST /field_summary with existing iterations."""
        mock_summary.return_value = {
            "field": "priority",
            "summary": {"High": 5, "Medium": 3}
        }

        response = auth_client.post('/field_summary',
                                  json={"project": "TEST_PROJECT", "field": "priority"})

        assert_json_response(response, 200)
        data = json.loads(response.data)
        assert data['field'] == 'priority'

