import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Add repo root
HERE = os.path.dirname(__file__)
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# --------------------------------------------------
# Mock bpy BEFORE importing operators
# --------------------------------------------------

mock_bpy = types.ModuleType("bpy")
mock_bpy.types = types.SimpleNamespace(Operator=object)
mock_bpy.props = types.SimpleNamespace(StringProperty=lambda **kwargs: None)
mock_bpy.utils = types.SimpleNamespace(register_class=lambda x: None,
                                       unregister_class=lambda x: None)
mock_bpy.context = types.SimpleNamespace(window_manager=types.SimpleNamespace(windows=[]))
mock_bpy.ops = types.SimpleNamespace(wm=types.SimpleNamespace(url_open=lambda **kwargs: None))

sys.modules["bpy"] = mock_bpy

from scripts.operators import (
    OBJECT_OT_import_plane_from_image,
    OBJECT_OT_import_plane_from_platform,
    PLANETOPBR_OT_platform_login,
    PLANETOPBR_OT_platform_cancel_login,
    PLANETOPBR_OT_platform_logout,
)


class TestOperators(unittest.TestCase):

    def _mock_context(self, image_path="fake.png"):
        context = MagicMock()
        context.scene.planetopbr_prompt = "brick"
        context.scene.planetopbr_image_path = image_path
        context.preferences.addons = {}

        context.window_manager.progress_begin = MagicMock()
        context.window_manager.progress_update = MagicMock()
        context.window_manager.progress_end = MagicMock()
        context.window_manager.event_timer_add = MagicMock(return_value="timer")
        context.window_manager.event_timer_remove = MagicMock()
        context.window_manager.modal_handler_add = MagicMock()

        context.window = MagicMock()
        return context

    def _add_preferences(self, context, **overrides):
        prefs = types.SimpleNamespace(
            platform_access_token="access_123",
            platform_refresh_token="refresh_456",
            platform_account_email="user@example.com",
            platform_plan_label="Free plan",
            platform_balance_tokens=0,
            platform_logged_in=True,
            platform_login_in_progress=False,
            platform_browser_session_id="",
        )

        for key, value in overrides.items():
            setattr(prefs, key, value)

        context.preferences.addons["scripts"] = types.SimpleNamespace(preferences=prefs)
        return prefs

    # --------------------------------------------------
    # 1️⃣ execute() no image guard
    # --------------------------------------------------

    def test_execute_no_image(self):
        op = OBJECT_OT_import_plane_from_image()
        context = self._mock_context(image_path="")

        op.report = MagicMock()

        result = op.execute(context)

        self.assertEqual(result, {'CANCELLED'})
        op.report.assert_called_once()

    # --------------------------------------------------
    # 2️⃣ modal() HF error branch
    # --------------------------------------------------

    def test_modal_hf_error(self):
        op = OBJECT_OT_import_plane_from_image()
        context = self._mock_context()

        op._done = True
        op._error_message = "HF failed"
        op._textures = None
        op._timer = "timer"
        op.report = MagicMock()

        event = MagicMock()
        event.type = "TIMER"

        result = op.modal(context, event)

        self.assertEqual(result, {'CANCELLED'})
        op.report.assert_called_once()

    # --------------------------------------------------
    # 3️⃣ modal() success branch
    # --------------------------------------------------

    @patch("scripts.operators.import_plane_from_image")
    def test_modal_success(self, mock_import):
        op = OBJECT_OT_import_plane_from_image()
        context = self._mock_context()

        op._done = True
        op._error_message = None
        op._textures = {"diffuse": "x"}
        op._timer = "timer"
        op.report = MagicMock()

        event = MagicMock()
        event.type = "TIMER"

        result = op.modal(context, event)

        self.assertEqual(result, {'FINISHED'})
        mock_import.assert_called_once()
        op.report.assert_called_once()

    # --------------------------------------------------
    # 4️⃣ modal() no textures failure branch
    # --------------------------------------------------

    def test_modal_no_textures(self):
        op = OBJECT_OT_import_plane_from_image()
        context = self._mock_context()

        op._done = True
        op._error_message = None
        op._textures = None
        op._timer = "timer"
        op.report = MagicMock()

        event = MagicMock()
        event.type = "TIMER"

        result = op.modal(context, event)

        self.assertEqual(result, {'CANCELLED'})
        op.report.assert_called_once()

    # --------------------------------------------------
    # 5️⃣ execute() unexpected exception
    # --------------------------------------------------

    def test_execute_unexpected_exception(self):
        op = OBJECT_OT_import_plane_from_image()
        context = self._mock_context()

        # Trigger exception in execute
        context.scene = None
        op.report = MagicMock()

        result = op.execute(context)

        self.assertEqual(result, {'CANCELLED'})
        op.report.assert_called_once()
        args = op.report.call_args[0]
        self.assertEqual(args[0], {'ERROR'})
        self.assertIn("Unexpected error", args[1])

    # --------------------------------------------------
    # 6️⃣ modal() import exception
    # --------------------------------------------------

    @patch("scripts.operators.import_plane_from_image")
    def test_modal_import_exception(self, mock_import):
        mock_import.side_effect = Exception("Import failed")

        op = OBJECT_OT_import_plane_from_image()
        context = self._mock_context()

        op._done = True
        op._error_message = None
        op._textures = {"diffuse": "x"}
        op._timer = "timer"
        op.report = MagicMock()

        event = MagicMock()
        event.type = "TIMER"

        result = op.modal(context, event)

        self.assertEqual(result, {'CANCELLED'})
        op.report.assert_called_once()
        args = op.report.call_args[0]
        self.assertEqual(args[0], {'ERROR'})
        self.assertIn("Import failed", args[1])

    # --------------------------------------------------
    # 7️⃣ modal() non-TIMER event
    # --------------------------------------------------

    def test_modal_non_timer_event(self):
        op = OBJECT_OT_import_plane_from_image()
        context = self._mock_context()

        op._done = False
        op._timer = "timer"

        event = MagicMock()
        event.type = "MOUSEMOVE"

        result = op.modal(context, event)

        self.assertEqual(result, {'PASS_THROUGH'})

    # --------------------------------------------------
    # 8️⃣ modal() processing in progress
    # --------------------------------------------------

    def test_modal_processing_in_progress(self):
        op = OBJECT_OT_import_plane_from_image()
        context = self._mock_context()

        op._done = False
        op._progress = 10
        op._timer = "timer"

        event = MagicMock()
        event.type = "TIMER"

        result = op.modal(context, event)

        self.assertEqual(result, {'PASS_THROUGH'})
        context.window_manager.progress_update.assert_called_once()
        # Progress should have incremented
        self.assertEqual(op._progress, 12)

    # --------------------------------------------------
    # 9️⃣ _run_hf() success path
    # --------------------------------------------------

    @patch("scripts.operators.get_project_texture_dir")
    @patch("scripts.operators.call_hf_pbr")
    def test_run_hf_success(self, mock_call_hf, mock_get_dir):
        mock_get_dir.return_value = "/fake/textures"
        mock_call_hf.return_value = {"diffuse": "path/to/diffuse.png"}

        op = OBJECT_OT_import_plane_from_image()
        op._run_hf("fake.png", "brick")

        self.assertTrue(op._done)
        self.assertIsNone(op._error_message)
        self.assertEqual(op._textures, {"diffuse": "path/to/diffuse.png"})
        mock_call_hf.assert_called_once_with(
            image_path="fake.png",
            output_dir="/fake/textures",
            prompt="brick"
        )

    # --------------------------------------------------
    # 🔟 _run_hf() exception handling
    # --------------------------------------------------

    @patch("scripts.operators.get_project_texture_dir")
    @patch("scripts.operators.call_hf_pbr")
    def test_run_hf_exception(self, mock_call_hf, mock_get_dir):
        mock_get_dir.return_value = "/fake/textures"
        mock_call_hf.side_effect = Exception("HF API error")

        op = OBJECT_OT_import_plane_from_image()
        op._run_hf("fake.png", "brick")

        self.assertTrue(op._done)
        self.assertEqual(op._error_message, "HF API error")
        self.assertIsNone(op._textures)

    @patch("scripts.operators.PlatformClient")
    def test_platform_login_operator_success(self, mock_client_cls):
        context = self._mock_context()
        prefs = self._add_preferences(
            context,
            platform_access_token="",
            platform_refresh_token="",
            platform_logged_in=False,
        )

        client = mock_client_cls.return_value
        client.start_browser_login.return_value = {
            "session_id": "session_123",
            "authorize_url": "https://example.com/login",
        }

        op = PLANETOPBR_OT_platform_login()
        op.mode = "login"
        op.report = MagicMock()

        result = op.execute(context)

        self.assertEqual(result, {'RUNNING_MODAL'})
        client.start_browser_login.assert_called_once_with(mode="login")
        self.assertEqual(prefs.platform_browser_session_id, "session_123")
        self.assertTrue(prefs.platform_login_in_progress)
        context.window_manager.modal_handler_add.assert_called_once()

    def test_platform_logout_operator_clears_login_state(self):
        context = self._mock_context()
        prefs = self._add_preferences(context)

        op = PLANETOPBR_OT_platform_logout()
        op.report = MagicMock()

        result = op.execute(context)

        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(prefs.platform_access_token, "")
        self.assertEqual(prefs.platform_refresh_token, "")
        self.assertEqual(prefs.platform_account_email, "")
        self.assertEqual(prefs.platform_plan_label, "Free plan")
        self.assertEqual(prefs.platform_balance_tokens, 0)
        self.assertEqual(prefs.platform_browser_session_id, "")
        self.assertFalse(prefs.platform_logged_in)

    @patch("scripts.operators.PlatformClient")
    def test_platform_cancel_login_clears_browser_state(self, mock_client_cls):
        context = self._mock_context()
        prefs = self._add_preferences(
            context,
            platform_login_in_progress=True,
            platform_browser_session_id="session_123",
        )

        op = PLANETOPBR_OT_platform_cancel_login()
        op.report = MagicMock()

        result = op.execute(context)

        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(prefs.platform_browser_session_id, "")
        self.assertFalse(prefs.platform_login_in_progress)
        mock_client_cls.return_value.cancel_browser_login.assert_called_once_with("session_123")

    def test_platform_execute_requires_login(self):
        context = self._mock_context()
        self._add_preferences(
            context,
            platform_access_token="",
            platform_refresh_token="",
            platform_logged_in=False,
        )

        op = OBJECT_OT_import_plane_from_platform()
        op.report = MagicMock()

        result = op.execute(context)

        self.assertEqual(result, {'CANCELLED'})
        op.report.assert_called_once()
        self.assertIn("login required", op.report.call_args[0][1].lower())

    @patch("scripts.operators.call_platform_pbr")
    @patch("scripts.operators.get_project_texture_dir")
    def test_run_platform_success_uses_saved_tokens(self, mock_get_dir, mock_call_platform):
        mock_get_dir.return_value = "/fake/textures"
        mock_call_platform.return_value = (
            {"diffuse": "path/to/diffuse.png"},
            {"access_token": "refreshed_access", "refresh_token": "refresh_456"},
        )

        op = OBJECT_OT_import_plane_from_platform()
        op._run_platform_api("fake.png", "brick", "access_123", "refresh_456")

        self.assertTrue(op._platform_done)
        self.assertEqual(op._textures, {"diffuse": "path/to/diffuse.png"})
        self.assertEqual(op._updated_auth_state["access_token"], "refreshed_access")
        mock_call_platform.assert_called_once_with(
            image_path="fake.png",
            output_dir="/fake/textures",
            prompt="brick",
            access_token="access_123",
            refresh_token="refresh_456",
        )

    def test_platform_modal_persists_refreshed_tokens(self):
        context = self._mock_context()
        prefs = self._add_preferences(context)

        op = OBJECT_OT_import_plane_from_platform()
        op._platform_done = True
        op._error_message = None
        op._textures = {"diffuse": "x"}
        op._updated_auth_state = {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
        }
        op._timer = "timer"
        op.report = MagicMock()

        event = MagicMock()
        event.type = "TIMER"

        with patch("scripts.operators.import_plane_from_image") as mock_import:
            result = op.modal(context, event)

        self.assertEqual(result, {'FINISHED'})
        mock_import.assert_called_once()
        self.assertEqual(prefs.platform_access_token, "new_access")
        self.assertEqual(prefs.platform_refresh_token, "new_refresh")
        self.assertTrue(prefs.platform_logged_in)

    @patch("scripts.operators.PlatformClient")
    def test_platform_login_modal_approved(self, mock_client_cls):
        context = self._mock_context()
        prefs = self._add_preferences(
            context,
            platform_access_token="",
            platform_refresh_token="",
            platform_logged_in=False,
            platform_login_in_progress=True,
            platform_browser_session_id="session_123",
            platform_account_email="",
        )

        client = mock_client_cls.return_value
        client.get_browser_login_status.return_value = {
            "status": "approved",
            "access_token": "new_access",
            "refresh_token": "new_refresh",
        }
        client.get_me.return_value = {"email": "artist@example.com"}
        client.get_balance.return_value = {"balance_tokens": 42}

        op = PLANETOPBR_OT_platform_login()
        op.mode = "login"
        op._client = client
        op._timer = "timer"
        op.report = MagicMock()

        event = MagicMock()
        event.type = "TIMER"

        result = op.modal(context, event)

        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(prefs.platform_access_token, "new_access")
        self.assertEqual(prefs.platform_refresh_token, "new_refresh")
        self.assertEqual(prefs.platform_account_email, "artist@example.com")
        self.assertEqual(prefs.platform_plan_label, "Free plan")
        self.assertEqual(prefs.platform_balance_tokens, 42)
        self.assertEqual(prefs.platform_browser_session_id, "")
        self.assertFalse(prefs.platform_login_in_progress)


if __name__ == "__main__":
    unittest.main()
