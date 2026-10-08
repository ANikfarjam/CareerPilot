import html
import logging
import typing

import fastapi
from fastapi.responses import HTMLResponse, RedirectResponse

from agents.resume_builder import drive
from apis.schemas import DriveStatus

DRIVE_ROUTER: typing.Final = fastapi.APIRouter(prefix="/drive", tags=["drive"])

logger = logging.getLogger(__name__)

# Shown in the sign-in popup once Google sends it back; the frontend notices the new
# connection by polling GET /drive/status, so the page only has to close itself.
_DONE_PAGE = """<!doctype html><meta charset="utf-8"><title>CareerPilot · Google Drive</title>
<body style="font-family:system-ui,sans-serif;display:grid;place-items:center;height:90vh;margin:0">
<p style="text-align:center;max-width:24rem">{message}<br><br>You can close this window.</p>
<script>{script}</script></body>"""


@DRIVE_ROUTER.get("/status", response_model=DriveStatus)
def get_drive_status():
    """Whether resumes can be exported to Google Drive: available (CareerPilot ships an OAuth
    client), connected (the user signed in) and the signed-in account's email."""
    return drive.status()


@DRIVE_ROUTER.get("/login", include_in_schema=False)
def drive_login(request: fastapi.Request):
    """Starts the Google sign-in: redirects the browser (the frontend opens this in a popup) to
    Google's consent page, which returns to GET /drive/callback. 503 if Drive isn't available."""
    try:
        return RedirectResponse(drive.login_url(str(request.url_for("drive_callback"))))
    except drive.DriveUnavailable as e:
        raise fastapi.HTTPException(status_code=503, detail=str(e))


@DRIVE_ROUTER.get("/callback", include_in_schema=False, response_class=HTMLResponse)
def drive_callback(state: str = "", code: str = "", error: str = ""):
    """Where Google sends the browser after the consent page: saves the user's token, then shows
    a page that closes the popup."""
    if error or not code:
        message = "Google Drive wasn't connected" + (f" ({error})." if error else ".")
        return HTMLResponse(_DONE_PAGE.format(message=html.escape(message), script=""), status_code=400)
    try:
        drive.finish_login(state, code)
    except ValueError as e:
        return HTMLResponse(_DONE_PAGE.format(message=html.escape(str(e)), script=""), status_code=400)
    except Exception as e:
        logger.exception("Google Drive sign-in failed")
        return HTMLResponse(_DONE_PAGE.format(message=html.escape(f"Sign-in failed: {e}"), script=""), status_code=500)
    return HTMLResponse(_DONE_PAGE.format(message="Google Drive is connected to CareerPilot.",
                                          script="setTimeout(() => window.close(), 800)"))


@DRIVE_ROUTER.delete("", response_model=DriveStatus)
def disconnect_drive():
    """Signs CareerPilot out of Google Drive: revokes and deletes the saved token.
    Docs already exported stay in the user's Drive."""
    drive.disconnect()
    return drive.status()
