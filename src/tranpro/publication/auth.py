"""Desktop OAuth with refresh tokens stored in the operating-system keychain."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, cast

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from tranpro.paths import AppPaths

SCOPES = (
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
)
_KEYRING_SERVICE = "tranpro.google"
_KEYRING_ACCOUNT = "oauth-token"


class GoogleAuthError(RuntimeError):
    """Raised when Google credentials cannot be configured or refreshed."""


def install_client_credentials(source: Path, paths: AppPaths | None = None) -> Path:
    app_paths = paths or AppPaths.for_user()
    source_path = source.expanduser().resolve()
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GoogleAuthError(f"Could not read OAuth credentials: {error}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("installed"), dict):
        raise GoogleAuthError("Google OAuth credentials must be for a Desktop app")
    app_paths.create_private_directories()
    destination = app_paths.google_credentials_file
    try:
        shutil.copyfile(source_path, destination)
        destination.chmod(0o600)
    except OSError as error:
        raise GoogleAuthError(f"Could not store OAuth credentials: {error}") from error
    return destination


def authorize(paths: AppPaths | None = None) -> Credentials:
    app_paths = paths or AppPaths.for_user()
    if not app_paths.google_credentials_file.is_file():
        raise GoogleAuthError(
            "Google OAuth client is not configured; run "
            "`tp google setup --credentials FILE`"
        )
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(app_paths.google_credentials_file), scopes=SCOPES
        )
        credentials = cast(
            Credentials, flow.run_local_server(port=0, open_browser=True)
        )
        _store_token(credentials)
        return credentials
    except Exception as error:
        raise GoogleAuthError(f"Google authorization failed: {error}") from error


def load_credentials(paths: AppPaths | None = None) -> Credentials:
    app_paths = paths or AppPaths.for_user()
    token = keyring.get_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
    if token is None:
        raise GoogleAuthError("Google is not authorized; run `tp google authorize`")
    try:
        info = json.loads(token)
        credentials = cast(
            Credentials,
            Credentials.from_authorized_user_info(info, scopes=SCOPES),
        )
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            _store_token(credentials)
    except Exception as error:
        raise GoogleAuthError(
            f"Could not load Google authorization: {error}"
        ) from error
    if not credentials.valid:
        raise GoogleAuthError("Google authorization is invalid; authorize again")
    if not app_paths.google_credentials_file.is_file():
        raise GoogleAuthError("Google OAuth client credentials are missing; run setup")
    return credentials


def disconnect() -> None:
    try:
        keyring.delete_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
    except keyring.errors.PasswordDeleteError:
        return


def _store_token(credentials: Any) -> None:
    keyring.set_password(
        _KEYRING_SERVICE,
        _KEYRING_ACCOUNT,
        credentials.to_json(),
    )
