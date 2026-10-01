# auth/credentials.py
"""Jira credential verification."""
import requests
from requests.auth import HTTPBasicAuth
from urllib.parse import urlparse, urlunparse

DEFAULT_TIMEOUT = 10


def normalize_jira_url(url: str) -> str:
    """
    Normalize Jira base URL. For Jira Cloud (.atlassian.net), strip any context path
    since Cloud REST API lives at the root domain. For Server, keep path intact.
    """
    url = url.rstrip("/")
    if ".atlassian.net" in url.lower():
        parsed = urlparse(url)
        return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    return url


def verify_jira_credentials(jira_url: str, username: str, password: str) -> bool:
    """
    Validates Jira credentials by calling /rest/api/latest/myself.
    Returns True if credentials work, otherwise False.
    """
    jira_url = normalize_jira_url(jira_url)
    url = f"{jira_url}/rest/api/latest/myself"
    print(f"[DEBUG] Verifying credentials at: {url}")

    try:
        resp = requests.get(url, auth=HTTPBasicAuth(username, password), timeout=DEFAULT_TIMEOUT)
        print(f"[DEBUG] Credential verification status: {resp.status_code}")
        return resp.status_code == 200
    except requests.RequestException as e:
        print(f"[DEBUG] Credential verification failed: {e}")
        return False
