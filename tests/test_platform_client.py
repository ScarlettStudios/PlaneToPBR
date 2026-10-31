import base64
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from http.client import IncompleteRead
from unittest.mock import MagicMock, mock_open, patch
from urllib.error import HTTPError, URLError

# Add repo root to sys.path
HERE = os.path.dirname(__file__)
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.platform_client import (
    PlatformAuthError,
    PlatformClient,
    PlatformClientError,
    PlatformHTTPError,
    _guess_mime_type,
    _parse_error_response,
)


class TestPlatformClient(unittest.TestCase):
    # ------------------------------------------------------------
    # Initialization Tests
    # ------------------------------------------------------------

    def test_init_default_values(self):
        """Test client initializes with default values."""
        client = PlatformClient()

        self.assertEqual(client.base_url, "http://127.0.0.1:8001")
        self.assertEqual(client.timeout, 60)
        self.assertIsNone(client.access_token)
        self.assertIsNone(client.refresh_token)

    def test_init_custom_values(self):
        """Test client initializes with custom values."""
        client = PlatformClient(base_url="https://custom.api.com/v2", timeout=120)

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
        mock_response.read.return_value = json.dumps(
            {"access_token": "access_123", "refresh_token": "refresh_456"}
        ).encode("utf-8")
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
        mock_response.read.return_value = json.dumps({"refresh_token": "refresh_456"}).encode(
            "utf-8"
        )
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
        mock_response.read.return_value = json.dumps(
            {"id": "user_123", "email": "user@example.com"}
        ).encode("utf-8")
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
        mock_response.read.return_value = json.dumps(
            {
                "access_token": "new_access_789",
                "refresh_token": "refresh_999",
            }
        ).encode("utf-8")
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
        mock_response.read.return_value = json.dumps({"refresh_token": "refresh_999"}).encode(
            "utf-8"
        )
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
        mock_response.read.return_value = json.dumps({"balance_tokens": 1000}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = PlatformClient()
        client.access_token = "access_123"

        result = client.get_balance()

        self.assertEqual(result["balance_tokens"], 1000)

    # ------------------------------------------------------------
    # Create PBR Job Tests
    # ------------------------------------------------------------

    @patch("builtins.open", new_callable=mock_open, read_data=b"fake_image_data")
    @patch("scripts.platform_client.os.path.exists", return_value=True)
    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_create_pbr_job_success(self, mock_urlopen, mock_exists, mock_file):
        """Test create_pbr_job sends correct payload."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {"job_id": "job_123", "status": "pending"}
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = PlatformClient()
        client.access_token = "access_123"

        result = client.create_pbr_job(
            image_path="/fake/image.png",
            prompt="brick wall",
            output_format="png",
            return_mask=True,
            client_request_id="req_123",
        )

        self.assertEqual(result["job_id"], "job_123")
        self.assertEqual(result["status"], "pending")
        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.get_header("Authorization"), "Bearer access_123")
        self.assertEqual(
            payload,
            {
                "input_image": {
                    "filename": "image.png",
                    "content_type": "image/png",
                    "data_base64": base64.b64encode(b"fake_image_data").decode("ascii"),
                },
                "prompt": "brick wall",
                "options": {"return_mask": True, "output_format": "png"},
                "client_request_id": "req_123",
            },
        )

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
        mock_response.read.return_value = json.dumps({"job_id": "job_123"}).encode("utf-8")
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
        mock_response.read.return_value = json.dumps(
            {
                "job_id": "job_123",
                "status": "completed",
                "download_url": "https://example.com/result.zip",
            }
        ).encode("utf-8")
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

        result = client.download_results("https://example.com/result.zip", "/output/result.zip")

        self.assertEqual(result, "/output/result.zip")
        mock_file().write.assert_called_once_with(b"zip_file_data")

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_download_results_http_error(self, mock_urlopen):
        """Test download_results handles HTTP errors."""
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError(
            url="https://example.com/result.zip", code=404, msg="Not Found", hdrs={}, fp=None
        )

        client = PlatformClient()

        with self.assertRaises(PlatformHTTPError) as ctx:
            client.download_results("https://example.com/result.zip", "/output/result.zip")

        self.assertIn("DOWNLOAD_FAILED", str(ctx.exception))

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_download_results_timeout(self, mock_urlopen):
        """Test download_results handles timeout."""
        mock_urlopen.side_effect = TimeoutError()

        client = PlatformClient()

        with self.assertRaises(PlatformClientError) as ctx:
            client.download_results("https://example.com/result.zip", "/output/result.zip")

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
            url="https://api.example.com/auth/me", code=401, msg="Unauthorized", hdrs={}, fp=None
        )
        http_error.read = MagicMock(
            return_value=json.dumps(
                {"error": {"code": "UNAUTHORIZED", "message": "Token expired"}}
            ).encode("utf-8")
        )

        # Second call (refresh): success
        refresh_response = MagicMock()
        refresh_response.read.return_value = json.dumps(
            {
                "access_token": "new_access_789",
                "refresh_token": "refresh_999",
            }
        ).encode("utf-8")
        refresh_response.decode.return_value = json.dumps(
            {
                "access_token": "new_access_789",
                "refresh_token": "refresh_999",
            }
        )

        # Third call (retry): success
        retry_response = MagicMock()
        retry_response.read.return_value = json.dumps({"id": "user_123"}).encode("utf-8")
        retry_response.decode.return_value = json.dumps({"id": "user_123"})

        # Setup context manager returns
        refresh_ctx = MagicMock()
        refresh_ctx.__enter__ = MagicMock(return_value=refresh_response)
        refresh_ctx.__exit__ = MagicMock(return_value=False)

        retry_ctx = MagicMock()
        retry_ctx.__enter__ = MagicMock(return_value=retry_response)
        retry_ctx.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [http_error, refresh_ctx, retry_ctx]

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
        mock_response.read.return_value = json.dumps(
            {
                "session_id": "session_123",
                "authorize_url": "/login?bridge_session=session_123",
                "expires_in_seconds": 600,
            }
        ).encode("utf-8")
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
            url="https://api.example.com/test", code=400, msg="Bad Request", hdrs={}, fp=None
        )
        http_error.read = MagicMock(
            return_value=json.dumps(
                {
                    "error": {
                        "code": "INVALID_INPUT",
                        "message": "Invalid parameter",
                        "request_id": "req_123",
                    }
                }
            ).encode("utf-8")
        )

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
            fp=None,
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
            url="https://api.example.com/test", code=500, msg="Server Error", hdrs={}, fp=None
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
            status_code=404, code="NOT_FOUND", message="Resource not found", request_id="req_123"
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


class TestPlatformClientRegression(unittest.TestCase):
    @staticmethod
    def _response(body):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = body
        return response

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_invalid_success_responses_are_client_errors(self, urlopen):
        for body in (b"[]", b"null", b'"text"', b"42", b"{", b"\xff"):
            with self.subTest(body=body):
                urlopen.return_value = self._response(body)
                with self.assertRaises(PlatformClientError):
                    PlatformClient().login("test@example.com", "password")

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_interrupted_reads_are_client_errors(self, urlopen):
        client = PlatformClient()
        for action in (
            lambda: client.login("test@example.com", "password"),
            lambda: client.download_results("/results.zip", "/unused.zip"),
        ):
            response = self._response(b"")
            response.__enter__.return_value.read.side_effect = IncompleteRead(b"partial", 20)
            urlopen.return_value = response
            with self.assertRaises(PlatformClientError) as caught:
                action()
            self.assertIsInstance(caught.exception.__cause__, IncompleteRead)

    def test_absolute_signup_url_preserves_query_and_fragment(self):
        client = PlatformClient()
        with patch.object(
            client,
            "_request_json",
            return_value={"authorize_url": "https://example.com/login?session=123&mode=login#form"},
        ):
            result = client.start_browser_login(mode="register")
        self.assertEqual(
            result["authorize_url"], "https://example.com/login?session=123&mode=register#form"
        )

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_browser_status_and_cancel_are_public(self, urlopen):
        urlopen.return_value = self._response(b"{}")
        client = PlatformClient(base_url="https://example.com/v1")
        client.access_token = "private-token"
        client.get_browser_login_status("session_123")
        client.cancel_browser_login("session_123")
        requests = [call.args[0] for call in urlopen.call_args_list]
        self.assertEqual(
            [request.full_url for request in requests],
            [
                "https://example.com/v1/auth/browser/status/session_123",
                "https://example.com/v1/auth/browser/cancel/session_123",
            ],
        )
        self.assertEqual([request.get_method() for request in requests], ["GET", "POST"])
        self.assertTrue(all(request.get_header("Authorization") is None for request in requests))

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_public_download_urls_never_send_tokens(self, urlopen):
        urlopen.return_value = self._response(b"zip-data")
        client = PlatformClient(base_url="https://example.com/v1")
        client.access_token = "private-token"
        client.refresh_token = "private-refresh-token"
        with tempfile.TemporaryDirectory() as root:
            for url, expected in (
                ("/results.zip", "https://example.com/results.zip"),
                ("results.zip", "https://example.com/v1/results.zip"),
                (
                    "https://cdn.example.com/results.zip?signature=abc",
                    "https://cdn.example.com/results.zip?signature=abc",
                ),
            ):
                with self.subTest(url=url):
                    destination = os.path.join(root, "nested", "result.zip")
                    self.assertEqual(client.download_results(url, destination), destination)
                    request = urlopen.call_args.args[0]
                    self.assertEqual(request.full_url, expected)
                    self.assertIsNone(request.get_header("Authorization"))
                    with open(destination, "rb") as source:
                        self.assertEqual(source.read(), b"zip-data")

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_download_write_and_network_errors(self, urlopen):
        urlopen.side_effect = URLError("offline")
        with self.assertRaises(PlatformClientError):
            PlatformClient().download_results("https://example.com/result.zip", "result.zip")
        urlopen.side_effect = None
        urlopen.return_value = self._response(b"zip-data")
        with patch("scripts.platform_client.os.makedirs", side_effect=PermissionError("denied")):
            with self.assertRaises(PlatformClientError):
                PlatformClient().download_results("https://example.com/result.zip", "result.zip")

    def test_input_directory_and_permissions_are_client_errors(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(PlatformClientError):
                PlatformClient().create_pbr_job(root)
        with (
            patch("scripts.platform_client.os.path.exists", return_value=True),
            patch("builtins.open", side_effect=PermissionError("denied")),
        ):
            with self.assertRaises(PlatformClientError):
                PlatformClient().create_pbr_job("image.png")

    def test_extract_nested_archive(self):
        with tempfile.TemporaryDirectory() as root:
            archive = os.path.join(root, "result.zip")
            destination = os.path.join(root, "textures")
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("maps/", b"")
                output.writestr("maps/base_color.png", b"image-data")
            extracted = PlatformClient().extract_results(archive, destination)
            self.assertEqual(extracted, [os.path.join(destination, "maps", "base_color.png")])
            with open(extracted[0], "rb") as source:
                self.assertEqual(source.read(), b"image-data")

    def test_invalid_and_corrupt_archives_are_client_errors(self):
        with tempfile.TemporaryDirectory() as root:
            archive = os.path.join(root, "result.zip")
            destination = os.path.join(root, "textures")
            with open(archive, "wb") as output:
                output.write(b"not-a-zip")
            with self.assertRaises(PlatformClientError):
                PlatformClient().extract_results(archive, destination)
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as output:
                output.writestr("base_color.png", b"good-image-data")
            with open(archive, "rb") as source:
                data = source.read().replace(b"good-image-data", b"bad!-image-data", 1)
            with open(archive, "wb") as output:
                output.write(data)
            self.assertTrue(zipfile.is_zipfile(archive))
            with self.assertRaises(PlatformClientError) as caught:
                PlatformClient().extract_results(archive, destination)
            self.assertIsInstance(caught.exception.__cause__, zipfile.BadZipFile)
            with patch(
                "scripts.platform_client.os.makedirs", side_effect=PermissionError("denied")
            ):
                with self.assertRaises(PlatformClientError):
                    PlatformClient().extract_results(archive, destination)

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_retry_stops_after_second_401(self, urlopen):
        client = PlatformClient()
        client.access_token, client.refresh_token = "old-access", "old-refresh"
        urlopen.side_effect = [
            HTTPError("https://example.com", 401, "Unauthorized", {}, io.BytesIO(b"{}")),
            self._response(b'{"access_token":"new-access","refresh_token":"new-refresh"}'),
            HTTPError("https://example.com", 401, "Unauthorized", {}, io.BytesIO(b"{}")),
        ]
        with self.assertRaises(PlatformAuthError):
            client.get_me()
        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual(client.refresh_token, "new-refresh")

    @patch("scripts.platform_client.urllib.request.urlopen")
    def test_failed_refresh_does_not_retry_original_request(self, urlopen):
        client = PlatformClient()
        client.access_token, client.refresh_token = "old-access", "old-refresh"
        urlopen.side_effect = [
            HTTPError("https://example.com", 401, "Unauthorized", {}, io.BytesIO(b"{}")),
            HTTPError("https://example.com", 401, "Unauthorized", {}, io.BytesIO(b"{}")),
        ]
        with self.assertRaises(PlatformAuthError):
            client.get_me()
        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(client.refresh_token, "old-refresh")


if __name__ == "__main__":
    unittest.main()
