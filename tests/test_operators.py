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
mock_bpy.utils = types.SimpleNamespace(register_class=lambda x: None,
                                       unregister_class=lambda x: None)

sys.modules["bpy"] = mock_bpy

from scripts.operators import OBJECT_OT_import_plane_from_image


class TestOperators(unittest.TestCase):

    def _mock_context(self, image_path="fake.png"):
        context = MagicMock()
        context.scene.planetopbr_prompt = "brick"
        context.scene.planetopbr_image_path = image_path

        context.window_manager.progress_begin = MagicMock()
        context.window_manager.progress_update = MagicMock()
        context.window_manager.progress_end = MagicMock()
        context.window_manager.event_timer_add = MagicMock(return_value="timer")
        context.window_manager.event_timer_remove = MagicMock()
        context.window_manager.modal_handler_add = MagicMock()

        context.window = MagicMock()
        return context

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


if __name__ == "__main__":
    unittest.main()