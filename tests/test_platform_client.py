import os
import sys
import json
import unittest
from unittest.mock import patch, mock_open, MagicMock

# Add repo root to sys.path
HERE = os.path.dirname(__file__)
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.platform_client import (
    PlatformClient,
    PlatformClientError,
    PlatformAuthError,
    PlatformHTTPError,
    _parse_error_response,
    _guess_mime_type,
)


class TestPlatformClient(unittest.TestCase):

    # ------------------------------------------------------------
    # Initialization Tests
    # ------------------------------------------------------------

    def test_init_default_values(self):
        """Test client initializes with default values."""
        client = PlatformClient()

        self.assertEqual(client.base_url, "https://api.scarlettstudios.com/v1")
        self.assertEqual(client.timeout, 60)
        self.assertIsNone(client.access_token)
        self.assertIsNone(client.refresh_token)

    def test_init_custom_values(self):
        """Test client initializes with custom values."""
        client = PlatformClient(
            base_url="https://custom.api.com/v2",
            timeout=120
        )

        self.assertEqual(client.base_url, "https://custom.api.com/v2")
        self.assertEqual(client.timeout, 120)

    def test_init_strips_trailing_slash(self):
        """Test that base URL trailing slash is removed."""
        client = PlatformClient(base_url="https://api.example.com/")
        self.assertEqual(client.base_url, "https://api.example.com")

    # ------------------------------------------------------------
    # Login Tests
    # ------------------------------------------------------------

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_login_success(self, mock_urlopen):
        """Test successful login stores tokens."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "access_token": "access_123",
            "refresh_token": "refresh_456"
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = PlatformClient()
        result = client.login("user@example.com", "password123")

        self.assertEqual(client.access_token, "access_123")
        self.assertEqual(client.refresh_token, "refresh_456")
        self.assertEqual(result["access_token"], "access_123")

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_login_missing_access_token(self, mock_urlopen):
        """Test login raises error when access_token missing."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "refresh_token": "refresh_456"
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = PlatformClient()

        with self.assertRaises(PlatformAuthError) as ctx:
            client.login("user@example.com", "password123")

        self.assertIn("missing access_token", str(ctx.exception))

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_login_network_error(self, mock_urlopen):
        """Test login handles network errors."""
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Network error")

        client = PlatformClient()

        with self.assertRaises(PlatformClientError):
            client.login("user@example.com", "password123")

    # ------------------------------------------------------------
    # Get Me Tests
    # ------------------------------------------------------------

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_get_me_success(self, mock_urlopen):
        """Test get_me returns user info."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "id": "user_123",
            "email": "user@example.com"
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = PlatformClient()
        client.access_token = "access_123"

        result = client.get_me()

        self.assertEqual(result["id"], "user_123")
        self.assertEqual(result["email"], "user@example.com")

    def test_get_me_without_token(self):
        """Test get_me raises error without access token."""
        client = PlatformClient()

        with self.assertRaises(PlatformAuthError) as ctx:
            client.get_me()

        self.assertIn("No access token", str(ctx.exception))

    # ------------------------------------------------------------
    # Refresh Token Tests
    # ------------------------------------------------------------

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_refresh_access_token_success(self, mock_urlopen):
        """Test refresh token updates access token."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "access_token": "new_access_789",
            "refresh_token": "refresh_999",
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = PlatformClient()
        client.refresh_token = "refresh_456"

        result = client.refresh_access_token()

        self.assertEqual(client.access_token, "new_access_789")
        self.assertEqual(client.refresh_token, "refresh_999")
        self.assertEqual(result["access_token"], "new_access_789")

    def test_refresh_access_token_no_refresh_token(self):
        """Test refresh raises error without refresh token."""
        client = PlatformClient()

        with self.assertRaises(PlatformAuthError) as ctx:
            client.refresh_access_token()

        self.assertIn("No refresh token", str(ctx.exception))

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_refresh_access_token_missing_access_token(self, mock_urlopen):
        """Test refresh raises error when response missing access_token."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"refresh_token": "refresh_999"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = PlatformClient()
        client.refresh_token = "refresh_456"

        with self.assertRaises(PlatformAuthError) as ctx:
            client.refresh_access_token()

        self.assertIn("missing access_token", str(ctx.exception))

    # ------------------------------------------------------------
    # Get Balance Tests
    # ------------------------------------------------------------

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_get_balance_success(self, mock_urlopen):
        """Test get_balance returns balance info."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "balance": 1000,
            "currency": "credits"
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = PlatformClient()
        client.access_token = "access_123"

        result = client.get_balance()

        self.assertEqual(result["balance"], 1000)
        self.assertEqual(result["currency"], "credits")

    # ------------------------------------------------------------
    # Create PBR Job Tests
    # ------------------------------------------------------------

    @patch("builtins.open", new_callable=mock_open, read_data=b"fake_image_data")
    @patch("scripts.platform_client.os.path.exists", return_value=True)
    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_create_pbr_job_success(self, mock_urlopen, mock_exists, mock_file):
        """Test create_pbr_job sends correct payload."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "job_id": "job_123",
            "status": "pending"
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = PlatformClient()
        client.access_token = "access_123"

        result = client.create_pbr_job(
            image_path="/fake/image.png",
            prompt="brick wall",
            output_format="png",
            return_mask=True,
            client_request_id="req_123"
        )

        self.assertEqual(result["job_id"], "job_123")
        self.assertEqual(result["status"], "pending")

    def test_create_pbr_job_file_not_found(self):
        """Test create_pbr_job raises error for missing file."""
        client = PlatformClient()
        client.access_token = "access_123"

        with self.assertRaises(PlatformClientError) as ctx:
            client.create_pbr_job(image_path="/nonexistent/file.png")

        self.assertIn("Input image not found", str(ctx.exception))

    @patch("builtins.open", new_callable=mock_open, read_data=b"fake_image_data")
    @patch("scripts.platform_client.os.path.exists", return_value=True)
    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_create_pbr_job_default_prompt(self, mock_urlopen, mock_exists, mock_file):
        """Test create_pbr_job handles empty prompt."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "job_id": "job_123"
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = PlatformClient()
        client.access_token = "access_123"

        result = client.create_pbr_job(image_path="/fake/image.png")

        self.assertEqual(result["job_id"], "job_123")

    # ------------------------------------------------------------
    # Get Job Status Tests
    # ------------------------------------------------------------

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_get_job_status_success(self, mock_urlopen):
        """Test get_job_status returns job status."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "job_id": "job_123",
            "status": "completed",
            "download_url": "https://example.com/result.zip"
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = PlatformClient()
        client.access_token = "access_123"

        result = client.get_job_status("job_123")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["download_url"], "https://example.com/result.zip")

    # ------------------------------------------------------------
    # Download Results Tests
    # ------------------------------------------------------------

    @patch("builtins.open", new_callable=mock_open)
    @patch("scripts.platform_client.os.makedirs")
    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_download_results_success(self, mock_urlopen, mock_makedirs, mock_file):
        """Test download_results saves file."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"zip_file_data"
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = PlatformClient()

        result = client.download_results(
            "https://example.com/result.zip",
            "/output/result.zip"
        )

        self.assertEqual(result, "/output/result.zip")
        mock_file().write.assert_called_once_with(b"zip_file_data")

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_download_results_http_error(self, mock_urlopen):
        """Test download_results handles HTTP errors."""
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError(
            url="https://example.com/result.zip",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None
        )

        client = PlatformClient()

        with self.assertRaises(PlatformHTTPError) as ctx:
            client.download_results(
                "https://example.com/result.zip",
                "/output/result.zip"
            )

        self.assertIn("DOWNLOAD_FAILED", str(ctx.exception))

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_download_results_timeout(self, mock_urlopen):
        """Test download_results handles timeout."""
        import socket
        mock_urlopen.side_effect = socket.timeout()

        client = PlatformClient()

        with self.assertRaises(PlatformClientError) as ctx:
            client.download_results(
                "https://example.com/result.zip",
                "/output/result.zip"
            )

        self.assertIn("timed out", str(ctx.exception))

    # ------------------------------------------------------------
    # Auto-Refresh Tests
    # ------------------------------------------------------------

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_auto_refresh_on_401(self, mock_urlopen):
        """Test automatic token refresh on 401 error."""
        from urllib.error import HTTPError

        # First call: 401 error
        http_error = HTTPError(
            url="https://api.example.com/auth/me",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None
        )
        http_error.read = MagicMock(return_value=json.dumps({
            "error": {"code": "UNAUTHORIZED", "message": "Token expired"}
        }).encode("utf-8"))

        # Second call (refresh): success
        refresh_response = MagicMock()
        refresh_response.read.return_value = json.dumps({
            "access_token": "new_access_789",
            "refresh_token": "refresh_999",
        }).encode("utf-8")
        refresh_response.decode.return_value = json.dumps({
            "access_token": "new_access_789",
            "refresh_token": "refresh_999",
        })

        # Third call (retry): success
        retry_response = MagicMock()
        retry_response.read.return_value = json.dumps({
            "id": "user_123"
        }).encode("utf-8")
        retry_response.decode.return_value = json.dumps({
            "id": "user_123"
        })

        # Setup context manager returns
        refresh_ctx = MagicMock()
        refresh_ctx.__enter__ = MagicMock(return_value=refresh_response)
        refresh_ctx.__exit__ = MagicMock(return_value=False)

        retry_ctx = MagicMock()
        retry_ctx.__enter__ = MagicMock(return_value=retry_response)
        retry_ctx.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [
            http_error,
            refresh_ctx,
            retry_ctx
        ]

        client = PlatformClient()
        client.access_token = "old_access_123"
        client.refresh_token = "refresh_456"

        result = client.get_me()

        self.assertEqual(client.access_token, "new_access_789")
        self.assertEqual(client.refresh_token, "refresh_999")
        self.assertEqual(result["id"], "user_123")

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_start_browser_login_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "session_id": "session_123",
            "authorize_url": "/login?bridge_session=session_123",
            "expires_in_seconds": 600,
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = PlatformClient(base_url="https://api.example.com/v1")
        result = client.start_browser_login(mode="register")

        self.assertEqual(result["session_id"], "session_123")
        self.assertEqual(
            result["authorize_url"],
            "https://api.example.com/login?bridge_session=session_123&mode=register",
        )

    # ------------------------------------------------------------
    # Error Response Parsing Tests
    # ------------------------------------------------------------

    def test_parse_error_response_with_error_object(self):
        """Test parsing error response with standard error object."""
        from urllib.error import HTTPError

        http_error = HTTPError(
            url="https://api.example.com/test",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=None
        )
        http_error.read = MagicMock(return_value=json.dumps({
            "error": {
                "code": "INVALID_INPUT",
                "message": "Invalid parameter",
                "request_id": "req_123"
            }
        }).encode("utf-8"))

        result = _parse_error_response(http_error)

        self.assertEqual(result["code"], "INVALID_INPUT")
        self.assertEqual(result["message"], "Invalid parameter")
        self.assertEqual(result["request_id"], "req_123")

    def test_parse_error_response_fallback(self):
        """Test parsing error response falls back to defaults."""
        from urllib.error import HTTPError

        http_error = HTTPError(
            url="https://api.example.com/test",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=None
        )
        http_error.read = MagicMock(return_value=b"")

        result = _parse_error_response(http_error)

        self.assertEqual(result["code"], "HTTP_ERROR")
        self.assertEqual(result["message"], "Internal Server Error")
        self.assertIsNone(result["request_id"])

    def test_parse_error_response_invalid_json(self):
        """Test parsing error response handles invalid JSON."""
        from urllib.error import HTTPError

        http_error = HTTPError(
            url="https://api.example.com/test",
            code=500,
            msg="Server Error",
            hdrs={},
            fp=None
        )
        http_error.read = MagicMock(return_value=b"Not JSON")

        result = _parse_error_response(http_error)

        self.assertEqual(result["code"], "HTTP_ERROR")
        self.assertEqual(result["message"], "Server Error")

    # ------------------------------------------------------------
    # MIME Type Guessing Tests
    # ------------------------------------------------------------

    def test_guess_mime_type_png(self):
        """Test MIME type detection for PNG."""
        self.assertEqual(_guess_mime_type("image.png"), "image/png")
        self.assertEqual(_guess_mime_type("IMAGE.PNG"), "image/png")

    def test_guess_mime_type_jpeg(self):
        """Test MIME type detection for JPEG."""
        self.assertEqual(_guess_mime_type("image.jpg"), "image/jpeg")
        self.assertEqual(_guess_mime_type("image.jpeg"), "image/jpeg")
        self.assertEqual(_guess_mime_type("IMAGE.JPEG"), "image/jpeg")

    def test_guess_mime_type_webp(self):
        """Test MIME type detection for WebP."""
        self.assertEqual(_guess_mime_type("image.webp"), "image/webp")

    def test_guess_mime_type_bmp(self):
        """Test MIME type detection for BMP."""
        self.assertEqual(_guess_mime_type("image.bmp"), "image/bmp")

    def test_guess_mime_type_tiff(self):
        """Test MIME type detection for TIFF."""
        self.assertEqual(_guess_mime_type("image.tif"), "image/tiff")
        self.assertEqual(_guess_mime_type("image.tiff"), "image/tiff")

    def test_guess_mime_type_default(self):
        """Test MIME type defaults to PNG for unknown extensions."""
        self.assertEqual(_guess_mime_type("image.xyz"), "image/png")
        self.assertEqual(_guess_mime_type("noextension"), "image/png")

    # ------------------------------------------------------------
    # Exception Types Tests
    # ------------------------------------------------------------

    def test_platform_http_error_attributes(self):
        """Test PlatformHTTPError stores all attributes."""
        error = PlatformHTTPError(
            status_code=404,
            code="NOT_FOUND",
            message="Resource not found",
            request_id="req_123"
        )

        self.assertEqual(error.status_code, 404)
        self.assertEqual(error.code, "NOT_FOUND")
        self.assertEqual(error.request_id, "req_123")
        self.assertIn("HTTP 404 NOT_FOUND", str(error))

    def test_platform_auth_error_inheritance(self):
        """Test PlatformAuthError is a PlatformClientError."""
        error = PlatformAuthError("Auth failed")
        self.assertIsInstance(error, PlatformClientError)
        self.assertIsInstance(error, RuntimeError)

    def test_platform_http_error_inheritance(self):
        """Test PlatformHTTPError is a PlatformClientError."""
        error = PlatformHTTPError(500, "ERROR", "Server error")
        self.assertIsInstance(error, PlatformClientError)
        self.assertIsInstance(error, RuntimeError)


if __name__ == "__main__":
    unittest.main()
