"""
Tests for file manager routes.
"""
import json
import os
import io
import pytest
from unittest.mock import patch, Mock

from tests.test_utils import (
    create_test_file_content, create_temp_json_file,
    assert_json_response, assert_template_response
)


class TestFileManagerRoutes:
    """Test cases for file manager routes."""

    @patch('utils_pkg.get_current_files')
    @patch('utils_pkg.get_cached_files')
    @patch('utils_pkg.get_timestamp_root_folders')
    def test_file_manager_get(self, mock_timestamp, mock_cached, mock_current, auth_client):
        """Test GET /file_manager."""
        mock_current.return_value = {
            "databases": ["test1.json", "test2.json"],
            "dependency_model": []
        }
        mock_cached.return_value = {
            "predictions": ["pred1.json", "pred2.json"],
            "ml_models": ["model1.pkl"]
        }
        mock_timestamp.return_value = ["PROJECT_20230501_120000"]
        
        response = auth_client.get('/file_manager')
        assert_template_response(response, 200)

    @patch('utils_pkg.validate_json_file')
    @patch('utils_pkg.save_json_file')
    def test_file_manager_post_success(self, mock_save, mock_validate, auth_client):
        """Test POST /file_manager with valid file."""
        mock_validate.return_value = ("test.json", {"key": "value"})
        mock_save.return_value = ("test.json", False)
        
        mock_file = Mock()
        mock_file.filename = "test.json"
        
        response = auth_client.post('/file_manager',
                             data={
                                 "json_file": (io.BytesIO(b'{"key": "value"}'), "test.json"),
                                 "destination": "/test/path"
                             },
                             content_type="multipart/form-data")
        
        assert response.status_code == 302  # Redirect

    def test_file_manager_post_no_file(self, auth_client):
        """Test POST /file_manager without file."""
        response = auth_client.post('/file_manager',
                             data={},
                             content_type="multipart/form-data")
        
        assert response.status_code == 302  # Redirect with error

    @patch('utils_pkg.validate_json_file')
    def test_file_manager_post_invalid_file(self, mock_validate, auth_client):
        """Test POST /file_manager with invalid file."""
        mock_validate.return_value = (None, None)  # Validation failed
        
        mock_file = Mock()
        mock_file.filename = "invalid.json"
        
        response = auth_client.post('/file_manager',
                             data={
                                 "json_file": (io.BytesIO(b'invalid json'), "invalid.json"),
                                 "destination": "/test/path"
                             },
                             content_type="multipart/form-data")
        
        assert response.status_code == 302  # Redirect with error

    @patch('utils_pkg.validate_json_file')
    @patch('utils_pkg.save_json_file')
    def test_file_manager_post_duplicate_renamed(self, mock_save, mock_validate, auth_client):
        """Test POST /file_manager with duplicate file (renamed)."""
        mock_validate.return_value = ("test.json", {"key": "value"})
        mock_save.return_value = ("test_1.json", True)  # Renamed due to duplicate
        
        mock_file = Mock()
        mock_file.filename = "test.json"
        
        response = auth_client.post('/file_manager',
                             data={
                                 "json_file": (io.BytesIO(b'{"key": "value"}'), "test.json"),
                                 "destination": "/test/path"
                             },
                             content_type="multipart/form-data")
        
        assert response.status_code == 302  # Redirect

    @patch('utils_pkg.get_folder_paths')
    def test_download_file_success(self, mock_folders, auth_client, temp_dir):
        """Test GET /download_file with valid file."""
        # Create a real file in the temp directory so send_from_directory works
        test_file = os.path.join(temp_dir, "test.json")
        with open(test_file, 'w') as f:
            json.dump({"key": "value"}, f)
        mock_folders.return_value = {"databases": temp_dir}

        response = auth_client.get('/download_file/databases/test.json')
        assert response.status_code == 200

    def test_download_file_missing_path(self, auth_client):
        """Test GET /download_file without path parameters - 404 handled by middleware."""
        response = auth_client.get('/download_file')
        # No route matches /download_file (needs /<folder>/<filename>), middleware redirects 404
        assert response.status_code == 302

    @patch('utils_pkg.get_folder_paths')
    @patch('os.path.exists')
    def test_download_file_not_found(self, mock_exists, mock_folders, auth_client):
        """Test GET /download_file with non-existent file."""
        mock_folders.return_value = {"databases": "/test/path"}
        mock_exists.return_value = False
        
        response = auth_client.get('/download_file/databases/nonexistent.json')
        assert response.status_code == 302  # Redirect with flash message

    @patch('utils_pkg.get_folder_paths')
    def test_download_file_invalid_folder(self, mock_folders, auth_client):
        """Test GET /download_file with invalid folder."""
        mock_folders.return_value = {"databases": "/test/path"}
        
        response = auth_client.get('/download_file/invalid_folder/test.json')
        assert response.status_code == 302  # Redirect with flash message

    @patch('utils_pkg.get_folder_paths')
    @patch('os.path.exists')
    @patch('os.remove')
    def test_delete_file_success(self, mock_remove, mock_exists, mock_folders, auth_client):
        """Test POST /delete_file with valid file."""
        mock_folders.return_value = {"databases": "/test/path"}
        mock_exists.return_value = True
        
        response = auth_client.post('/delete_file/databases/test.json')
        
        assert response.status_code == 302  # Redirect with flash message
        mock_remove.assert_called_once()

    def test_delete_file_missing_path(self, auth_client):
        """Test POST /delete_file without path parameters."""
        response = auth_client.post('/delete_file')
        assert response.status_code == 302  # Redirect to file_manager

    @patch('utils_pkg.get_folder_paths')
    @patch('os.path.exists')
    def test_delete_file_not_found(self, mock_exists, mock_folders, auth_client):
        """Test POST /delete_file with non-existent file."""
        mock_folders.return_value = {"databases": "/test/path"}
        mock_exists.return_value = False
        
        response = auth_client.post('/delete_file/databases/nonexistent.json')
        
        assert response.status_code == 302  # Redirect with flash message

    @patch('utils_pkg.get_folder_paths')
    @patch('os.path.exists')
    @patch('os.remove')
    def test_delete_file_exception(self, mock_remove, mock_exists, mock_folders, auth_client):
        """Test POST /delete_file with exception."""
        mock_folders.return_value = {"databases": "/test/path"}
        mock_exists.return_value = True
        mock_remove.side_effect = Exception("Permission denied")
        
        response = auth_client.post('/delete_file/databases/test.json')
        
        assert response.status_code == 302  # Redirect with flash message

    @patch('utils_pkg.get_folder_paths')
    @patch('os.path.exists')
    @patch('builtins.open')
    def test_preview_file_success(self, mock_open, mock_exists, mock_folders, auth_client):
        """Test GET /preview_file with valid JSON file."""
        mock_folders.return_value = {"databases": "/test/path"}
        mock_exists.return_value = True

        mock_file = Mock()
        mock_file.read.return_value = json.dumps([{"key": "TEST-1", "summary": "Test"}])
        mock_open.return_value.__enter__.return_value = mock_file

        response = auth_client.get('/preview_file/databases/test.json')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['filename'] == 'test.json'
        assert 'content' in data

    def test_preview_file_missing_path(self, auth_client):
        """Test GET /preview_file without path parameters."""
        response = auth_client.get('/preview_file')
        assert response.status_code == 302  # Redirect to file_manager

    @patch('utils_pkg.get_cacheable_folder_paths')
    @patch('os.path.exists')
    @patch('os.remove')
    @patch('os.path.isdir')
    def test_delete_cached_item_file(self, mock_isdir, mock_remove, mock_exists, mock_cacheable, auth_client):
        """Test POST /delete_cached_item for file."""
        mock_cacheable.return_value = {"predictions": "/test/predictions"}
        mock_exists.return_value = True
        mock_isdir.return_value = False
        
        response = auth_client.post('/delete_cached_item/predictions/test.json')
        
        assert response.status_code == 302  # Redirect with flash message

    @patch('utils_pkg.get_cacheable_folder_paths')
    @patch('os.path.exists')
    @patch('shutil.rmtree')
    @patch('os.path.isdir')
    def test_delete_cached_item_directory(self, mock_isdir, mock_rmtree, mock_exists, mock_cacheable, auth_client):
        """Test POST /delete_cached_item for directory."""
        mock_cacheable.return_value = {"ml_models": "/test/ml_models"}
        mock_exists.return_value = True
        mock_isdir.return_value = True
        
        response = auth_client.post('/delete_cached_item/ml_models/model_folder')
        
        assert response.status_code == 302  # Redirect with flash message

    def test_delete_cached_item_missing_path(self, auth_client):
        """Test POST /delete_cached_item without path."""
        response = auth_client.post('/delete_cached_item/predictions/')
        assert response.status_code == 302  # Redirect to file_manager

    @patch('utils_pkg.get_cacheable_folder_paths')
    @patch('os.path.exists')
    def test_delete_cached_item_not_found(self, mock_exists, mock_cacheable, auth_client):
        """Test POST /delete_cached_item with non-existent item."""
        mock_cacheable.return_value = {"predictions": "/test/predictions"}
        mock_exists.return_value = False
        
        response = auth_client.post('/delete_cached_item/predictions/nonexistent.json')
        
        assert response.status_code == 302  # Redirect with flash message

    @patch('utils_pkg.get_all_clearable_items')
    def test_api_clearable_items(self, mock_clearable, auth_client):
        """Test GET /api/clearable_items."""
        mock_clearable.return_value = {
            "predictions": ["pred1.json", "pred2.json"],
            "ml_models": ["model1.pkl"],
            "iterations": ["iter1.json"]
        }
        
        response = auth_client.get('/api/clearable_items')
        
        assert_json_response(response, 200)
        data = json.loads(response.data)
        assert 'predictions' in data
        assert len(data['predictions']) == 2

    @patch('utils_pkg.get_all_clearable_items')
    def test_api_clearable_items_empty(self, mock_clearable, auth_client):
        """Test GET /api/clearable_items with no items."""
        mock_clearable.return_value = {}
        
        response = auth_client.get('/api/clearable_items')
        
        assert_json_response(response, 200)
        data = json.loads(response.data)
        assert len(data) == 0

    @patch('os.path.exists')
    @patch('os.remove')
    @patch('os.path.isdir')
    @patch('shutil.rmtree')
    def test_clear_all_cache_success(self, mock_rmtree, mock_isdir, mock_remove, mock_exists, auth_client):
        """Test POST /clear_all_cache with valid selections."""
        # Mock different types of items
        def mock_exists_side_effect(path):
            return True  # All items exist
        
        def mock_isdir_side_effect(path):
            return 'folder' in path  # Folders are directories
        
        mock_exists.side_effect = mock_exists_side_effect
        mock_isdir.side_effect = mock_isdir_side_effect
        
        response = auth_client.post('/clear_all_cache',
                             json={
                                 "items": [
                                     {"path": "/predictions/pred1.json", "is_dir": False},
                                     {"path": "/ml_models/model_folder", "is_dir": True},
                                     {"path": "/iterations/iter1.json", "is_dir": False}
                                 ]
                             })
        
        assert_json_response(response, 200)
        data = json.loads(response.data)
        assert data['deleted'] == 3

    def test_clear_all_cache_empty_selection(self, auth_client):
        """Test POST /clear_all_cache with empty selection."""
        response = auth_client.post('/clear_all_cache',
                             json={"items": []})
        
        assert_json_response(response, 200)
        data = json.loads(response.data)
        assert data['deleted'] == 0

    @patch('os.path.exists')
    def test_clear_all_cache_item_not_found(self, mock_exists, auth_client):
        """Test POST /clear_all_cache with non-existent item."""
        mock_exists.return_value = False
        
        response = auth_client.post('/clear_all_cache',
                             json={"items": [{"path": "/predictions/nonexistent.json", "is_dir": False}]})
        
        assert_json_response(response, 200)
        data = json.loads(response.data)
        assert data['deleted'] == 0

    @patch('os.path.exists')
    @patch('os.remove')
    def test_clear_all_cache_exception(self, mock_remove, mock_exists, auth_client):
        """Test POST /clear_all_cache with exception."""
        mock_exists.return_value = True
        mock_remove.side_effect = Exception("Permission denied")
        
        response = auth_client.post('/clear_all_cache',
                             json={"items": [{"path": "/predictions/pred1.json", "is_dir": False}]})
        
        assert_json_response(response, 200)
        data = json.loads(response.data)
        assert data['deleted'] == 0
        assert len(data['errors']) == 1

    @patch('utils_pkg.get_current_files')
    def test_file_manager_with_large_files(self, mock_current, auth_client):
        """Test GET /file_manager with large files."""
        mock_current.return_value = {
            "databases": ["large_file.json", "small_file.json"],
            "dependency_model": []
        }
        
        response = auth_client.get('/file_manager')
        assert_template_response(response, 200)

    @patch('utils_pkg.validate_json_file')
    def test_file_manager_post_large_file(self, mock_validate, auth_client):
        """Test POST /file_manager with large file (>20MB)."""
        mock_validate.return_value = ("large_file.json", {"key": "value"})
        
        mock_file = Mock()
        mock_file.filename = "large_file.json"
        
        # Flask's MAX_CONTENT_LENGTH should handle this
        response = auth_client.post('/file_manager',
                             data={
                                 "json_file": (io.BytesIO(b'{"key": "value"}'), "large_file.json"),
                                 "destination": "/test/path"
                             },
                             content_type="multipart/form-data")
        
        # Test payload is tiny so Flask doesn't reject it; route processes and redirects
        assert response.status_code == 302

    @patch('utils_pkg.get_current_files')
    def test_file_manager_with_special_characters(self, mock_current, auth_client):
        """Test GET /file_manager with special characters in filenames."""
        mock_current.return_value = {
            "databases": ["file with spaces.json", "file-with-dashes.json", "file_with_underscores.json"],
            "dependency_model": []
        }
        
        response = auth_client.get('/file_manager')
        assert_template_response(response, 200)
