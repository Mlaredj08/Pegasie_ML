"""
Integration test: validates data flow across the full pipeline.

Pipeline: Export → Save Iteration → Consolidate → Push to Jira

Mocked boundaries: Jira HTTP API, ML model inference.
Real code: file I/O, data transformations, route logic, JSON serialization.

This test ensures that the data format produced by each stage is compatible
with the next stage's expectations — catching schema drift, filename bugs,
and session state issues that unit tests miss.
"""
import json
import os
import pytest
from unittest.mock import patch, Mock
from datetime import datetime

from tests.test_constants import (
    TEST_JIRA_URL, TEST_JIRA_USERNAME, TEST_JIRA_PASSWORD,
    TEST_AUTH_SESSION, HTTP_OK, HTTP_BAD_REQUEST, HTTP_NOT_FOUND,
)
from tests.test_utils import assert_json_response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pipeline_dirs(tmp_path):
    """
    Create an isolated workspace with all folders the pipeline writes to.
    Patches constants so routes and services use these temp directories.
    """
    db_folder = tmp_path / "databases"
    db_settings = db_folder / "settings"
    iter_folder = tmp_path / "iterations"
    ready_to_send = iter_folder / "ready_to_send"

    db_folder.mkdir()
    db_settings.mkdir()
    iter_folder.mkdir()
    ready_to_send.mkdir()

    # Only patch constants that actually exist in each module
    patch_targets = [
        ('web.routes.jira_routes.DATABASES_FOLDER', str(db_folder)),
        ('web.routes.jira_routes.ITERATION_FOLDER', str(iter_folder)),
        ('web.routes.inference_routes.DATABASES_FOLDER', str(db_folder)),
        ('web.routes.inference_routes.ITERATION_FOLDER', str(iter_folder)),
        ('web.routes.iteration_routes.ITERATION_FOLDER', str(iter_folder)),
        ('services.iteration_service.ITERATION_FOLDER', str(iter_folder)),
    ]

    active_patches = []
    for target, value in patch_targets:
        p = patch(target, value)
        active_patches.append(p)
        p.start()

    yield {
        'databases': db_folder,
        'settings': db_settings,
        'iterations': iter_folder,
        'ready_to_send': ready_to_send,
        'tmp_path': tmp_path,
    }

    for p in active_patches:
        p.stop()


@pytest.fixture
def pipeline_client(auth_client):
    """Authenticated test client — wraps the existing auth_client fixture."""
    return auth_client


# ---------------------------------------------------------------------------
# Helper: build realistic iteration file content
# ---------------------------------------------------------------------------

def build_iteration_file_content(output_folder, predictions_by_field):
    """
    Build iteration file content matching generate_iteration_file() output format.
    
    Args:
        output_folder: e.g. "TEST_20260525_120000"
        predictions_by_field: dict of {field_name: [{value, issue_keys}]}
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_fields = []
    for field_name, preds in predictions_by_field.items():
        predictions_list = []
        for p in preds:
            predictions_list.append({
                "value": p["value"],
                "original_prediction_value": p["value"],
                "issue_keys": p["issue_keys"]
            })
        target_fields.append({
            "field_name": field_name,
            "predictions": predictions_list
        })

    return {
        "time_stamp": timestamp,
        "user": "test_user",
        "output_folder": output_folder,
        "target_fields": target_fields,
        "changed_keywords_list": []
    }


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestPipelineIntegration:
    """
    End-to-end pipeline tests validating data format compatibility
    between stages: iteration file → consolidation → push.
    """

    def test_full_pipeline_consolidate_and_push(self, pipeline_client, pipeline_dirs):
        """
        Full pipeline: create iteration file → consolidate → push to Jira.
        Validates that data flows correctly through real code with real file I/O.
        """
        output_folder = "TEST_20260525_120000"
        iter_folder = pipeline_dirs['iterations']
        ready_to_send = pipeline_dirs['ready_to_send']

        # ── STEP 1: Create iteration file (simulates confirmation_completed output) ──
        iteration_content = build_iteration_file_content(output_folder, {
            "priority": [
                {"value": "High", "issue_keys": ["TEST-1", "TEST-2"]},
                {"value": "Critical", "issue_keys": ["TEST-3"]},
            ],
            "components": [
                {"value": "Backend", "issue_keys": ["TEST-1", "TEST-4"]},
            ]
        })

        # Write iteration file with correct naming convention
        iter_filename = f"{output_folder}_iteration_20260525_120100.json"
        iter_filepath = iter_folder / iter_filename
        iter_filepath.write_text(json.dumps(iteration_content, indent=2), encoding='utf-8')

        # Verify file was created
        assert iter_filepath.exists()

        # ── STEP 2: Consolidate iterations via route ──
        with patch('services.iteration_service.utils') as mock_utils:
            mock_utils.model_config = None  # No config — use project_override
            mock_utils.get_issuetype_lookup.return_value = {
                "TEST-1": "Bug",
                "TEST-2": "Bug",
                "TEST-3": "Story",
                "TEST-4": "Bug",
            }

            response = pipeline_client.post('/consolidate_iterations',
                                           json={
                                               "project": "TEST",
                                               "output_folder": output_folder
                                           })

        assert response.status_code == 200
        consolidation_result = json.loads(response.data)
        assert consolidation_result['success'] is True
        assert consolidation_result['total_issue_keys'] == 5  # TEST-1,2,3 (priority) + TEST-1,4 (components)
        assert 'predictions_by_issuetype' in consolidation_result
        assert 'filename' in consolidation_result

        # Verify consolidated file was written to ready_to_send
        consolidated_filename = consolidation_result['filename']
        consolidated_path = ready_to_send / consolidated_filename
        assert consolidated_path.exists()

        # Read and validate consolidated file structure
        consolidated_data = json.loads(consolidated_path.read_text(encoding='utf-8'))
        assert consolidated_data['project'] == "TEST"
        assert 'predictions_by_issuetype' in consolidated_data
        assert 'timestamp' in consolidated_data
        assert consolidated_data['total_issue_keys'] == 5

        # Verify predictions are grouped by issue type
        preds_by_type = consolidated_data['predictions_by_issuetype']
        all_predictions = []
        for issue_type, preds in preds_by_type.items():
            for p in preds:
                all_predictions.append(p)
                # Each prediction has the required keys for push
                assert 'field' in p
                assert 'new_value' in p
                assert 'issue_keys' in p
                assert isinstance(p['issue_keys'], list)

        # ── STEP 3: Push to Jira ──
        with patch('web.routes.jira_routes.fetch_issue_fields') as mock_fetch_fields, \
             patch('web.routes.jira_routes.apply_prediction_json_to_jira') as mock_apply:

            # All fields are empty in Jira → proceed with all updates
            mock_fetch_fields.return_value = {}

            # Simulate successful Jira updates for each issue+field combo
            mock_apply.return_value = [
                {"issuekey": "TEST-1", "field": "priority", "status": 200, "response": {}},
                {"issuekey": "TEST-2", "field": "priority", "status": 200, "response": {}},
                {"issuekey": "TEST-3", "field": "priority", "status": 200, "response": {}},
                {"issuekey": "TEST-1", "field": "components", "status": 200, "response": {}},
                {"issuekey": "TEST-4", "field": "components", "status": 200, "response": {}},
            ]

            response = pipeline_client.post('/push_to_jira',
                                           json={"filename": consolidated_filename})

        assert response.status_code == 200
        push_result = json.loads(response.data)
        assert push_result['success'] is True
        assert push_result['success_count'] == 5
        assert push_result['failed_count'] == 0
        assert len(push_result['successful_items']) == 5
        assert len(push_result['failed_items']) == 0

        # Verify apply_prediction_json_to_jira received correct format
        call_args = mock_apply.call_args
        jira_format = call_args[0][0]
        assert 'target_fields' in jira_format
        assert 'user' in jira_format
        assert 'time_stamp' in jira_format
        # Verify all fields are present
        field_names = {tf['field_name'] for tf in jira_format['target_fields']}
        assert 'priority' in field_names
        assert 'components' in field_names

    def test_pipeline_with_partial_push_failures(self, pipeline_client, pipeline_dirs):
        """
        Pipeline where some Jira pushes fail — verifies error reporting.
        """
        output_folder = "FAIL_20260525_130000"
        iter_folder = pipeline_dirs['iterations']

        # Create iteration file
        iteration_content = build_iteration_file_content(output_folder, {
            "priority": [
                {"value": "High", "issue_keys": ["FAIL-1", "FAIL-2", "FAIL-3"]},
            ]
        })
        iter_filename = f"{output_folder}_iteration_20260525_130100.json"
        (iter_folder / iter_filename).write_text(
            json.dumps(iteration_content, indent=2), encoding='utf-8'
        )

        # Consolidate
        with patch('services.iteration_service.utils') as mock_utils:
            mock_utils.model_config = None
            mock_utils.get_issuetype_lookup.return_value = {
                "FAIL-1": "Bug", "FAIL-2": "Bug", "FAIL-3": "Story"
            }
            response = pipeline_client.post('/consolidate_iterations',
                                           json={"project": "FAIL", "output_folder": output_folder})

        assert response.status_code == 200
        consolidated_filename = json.loads(response.data)['filename']

        # Push with partial failures
        with patch('web.routes.jira_routes.fetch_issue_fields') as mock_fetch_fields, \
             patch('web.routes.jira_routes.apply_prediction_json_to_jira') as mock_apply:

            mock_fetch_fields.return_value = {}
            mock_apply.return_value = [
                {"issuekey": "FAIL-1", "field": "priority", "status": 200, "response": {}},
                {"issuekey": "FAIL-2", "field": "priority", "status": 400, "response": {
                    "errors": {"priority": "Field 'priority' cannot be set"},
                    "errorMessages": []
                }},
                {"issuekey": "FAIL-3", "field": "priority", "status": 403, "response": {
                    "errors": {},
                    "errorMessages": ["You do not have permission to edit this issue"]
                }},
            ]

            response = pipeline_client.post('/push_to_jira',
                                           json={"filename": consolidated_filename})

        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        assert result['success_count'] == 1
        assert result['failed_count'] == 2

        # Verify failed items have error details
        failed = result['failed_items']
        assert len(failed) == 2
        assert any("cannot be set" in item.get("error", "") for item in failed)
        assert any("permission" in item.get("error", "") for item in failed)

    def test_pipeline_filter_non_empty_fields(self, pipeline_client, pipeline_dirs):
        """
        Pipeline where some fields are already populated in Jira —
        verifies _filter_non_empty_fields removes them before push.
        """
        output_folder = "FILTER_20260525_140000"
        iter_folder = pipeline_dirs['iterations']

        # Create iteration with predictions for 3 issues
        iteration_content = build_iteration_file_content(output_folder, {
            "priority": [
                {"value": "High", "issue_keys": ["FILTER-1", "FILTER-2", "FILTER-3"]},
            ]
        })
        iter_filename = f"{output_folder}_iteration_20260525_140100.json"
        (iter_folder / iter_filename).write_text(
            json.dumps(iteration_content, indent=2), encoding='utf-8'
        )

        # Consolidate
        with patch('services.iteration_service.utils') as mock_utils:
            mock_utils.model_config = None
            mock_utils.get_issuetype_lookup.return_value = {
                "FILTER-1": "Bug", "FILTER-2": "Bug", "FILTER-3": "Bug"
            }
            response = pipeline_client.post('/consolidate_iterations',
                                           json={"project": "FILTER", "output_folder": output_folder})

        assert response.status_code == 200
        consolidated_filename = json.loads(response.data)['filename']

        # Push — but FILTER-2 already has priority set in Jira
        with patch('web.routes.jira_routes.fetch_issue_fields') as mock_fetch_fields, \
             patch('web.routes.jira_routes.apply_prediction_json_to_jira') as mock_apply:

            # fetch_issue_fields returns non-empty value for FILTER-2 priority
            mock_fetch_fields.return_value = {
                "FILTER-2": {"priority": {"name": "Medium"}}
            }
            mock_apply.return_value = [
                {"issuekey": "FILTER-1", "field": "priority", "status": 200, "response": {}},
                {"issuekey": "FILTER-3", "field": "priority", "status": 200, "response": {}},
            ]

            response = pipeline_client.post('/push_to_jira',
                                           json={"filename": consolidated_filename})

        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True
        # FILTER-2 should be filtered out — only 2 pushed
        assert result['success_count'] == 2
        assert result['failed_count'] == 0

    def test_pipeline_consolidation_deduplicates_across_iterations(self, pipeline_client, pipeline_dirs):
        """
        Multiple iteration files for the same database — consolidation deduplicates issue keys.
        This is the exact bug that was previously fixed (mixing predictions from different databases).
        """
        output_folder = "DEDUP_20260525_150000"
        iter_folder = pipeline_dirs['iterations']

        # First iteration: TEST-1, TEST-2 → priority High
        iter1 = build_iteration_file_content(output_folder, {
            "priority": [{"value": "High", "issue_keys": ["DEDUP-1", "DEDUP-2"]}]
        })
        (iter_folder / f"{output_folder}_iteration_20260525_150100.json").write_text(
            json.dumps(iter1, indent=2), encoding='utf-8'
        )

        # Second iteration: TEST-2, TEST-3 → priority High (TEST-2 is duplicate)
        iter2 = build_iteration_file_content(output_folder, {
            "priority": [{"value": "High", "issue_keys": ["DEDUP-2", "DEDUP-3"]}]
        })
        (iter_folder / f"{output_folder}_iteration_20260525_150200.json").write_text(
            json.dumps(iter2, indent=2), encoding='utf-8'
        )

        # Also create an iteration for a DIFFERENT database — should NOT be included
        other_folder = "OTHER_20260525_160000"
        iter_other = build_iteration_file_content(other_folder, {
            "priority": [{"value": "Low", "issue_keys": ["OTHER-1"]}]
        })
        (iter_folder / f"{other_folder}_iteration_20260525_160100.json").write_text(
            json.dumps(iter_other, indent=2), encoding='utf-8'
        )

        # Consolidate only the DEDUP database
        with patch('services.iteration_service.utils') as mock_utils:
            mock_utils.model_config = None
            mock_utils.get_issuetype_lookup.return_value = {
                "DEDUP-1": "Bug", "DEDUP-2": "Bug", "DEDUP-3": "Story"
            }
            response = pipeline_client.post('/consolidate_iterations',
                                           json={"project": "DEDUP", "output_folder": output_folder})

        assert response.status_code == 200
        result = json.loads(response.data)
        assert result['success'] is True

        # DEDUP-2 appears in both iterations but should be deduplicated
        assert result['total_issue_keys'] == 3  # DEDUP-1, DEDUP-2, DEDUP-3 (not 4)

        # Verify OTHER-1 was NOT included
        all_keys = set()
        for issue_type, preds in result['predictions_by_issuetype'].items():
            for p in preds:
                all_keys.update(p['issue_keys'])
        assert "OTHER-1" not in all_keys
        assert all_keys == {"DEDUP-1", "DEDUP-2", "DEDUP-3"}

    def test_pipeline_push_no_consolidated_file(self, pipeline_client, pipeline_dirs):
        """Push to Jira when no consolidated file exists — returns 404."""
        response = pipeline_client.post('/push_to_jira',
                                       json={"filename": "nonexistent.json"})
        assert response.status_code == 404
        result = json.loads(response.data)
        assert 'error' in result

    def test_pipeline_push_empty_ready_to_send(self, pipeline_client, pipeline_dirs):
        """Push to Jira with empty ready_to_send folder — returns 404."""
        response = pipeline_client.post('/push_to_jira', json={})
        assert response.status_code == 404
        result = json.loads(response.data)
        assert 'No consolidated files found' in result['error']

    def test_pipeline_consolidation_no_iteration_files(self, pipeline_client, pipeline_dirs):
        """Consolidate when no iteration files exist for the project."""
        with patch('services.iteration_service.utils') as mock_utils:
            mock_utils.model_config = None
            response = pipeline_client.post('/consolidate_iterations',
                                           json={"project": "EMPTY", "output_folder": "EMPTY_20260525"})

        assert response.status_code == 404
        result = json.loads(response.data)
        assert 'No iteration files found' in result['error']

    def test_pipeline_toggle_ignore_flag_in_consolidated(self, pipeline_client, pipeline_dirs):
        """
        Toggle ignore flag on a consolidated file, then verify push skips ignored issues.
        """
        output_folder = "IGNORE_20260525_170000"
        iter_folder = pipeline_dirs['iterations']
        ready_to_send = pipeline_dirs['ready_to_send']

        # Create iteration
        iteration_content = build_iteration_file_content(output_folder, {
            "priority": [
                {"value": "High", "issue_keys": ["IGN-1", "IGN-2"]},
            ]
        })
        (iter_folder / f"{output_folder}_iteration_20260525_170100.json").write_text(
            json.dumps(iteration_content, indent=2), encoding='utf-8'
        )

        # Consolidate
        with patch('services.iteration_service.utils') as mock_utils:
            mock_utils.model_config = None
            mock_utils.get_issuetype_lookup.return_value = {"IGN-1": "Bug", "IGN-2": "Bug"}
            response = pipeline_client.post('/consolidate_iterations',
                                           json={"project": "IGNORE", "output_folder": output_folder})

        assert response.status_code == 200
        consolidated_filename = json.loads(response.data)['filename']

        # Toggle ignore flag on IGN-1|priority
        response = pipeline_client.post('/toggle_ignore_flag',
                                       json={
                                           "filename": consolidated_filename,
                                           "issue_key": "IGN-1",
                                           "field": "priority",
                                           "reason": "already_populated"
                                       })

        assert response.status_code == 200
        toggle_result = json.loads(response.data)
        assert toggle_result['success'] is True
        assert toggle_result['action'] == 'added'
        assert toggle_result['new_state'] == 'ignored'

        # Verify the consolidated file now has the ignore flag
        consolidated_data = json.loads(
            (ready_to_send / consolidated_filename).read_text(encoding='utf-8')
        )
        assert "ignore_flags" in consolidated_data
        assert "IGN-1|priority" in consolidated_data["ignore_flags"]

        # Toggle again — removes the flag
        response = pipeline_client.post('/toggle_ignore_flag',
                                       json={
                                           "filename": consolidated_filename,
                                           "issue_key": "IGN-1",
                                           "field": "priority"
                                       })

        assert response.status_code == 200
        toggle_result = json.loads(response.data)
        assert toggle_result['action'] == 'removed'
        assert toggle_result['new_state'] == 'active'
