import base64
import json
import os
import socket
import urllib.error
import urllib.request
from typing import Dict, Optional


DEFAULT_TIMEOUT = 60
DEFAULT_BASE_URL = os.getenv("PLANETOPBR_API_BASE_URL", "http://127.0.0.1:8001")


class PlatformClientError(RuntimeError):
    """Base client exception for backend API failures."""


class PlatformAuthError(PlatformClientError):
    """Raised when authentication fails or tokens are missing/expired."""


class PlatformHTTPError(PlatformClientError):
    """Raised for non-auth HTTP failures with parsed backend error details."""

    def __init__(self, status_code: int, code: str, message: str, request_id: Optional[str] = None):
        self.status_code = status_code
        self.code = code
        self.request_id = request_id
        super().__init__(f"HTTP {status_code} {code}: {message}")


class PlatformClient:
    """
    Thin client for ScarlettStudios backend API.

    Security notes:
    - Passwords are sent only over HTTPS/TLS during login.
    - Passwords are never persisted in this client.
    - Use access/refresh tokens for all subsequent requests.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: int = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None

    # ------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------

    def login(self, email: str, password: str) -> Dict:
        payload = {"email": email, "password": password}
        response = self._request_json("POST", "/auth/login", payload=payload, auth_required=False)

        access_token = response.get("access_token")
        if not access_token:
            raise PlatformAuthError("Login response missing access_token.")

        self.access_token = access_token
        self.refresh_token = response.get("refresh_token")
        return response

    def start_browser_login(self, mode: str = "login") -> Dict:
        response = self._request_json("POST", "/auth/browser/start", auth_required=False)
        authorize_url = response.get("authorize_url")
        if authorize_url and not authorize_url.startswith("http"):
            separator = "&" if "?" in authorize_url else "?"
            authorize_url = f"{self._public_base_url()}{authorize_url}{separator}mode={mode}"
            response["authorize_url"] = authorize_url
        return response

    def get_browser_login_status(self, session_id: str) -> Dict:
        return self._request_json("GET", f"/auth/browser/status/{session_id}", auth_required=False)

    def cancel_browser_login(self, session_id: str) -> Dict:
        return self._request_json("POST", f"/auth/browser/cancel/{session_id}", auth_required=False)

    def get_me(self) -> Dict:
        return self._request_json("GET", "/auth/me", auth_required=True)

    def refresh_access_token(self) -> Dict:
        """Refresh and store a new access token using the refresh token."""
        if not self.refresh_token:
            raise PlatformAuthError("No refresh token available. Login is required.")

        response = self._request_json(
            "POST",
            "/auth/refresh",
            payload={"refresh_token": self.refresh_token},
            auth_required=False,
        )

        access_token = response.get("access_token")
        if not access_token:
            raise PlatformAuthError("Refresh response missing access_token.")

        self.access_token = access_token
        self.refresh_token = response.get("refresh_token", self.refresh_token)
        return response

    def get_balance(self) -> Dict:
        """Fetch authenticated user's token balance."""
        return self._request_json("GET", "/wallet", auth_required=True)

    def create_pbr_job(
        self,
        image_path: str,
        prompt: str = "",
        output_format: str = "png",
        return_mask: bool = True,
        client_request_id: Optional[str] = None,
    ) -> Dict:
        """
        Create a backend-managed PBR generation job.

        Sends the image as base64 according to the contract.
        """
        if not os.path.exists(image_path):
            raise PlatformClientError(f"Input image not found: {image_path}")

        filename = os.path.basename(image_path)
        mime_type = _guess_mime_type(filename)

        with open(image_path, "rb") as infile:
            raw = infile.read()

        payload = {
            "input_image": {
                "filename": filename,
                "content_type": mime_type,
                "data_base64": base64.b64encode(raw).decode("ascii"),
            },
            "prompt": prompt or "",
            "options": {
                "return_mask": bool(return_mask),
                "output_format": output_format,
            },
        }

        if client_request_id:
            payload["client_request_id"] = client_request_id

        return self._request_json("POST", "/jobs/pbr", payload=payload, auth_required=True)

    def get_job_status(self, job_id: str) -> Dict:
        """Fetch status for a previously created job."""
        return self._request_json("GET", f"/jobs/{job_id}", auth_required=True)

    def download_results(self, download_url: str, output_zip_path: str) -> str:
        """
        Download job result zip from signed URL (or backend download endpoint).

        Returns the saved zip path.
        """
        try:
            req = urllib.request.Request(download_url, method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = resp.read()
        except urllib.error.HTTPError as e:
            raise PlatformHTTPError(e.code, "DOWNLOAD_FAILED", f"Failed to download results: {e.reason}")
        except urllib.error.URLError as e:
            raise PlatformClientError(f"Network error downloading results: {e.reason}")
        except socket.timeout:
            raise PlatformClientError("Result download timed out.")

        os.makedirs(os.path.dirname(output_zip_path) or ".", exist_ok=True)
        with open(output_zip_path, "wb") as outfile:
            outfile.write(data)

        return output_zip_path

    # ------------------------------------------------------------
    # Internal request helpers
    # ------------------------------------------------------------

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Optional[Dict] = None,
        auth_required: bool = True,
        retry_on_401: bool = True,
    ) -> Dict:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None

        headers = {"Content-Type": "application/json"}
        if auth_required:
            if not self.access_token:
                raise PlatformAuthError("No access token available. Login is required.")
            headers["Authorization"] = f"Bearer {self.access_token}"

        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}

        except urllib.error.HTTPError as e:
            parsed = _parse_error_response(e)

            if e.code == 401 and auth_required and retry_on_401 and self.refresh_token:
                self.refresh_access_token()
                return self._request_json(
                    method,
                    path,
                    payload=payload,
                    auth_required=auth_required,
                    retry_on_401=False,
                )

            if e.code == 401:
                raise PlatformAuthError(parsed["message"])

            raise PlatformHTTPError(
                status_code=e.code,
                code=parsed["code"],
                message=parsed["message"],
                request_id=parsed.get("request_id"),
            )

        except urllib.error.URLError as e:
            raise PlatformClientError(f"Network error calling backend API: {e.reason}")
        except socket.timeout:
            raise PlatformClientError("Backend API request timed out.")
        except json.JSONDecodeError:
            raise PlatformClientError("Invalid JSON response from backend API.")

    def _public_base_url(self) -> str:
        if self.base_url.endswith("/v1"):
            return self.base_url[:-3]
        return self.base_url


def _parse_error_response(http_error: urllib.error.HTTPError) -> Dict[str, Optional[str]]:
    """Parse standard backend error envelope; fallback to generic values."""
    fallback = {
        "code": "HTTP_ERROR",
        "message": http_error.reason or "Request failed",
        "request_id": None,
    }

    try:
        body = http_error.read().decode("utf-8")
        parsed = json.loads(body) if body else {}
    except Exception:
        return fallback

    error_obj = parsed.get("error") if isinstance(parsed, dict) else None
    if not isinstance(error_obj, dict):
        return fallback

    return {
        "code": error_obj.get("code", fallback["code"]),
        "message": error_obj.get("message", fallback["message"]),
        "request_id": error_obj.get("request_id"),
    }


def _guess_mime_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".bmp"):
        return "image/bmp"
    if lower.endswith(".tif") or lower.endswith(".tiff"):
        return "image/tiff"
    return "image/png"
