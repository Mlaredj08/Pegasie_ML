# Test Suite for JFIP Web UI Routes

This directory contains comprehensive test coverage for all Flask routes in the JFIP Web UI application.

## Test Structure

```
tests/
├── __init__.py                    # Test module initialization
├── conftest.py                    # Pytest fixtures and configuration
├── test_utils.py                  # Shared test utilities and helpers
├── test_auth_routes.py            # Authentication routes tests
├── test_config_routes.py          # Configuration and data analysis routes tests
├── test_inference_routes.py       # Inference and ML routes tests
├── test_decision_tree_routes.py   # Decision tree routes tests
├── test_file_manager_routes.py    # File manager routes tests
├── test_jira_routes.py           # Jira integration routes tests
├── test_azure_routes.py          # Azure DevOps integration routes tests
├── test_iteration_routes.py       # Iteration management routes tests
└── README.md                      # This file
```

## Running Tests

### Install Test Dependencies
```bash
pip install -r requirements-test.txt
```

### Run All Tests
```bash
python -m pytest tests/
```

### Run Specific Test File
```bash
pytest tests/test_auth_routes.py
```

### Run with Coverage
```bash
pytest --cov=web --cov-report=html
```

### Run with Verbose Output
```bash
pytest -v
```

### Run Only Unit Tests
```bash
pytest -m unit
```

### Run Only Authentication Tests
```bash
pytest -m auth
```

### Skip Slow Tests
```bash
pytest -m "not slow"
```

## Test Coverage

### Authentication Routes (`test_auth_routes.py`)
- `GET /login` - Login page rendering
- `POST /login` - Login form submission (success/failure)
- `GET /logout` - Logout functionality
- `GET /api/me` - Current user info
- `POST /auth/verify` - Credential verification

### Configuration Routes (`test_config_routes.py`)
- `GET /` - Main index page
- `GET /data_analysis` - Data analysis page
- `POST /get_iterations_by_project` - Project iteration data
- `POST /run_data_analysis` - Various analysis report types
- `GET /view/<filename>` - Template viewing
- `GET /data/<folder>` - JSON data serving
- `GET /audit/<folder>` - Audit data serving
- `GET /load_json` - JSON file loading

### Inference Routes (`test_inference_routes.py`)
- `GET /confirmation` - Confirmation page
- `POST /field_summary` - Field summary generation
- `POST /process_csv` - CSV file processing
- `POST /confirmation_completed` - Confirmation completion
- `POST /field_completion` - Field completion pipeline
- `POST /run_field_audit` - Field audit testing
- `POST /get_test_report` - Test report generation
- `POST /confirm_predictions` - ML prediction confirmation
- `GET /get_clustering_progress` - Clustering progress
- `GET /get_inference_progress` - Inference progress
- `POST /abort_ml_predictions` - Abort ML operations
- `GET /get_ml_predictions` - Get ML predictions

### Decision Tree Routes (`test_decision_tree_routes.py`)
- `GET /questionnarie_decision_tree` - Decision tree questionnaire
- `GET /tree_editor` - Tree editor interface
- `GET /trees` - List available trees
- `GET /get_tree` - Get specific tree
- `POST /dt/start` - Start new session
- `POST /dt/answer` - Answer tree questions
- `POST /dt/rewind` - Rewind session
- Various `/dt/log_*` endpoints - Session logging
- `POST /dt/save_tree` - Save tree
- `DELETE /dt/trees/<name>` - Delete tree
- `POST /dt/upload_csv` - CSV upload for trees

### File Manager Routes (`test_file_manager_routes.py`)
- `GET /file_manager` - File manager interface
- `POST /file_manager` - File upload
- `GET /download_file` - File download
- `POST /delete_file` - File deletion
- `GET /preview_file` - File preview
- `POST /delete_cached_item` - Delete cached items
- `GET /api/clearable_items` - List clearable items
- `POST /clear_all_cache` - Bulk cache clearing

### Jira Integration Routes (`test_jira_routes.py`)
- `GET /export_jira` - Jira export page
- `POST /export_jira` - Jira data export
- `POST /fields` - Jira field fetching
- `POST /generate` - Jira data generation
- `GET /jira_viewer` - Jira data viewer
- `GET /show_jira_viewer` - Show Jira data
- `POST /validate_push_issues` - Validate push data
- `POST /push_to_jira` - Push predictions to Jira

### Azure DevOps Routes (`test_azure_routes.py`)
- `GET /export_azure` - Azure export page
- `POST /export_azure` - Azure data export
- `POST /fields_azure` - Azure field fetching
- `POST /generate_azure` - Azure data generation

### Iteration Routes (`test_iteration_routes.py`)
- `POST /consolidate_iterations` - Consolidate iteration files
- `POST /delete_iteration_file` - Delete iteration files

## Testing Strategy

### Mocking and Stubs
- External API calls (Jira, Azure DevOps) are mocked
- File system operations use temporary directories
- Database operations use mock data
- Session management is simulated

### Authentication Testing
- Tests include both authenticated and unauthenticated scenarios
- Session mocking for protected routes
- Permission testing for different user roles

### Error Handling
- Network errors and timeouts
- Invalid data formats
- Missing parameters
- File system errors
- Authentication failures

### Edge Cases
- Large files and datasets
- Special characters in filenames
- Unicode content
- Concurrent requests
- Path traversal attempts

## Fixtures

### Main Fixtures
- `client` - Flask test client
- `auth_client` - Authenticated test client
- `temp_dir` - Temporary directory for file operations
- `sample_jira_data` - Sample Jira issue data
- `mock_jira_response` - Mock Jira API response
- `mock_azure_response` - Mock Azure API response

### Data Fixtures
- `sample_iteration_data` - Sample iteration files
- `sample_decision_tree` - Sample decision tree structure
- `mock_file_manager_data` - Mock file manager listings

## Configuration

### Pytest Configuration
- Located in `pytest.ini`
- Configured for verbose output
- Markers for test categorization
- Coverage reporting setup

### Test Dependencies
- Listed in `requirements-test.txt`
- Includes pytest and plugins
- Mocking and testing utilities
- Coverage and benchmarking tools

## Best Practices

1. **Test Isolation**: Each test is independent with proper setup/teardown
2. **Mock External Dependencies**: All external services are mocked
3. **Comprehensive Coverage**: Tests cover success, failure, and edge cases
4. **Clear Naming**: Test names clearly describe what is being tested
5. **Documentation**: Each test file has clear documentation of covered endpoints
6. **Authentication Testing**: Both authenticated and unauthenticated scenarios
7. **Error Scenarios**: Comprehensive error handling testing
8. **Data Validation**: Input validation and sanitization testing

## Adding New Tests

When adding new routes:

1. Create test methods following the naming convention `test_<endpoint>_<scenario>`
2. Use appropriate fixtures from `conftest.py`
3. Mock all external dependencies
4. Test both success and failure scenarios
5. Include edge cases and error conditions
6. Add documentation for new test coverage

## Continuous Integration

These tests are designed to run in CI/CD pipelines:

- Fast execution with proper mocking
- No external dependencies required
- Comprehensive coverage reporting
- Clear test output and reporting
