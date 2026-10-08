"""
Exports resume drafts to the user's Google Drive as Google Docs.

Layout in My Drive:
    career_pilot_resume/<job title>/<company> – Draft <n> – Resume
                                    <company> – Draft <n> – Side projects
Exporting the same draft again updates its docs in place, so re-exports don't pile up copies.
The resume is uploaded as a styled one-page .docx (resume_docx.py); side projects as Markdown.

Auth: OAuth with the drive.file scope, so the app only sees the folders and files it created.
  - CLIENT_FILE is the app's OAuth client (Google Cloud Console, type "Desktop app"). It ships
    with CareerPilot: Google doesn't treat a desktop client's secret as confidential.
  - The user signs in from the UI: GET /drive/login (apis/reposetories/drive.py) sends the
    browser to Google's consent page via `login_url`, Google returns to GET /drive/callback,
    and `finish_login` saves the user's token to TOKEN_FILE (kept local, in the gitignored Docs/).

Orchestration:
  POST /agents/resume/drafts/{draft_id}/drive and the resume chat's ```drive block
  (apis/reposetories/agents.py) call `export_draft`.
"""

import io
import json
import os
import re
import secrets
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from agents.resume_builder.resume_docx import DOCX_MIME, markdown_to_docx

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CLIENT_FILE = Path(os.getenv("GOOGLE_OAUTH_CLIENT_FILE", Path(__file__).with_name("google_client.json")))
TOKEN_FILE = Path(os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "Docs/google/token.json"))
ROOT_FOLDER = "career_pilot_resume"
FOLDER_MIME = "application/vnd.google-apps.folder"
DOC_MIME = "application/vnd.google-apps.document"
DOC_LABELS = {"resume": "Resume", "side_projects": "Side projects"}
LOGIN_TTL = 600  # seconds a started sign-in stays valid

# Folder find-or-create isn't atomic on Drive; serialize exports so two at once don't make twin folders.
_EXPORT_LOCK = threading.Lock()
# Sign-ins waiting for Google's callback: state -> (flow holding the PKCE verifier, started at).
_PENDING: dict[str, tuple[Flow, float]] = {}


class DriveUnavailable(RuntimeError):
    """CareerPilot has no OAuth client (CLIENT_FILE is missing), so Drive can't be used at all."""


class DriveNotConnected(RuntimeError):
    """The user hasn't signed in to Google yet, or the sign-in expired or was revoked."""


def available() -> bool:
    return CLIENT_FILE.exists()


def _credentials() -> Credentials:
    if not available():
        raise DriveUnavailable(f"Google Drive export isn't set up: {CLIENT_FILE} is missing.")
    if not TOKEN_FILE.exists():
        raise DriveNotConnected("Google Drive isn't connected yet.")
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            TOKEN_FILE.unlink(missing_ok=True)
            raise DriveNotConnected("The Google Drive sign-in expired; connect again.")
        TOKEN_FILE.write_text(creds.to_json())
        return creds
    TOKEN_FILE.unlink(missing_ok=True)
    raise DriveNotConnected("The Google Drive sign-in is invalid; connect again.")


def _drive():
    """Drive v3 client (its discovery doc ships with the library, so building it is cheap)."""
    return build("drive", "v3", credentials=_credentials(), cache_discovery=False)


# ---------- sign-in ----------

def login_url(redirect_uri: str) -> str:
    """Google's consent page for the drive.file scope; Google then sends the browser to
    redirect_uri with ?code&state. Asks for offline access so the sign-in survives restarts."""
    if not available():
        raise DriveUnavailable(f"Google Drive export isn't set up: {CLIENT_FILE} is missing.")
    now = time.time()
    for state in [s for s, (_, at) in _PENDING.items() if now - at > LOGIN_TTL]:
        del _PENDING[state]
    flow = Flow.from_client_secrets_file(str(CLIENT_FILE), SCOPES, redirect_uri=redirect_uri)
    state = secrets.token_urlsafe(24)
    url, _ = flow.authorization_url(access_type="offline", prompt="consent", state=state)
    _PENDING[state] = (flow, now)
    return url


def finish_login(state: str, code: str) -> None:
    """Swaps the callback's code for the user's token and saves it to TOKEN_FILE.
    Raises ValueError for an unknown or expired state."""
    flow, at = _PENDING.pop(state, (None, 0))
    if flow is None or time.time() - at > LOGIN_TTL:
        raise ValueError("This sign-in link expired; start again from CareerPilot.")
    flow.fetch_token(code=code)
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(flow.credentials.to_json())


def status() -> dict:
    """{"available", "connected", "email"}: whether Drive can be used, is signed in, and as whom."""
    if not available():
        return {"available": False, "connected": False, "email": None}
    try:
        about = _drive().about().get(fields="user(emailAddress)").execute()
    except DriveNotConnected:
        return {"available": True, "connected": False, "email": None}
    return {"available": True, "connected": True, "email": about["user"].get("emailAddress")}


def disconnect() -> None:
    """Revokes the user's token with Google (best effort) and deletes it."""
    if TOKEN_FILE.exists():
        token = json.loads(TOKEN_FILE.read_text()).get("refresh_token")
        if token:
            try:
                urllib.request.urlopen(urllib.request.Request(
                    "https://oauth2.googleapis.com/revoke", data=urllib.parse.urlencode({"token": token}).encode(),
                    headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=10)
            except OSError:
                pass  # deleting the token still disconnects CareerPilot
    TOKEN_FILE.unlink(missing_ok=True)


# ---------- export ----------

def _q(value: str) -> str:
    """Escapes a value for a Drive query string literal."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _clean(name: str) -> str:
    """A Drive-friendly file or folder name: no slashes or control characters, single spaces."""
    return re.sub(r"[/\\\x00-\x1f]", "-", re.sub(r"\s+", " ", name)).strip() or "untitled"


def _find(drive, name: str, parent: str, mime: str):
    q = f"name = '{_q(name)}' and '{parent}' in parents and mimeType = '{mime}' and trashed = false"
    files = drive.files().list(q=q, spaces="drive", fields="files(id, name, webViewLink)", pageSize=1).execute()
    return files["files"][0] if files["files"] else None


def _folder(drive, name: str, parent: str = "root") -> str:
    """Id of the folder `name` under `parent`, created if missing."""
    found = _find(drive, name, parent, FOLDER_MIME)
    if found:
        return found["id"]
    return drive.files().create(body={"name": name, "mimeType": FOLDER_MIME, "parents": [parent]},
                                fields="id").execute()["id"]


def export_markdown(job_title: str, name: str, markdown: str) -> dict:
    """Saves markdown as the Google Doc career_pilot_resume/<job_title>/<name>, converted by Drive
    (headings, lists, bold...). Replaces that doc's content if it already exists.
    @return: {"id", "name", "url"}"""
    return _export(job_title, name, markdown.encode(), "text/markdown")


def export_resume(job_title: str, name: str, markdown: str) -> dict:
    """Like export_markdown, but styled as a compact one-page resume (resume_docx.py): uploaded
    as a .docx, which Drive converts keeping its margins, fonts, rules and right-aligned dates."""
    return _export(job_title, name, markdown_to_docx(markdown), DOCX_MIME)


def _export(job_title: str, name: str, data: bytes, mimetype: str) -> dict:
    """Uploads data as the Google Doc career_pilot_resume/<job_title>/<name> (Drive converts it
    from mimetype), replacing that doc's content if it already exists."""
    drive = _drive()
    name = _clean(name)
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mimetype, resumable=False)
    fields = "id, name, webViewLink"
    with _EXPORT_LOCK:
        folder = _folder(drive, _clean(job_title), _folder(drive, ROOT_FOLDER))
        existing = _find(drive, name, folder, DOC_MIME)
        if existing:
            doc = drive.files().update(fileId=existing["id"], media_body=media, fields=fields).execute()
        else:
            doc = drive.files().create(body={"name": name, "mimeType": DOC_MIME, "parents": [folder]},
                                       media_body=media, fields=fields).execute()
    return {"id": doc["id"], "name": doc["name"], "url": doc["webViewLink"]}


def export_draft(draft: dict, number: int, targets: list[str]) -> list[dict]:
    """Exports a draft's docs (targets: "resume" / "side_projects") to Drive.
    draft is a db.dbOps.get_draft dict; number is its "Draft N" for its job (oldest = 1).
    @return: one {"target", "id", "name", "url"} per exported doc; empty docs are skipped"""
    job_title = draft.get("position") or "Untitled position"
    company = draft.get("company_name") or "Unknown company"
    out = []
    for target in dict.fromkeys(targets):  # dedupe, keep order
        if target in DOC_LABELS and draft[target].strip():
            export = export_resume if target == "resume" else export_markdown
            doc = export(job_title, f"{company} – Draft {number} – {DOC_LABELS[target]}", draft[target])
            out.append({"target": target, **doc})
    return out
