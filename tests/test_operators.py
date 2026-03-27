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
mock_bpy.types = types.SimpleNamespace(Operator=object, AddonPreferences=object)
mock_bpy.props = types.SimpleNamespace(
    BoolProperty=lambda **kwargs: None,
    StringProperty=lambda **kwargs: None,
)
mock_bpy.utils = types.SimpleNamespace(register_class=lambda x: None,
                                       unregister_class=lambda x: None)

sys.modules["bpy"] = mock_bpy
sys.modules["bpy.props"] = mock_bpy.props

from scripts.operators import (
    OBJECT_OT_import_plane_from_image,
    OBJECT_OT_import_plane_from_platform,
    PLANETOPBR_OT_login_platform,
    PLANETOPBR_OT_logout_platform,
)


class TestOperators(unittest.TestCase):

    def _mock_context(self, image_path="fake.png"):
        context = MagicMock()
        context.scene.planetopbr_prompt = "brick"
        context.scene.planetopbr_image_path = image_path
        context.preferences = MagicMock()

        context.window_manager.progress_begin = MagicMock()
        context.window_manager.progress_update = MagicMock()
        context.window_manager.progress_end = MagicMock()
        context.window_manager.event_timer_add = MagicMock(return_value="timer")
        context.window_manager.event_timer_remove = MagicMock()
        context.window_manager.modal_handler_add = MagicMock()

        context.window = MagicMock()
        return context

    def _mock_preferences(self, logged_in=False, email="pro@example.com", password="secret"):
        return types.SimpleNamespace(
            planetopbr_logged_in=logged_in,
            planetopbr_email=email,
            planetopbr_password=password,
            planetopbr_access_token="access-token" if logged_in else "",
            planetopbr_refresh_token="refresh-token" if logged_in else "",
            planetopbr_login_status="Not logged in",
        )

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

    @patch("scripts.operators.get_addon_preferences")
    @patch("scripts.operators._restore_platform_session")
    def test_platform_execute_requires_login(self, mock_restore_session, mock_get_prefs):
        from scripts.platform_client import PlatformAuthError

        op = OBJECT_OT_import_plane_from_platform()
        context = self._mock_context()
        mock_get_prefs.return_value = self._mock_preferences(logged_in=False)
        mock_restore_session.side_effect = PlatformAuthError("Log in from Preferences.")
        op.report = MagicMock()

        result = op.execute(context)

        self.assertEqual(result, {'CANCELLED'})
        self.assertIn("Log in", op.report.call_args[0][1])

    @patch("scripts.operators.threading.Thread")
    @patch("scripts.operators.get_addon_preferences")
    @patch("scripts.operators._restore_platform_session")
    def test_platform_execute_starts_thread_when_logged_in(self, mock_restore_session, mock_get_prefs, mock_thread):
        op = OBJECT_OT_import_plane_from_platform()
        context = self._mock_context()
        preferences = self._mock_preferences(logged_in=True)
        mock_get_prefs.return_value = preferences
        mock_restore_session.return_value = object()
        mock_thread.return_value = MagicMock(start=MagicMock())
        op.report = MagicMock()

        result = op.execute(context)

        self.assertEqual(result, {'RUNNING_MODAL'})
        mock_thread.assert_called_once()
        context.window_manager.progress_begin.assert_called_once()

    @patch("scripts.operators.PlatformClient")
    @patch("scripts.operators.get_addon_preferences")
    def test_login_operator_success(self, mock_get_prefs, mock_client_cls):
        preferences = self._mock_preferences(logged_in=False)
        mock_get_prefs.return_value = preferences
        mock_client = MagicMock()
        mock_client.access_token = "new-access"
        mock_client.refresh_token = "new-refresh"
        mock_client_cls.return_value = mock_client
        op = PLANETOPBR_OT_login_platform()
        op.report = MagicMock()

        result = op.execute(self._mock_context())

        self.assertEqual(result, {'FINISHED'})
        self.assertTrue(preferences.planetopbr_logged_in)
        self.assertEqual(preferences.planetopbr_login_status, "Logged in as pro@example.com")
        self.assertEqual(preferences.planetopbr_access_token, "new-access")
        self.assertEqual(preferences.planetopbr_refresh_token, "new-refresh")
        mock_client.login.assert_called_once_with(email="pro@example.com", password="secret")

    @patch("scripts.operators.get_addon_preferences")
    def test_logout_operator_clears_login_state(self, mock_get_prefs):
        preferences = self._mock_preferences(logged_in=True)
        mock_get_prefs.return_value = preferences
        op = PLANETOPBR_OT_logout_platform()
        op.report = MagicMock()

        result = op.execute(self._mock_context())

        self.assertEqual(result, {'FINISHED'})
        self.assertFalse(preferences.planetopbr_logged_in)
        self.assertEqual(preferences.planetopbr_login_status, "Not logged in")
        self.assertEqual(preferences.planetopbr_access_token, "")
        self.assertEqual(preferences.planetopbr_refresh_token, "")

    @patch("scripts.operators.PlatformClient")
    def test_restore_platform_session_uses_saved_tokens(self, mock_client_cls):
        from scripts.operators import _restore_platform_session

        preferences = self._mock_preferences(logged_in=True)
        mock_client = MagicMock()
        mock_client.access_token = "access-token"
        mock_client.refresh_token = "refresh-token"
        mock_client_cls.return_value = mock_client

        result = _restore_platform_session(preferences)

        self.assertIs(result, mock_client)
        mock_client.get_me.assert_called_once()
        mock_client.login.assert_not_called()

    @patch("scripts.operators.PlatformClient")
    def test_restore_platform_session_falls_back_to_login(self, mock_client_cls):
        from scripts.operators import _restore_platform_session
        from scripts.platform_client import PlatformAuthError

        preferences = self._mock_preferences(logged_in=True)
        expired_client = MagicMock()
        expired_client.access_token = "access-token"
        expired_client.refresh_token = "refresh-token"
        expired_client.get_me.side_effect = PlatformAuthError("expired")

        login_client = MagicMock()
        login_client.access_token = "fresh-access"
        login_client.refresh_token = "fresh-refresh"

        mock_client_cls.side_effect = [expired_client, login_client]

        result = _restore_platform_session(preferences)

        self.assertIs(result, login_client)
        login_client.login.assert_called_once_with(email="pro@example.com", password="secret")
        self.assertTrue(preferences.planetopbr_logged_in)
        self.assertEqual(preferences.planetopbr_access_token, "fresh-access")
        self.assertEqual(preferences.planetopbr_refresh_token, "fresh-refresh")


if __name__ == "__main__":
    unittest.main()
