"""
Tests for authentication routes.
"""
import json
import pytest
from unittest.mock import patch, Mock

from tests.test_utils import create_mock_session, assert_json_response, assert_template_response
from tests.test_constants import (
    TEST_JIRA_URL, TEST_JIRA_USERNAME, TEST_JIRA_PASSWORD, TEST_JIRA_REMEMBER,
    HTTP_OK, MOCK_JIRA_USER_RESPONSE
)


class TestAuthRoutes:
    """Test cases for authentication routes."""

    def test_login_get(self, client):
        """Test GET /login route."""
        response = client.get('/login')
        assert_template_response(response, 200)
        assert b'login' in response.data.lower()

    @patch('web.routes.auth_routes.verify_jira_credentials')
    def test_login_post_success(self, mock_verify, client):
        """Test successful POST /login."""
        mock_verify.return_value = True
        
        response = client.post('/login', data={
            'jira_url': TEST_JIRA_URL,
            'username': TEST_JIRA_USERNAME,
            'password': TEST_JIRA_PASSWORD,
            'remember': str(TEST_JIRA_REMEMBER).lower()
        })
        
        assert response.status_code == 302
        assert response.location == '/'

    @patch('web.routes.auth_routes.verify_jira_credentials')
    def test_login_post_with_next_param(self, mock_verify, client):
        """Test POST /login with next parameter."""
        mock_verify.return_value = True
        
        response = client.post('/login?next=/data_analysis', data={
            'jira_url': TEST_JIRA_URL,
            'username': TEST_JIRA_USERNAME,
            'password': TEST_JIRA_PASSWORD
        })
        
        assert response.status_code == 302
        assert response.location == '/data_analysis'

    def test_logout(self, auth_client):
        """Test /logout route."""
        response = auth_client.get('/logout')
        assert response.status_code == 302
        assert response.location.endswith('/login')

    def test_api_me_authenticated(self, auth_client):
        """Test GET /api/me when authenticated."""
        response = auth_client.get('/api/me')
        assert_json_response(response, HTTP_OK)
        
        data = json.loads(response.data)
        assert data['authenticated'] is True
        assert data['jira_username'] == TEST_JIRA_USERNAME

    @patch('requests.get')
    def test_auth_verify_success(self, mock_get, client):
        """Test POST /auth/verify with valid credentials."""
        mock_response = Mock()
        mock_response.status_code = HTTP_OK
        mock_response.json.return_value = MOCK_JIRA_USER_RESPONSE
        mock_get.return_value = mock_response
        
        response = client.post('/auth/verify', 
                             json={
                                 'jira_url': TEST_JIRA_URL,
                                 'username': TEST_JIRA_USERNAME,
                                 'password': TEST_JIRA_PASSWORD
                             })
        
        assert_json_response(response, HTTP_OK)
        data = json.loads(response.data)
        assert data['ok'] is True
        assert data['message'] == 'User verified'

    @patch('requests.get')
    def test_auth_verify_username_with_brackets(self, mock_get, client):
        """Test POST /auth/verify strips bracket content from username."""
        mock_response = Mock()
        mock_response.status_code = HTTP_OK
        mock_response.json.return_value = MOCK_JIRA_USER_RESPONSE
        mock_get.return_value = mock_response

        response = client.post('/auth/verify',
                             json={
                                 'jira_url': TEST_JIRA_URL,
                                 'username': f'{TEST_JIRA_USERNAME}[context]',
                                 'password': TEST_JIRA_PASSWORD
                             })

        # Route strips '[context]' → uses 'Frank' as username → verified OK
        assert_json_response(response, HTTP_OK)
        data = json.loads(response.data)
        assert data['ok'] is True

    @patch('requests.get')
    def test_auth_verify_url_normalization(self, mock_get, client):
        """Test POST /auth/verify URL normalization."""
        mock_response = Mock()
        mock_response.status_code = HTTP_OK
        mock_get.return_value = mock_response
        
        response = client.post('/auth/verify',
                             json={
                                 'jira_url': f'{TEST_JIRA_URL}/',
                                 'username': TEST_JIRA_USERNAME,
                                 'password': TEST_JIRA_PASSWORD
                             })
        
        # URL should be normalized (trailing slash removed)
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert not call_args[0][0].endswith('/')

    @patch('requests.get')
    def test_auth_verify_timeout(self, mock_get, client):
        """Test POST /auth/verify with timeout."""
        mock_response = Mock()
        mock_response.status_code = HTTP_OK
        mock_get.return_value = mock_response
        
        response = client.post('/auth/verify',
                             json={
                                 'jira_url': TEST_JIRA_URL,
                                 'username': TEST_JIRA_USERNAME,
                                 'password': TEST_JIRA_PASSWORD
                             })
        
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs['timeout'] == 10
