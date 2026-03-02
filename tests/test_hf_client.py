import os
import sys

# Add repo root (parent of PlaneToPBR/) to sys.path
HERE = os.path.dirname(__file__)
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import json
import unittest
from unittest.mock import patch, mock_open, MagicMock

from scripts.hf_client import (
    _resolve_fn_index,
    _join_queue,
    _poll_queue,
    _download_results,
    _download_file,
)


class TestHFClient(unittest.TestCase):

    @patch("scripts.hf_client._download_results")
    @patch("scripts.hf_client._poll_queue")
    @patch("scripts.hf_client._join_queue")
    @patch("scripts.hf_client._upload_file")
    @patch("scripts.hf_client._resolve_fn_index")
    @patch("scripts.hf_client.os.path.exists", return_value=True)
    @patch("builtins.open", new_callable=mock_open, read_data=b"imagebytes")
    def test_call_hf_pbr_success(
            self,
            mock_file,
            mock_exists,
            mock_resolve,
            mock_upload,
            mock_join,
            mock_poll,
            mock_download,
    ):
        mock_resolve.return_value = 0
        mock_upload.return_value = "uploaded_path"
        mock_join.return_value = "event123"
        mock_poll.return_value = [{"url": "d"}, {"url": "n"}, {"url": "r"}, {"url": "m"}]
        mock_download.return_value = {"depth": "d", "normal": "n", "roughness": "r", "mask": "m",
                                      "diffuse": "diffuse.png"}

        from scripts.hf_client import call_hf_pbr

        result = call_hf_pbr("fake.png", prompt="brick")

        self.assertIn("depth", result)
        self.assertEqual(result["diffuse"], "diffuse.png")

        mock_resolve.assert_called_once()
        mock_upload.assert_called_once()
        mock_join.assert_called_once()
        mock_poll.assert_called_once()
        mock_download.assert_called_once()

    @patch("scripts.hf_client.urllib.request.urlopen")
    def test_resolve_fn_index_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "dependencies": [
                {"api_name": "foo"},
                {"api_name": "predict"},
            ]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = _resolve_fn_index("predict")
        self.assertEqual(result, 1)

    @patch("scripts.hf_client.urllib.request.urlopen")
    def test_resolve_fn_index_not_found(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "dependencies": [{"api_name": "foo"}]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with self.assertRaises(RuntimeError):
            _resolve_fn_index("missing")

    @patch("scripts.hf_client.urllib.request.urlopen")
    def test_join_queue_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "event_id": "evt123"
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        payload = {"data": [], "fn_index": 0, "session_hash": "abc"}
        result = _join_queue(payload)

        self.assertEqual(result, "evt123")

    @patch("scripts.hf_client.urllib.request.urlopen")
    def test_poll_queue_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.__iter__.return_value = [
            b'data: {"msg": "process_started"}\n',
            b'data: {"msg": "process_completed", "output": {"data": ["a", "b"]}}\n',
        ]
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = _poll_queue("abc")
        self.assertEqual(result, ["a", "b"])

    @patch("scripts.hf_client._download_file")
    @patch("scripts.hf_client.tempfile.gettempdir")
    def test_download_results(self, mock_tmp, mock_download):
        mock_tmp.return_value = "/tmp"
        mock_download.side_effect = [
            "/tmp/depth.png",
            "/tmp/normal.png",
            "/tmp/roughness.png",
            "/tmp/mask.png",
        ]

        output = [
            {"url": "d"},
            {"url": "n"},
            {"url": "r"},
            {"url": "m"},
        ]

        textures = _download_results(output)

        self.assertEqual(textures["depth"], "/tmp/depth.png")
        self.assertEqual(textures["normal"], "/tmp/normal.png")
        self.assertEqual(textures["roughness"], "/tmp/roughness.png")
        self.assertEqual(textures["mask"], "/tmp/mask.png")

        # Optional: just validate diffuse points into TEXTURE_DIR
        self.assertTrue(textures["diffuse"].endswith("diffuse.png"))

        self.assertEqual(mock_download.call_count, 4)

    @patch("builtins.open", new_callable=mock_open)
    @patch("scripts.hf_client.urllib.request.urlopen")
    def test_download_file(self, mock_urlopen, mock_file):
        mock_response = MagicMock()
        mock_response.read.return_value = b"filedata"
        mock_urlopen.return_value.__enter__.return_value = mock_response

        path = _download_file("http://x", "/tmp/x.png")

        self.assertEqual(path, "/tmp/x.png")
        mock_file().write.assert_called_once_with(b"filedata")


if __name__ == "__main__":
    unittest.main()