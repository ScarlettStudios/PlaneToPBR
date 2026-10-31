import os
import sys
import types
from unittest.mock import MagicMock

import pytest

# Add repo root
HERE = os.path.dirname(__file__)
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# --------------------------------------------------
# Mock bpy BEFORE importing the add-on modules
# --------------------------------------------------

mock_bpy = types.ModuleType("bpy")
mock_bpy.types = types.SimpleNamespace(Operator=object, Panel=object)
mock_bpy.props = types.SimpleNamespace(StringProperty=lambda **kwargs: None)
mock_bpy.utils = types.SimpleNamespace(
    register_class=lambda x: None, unregister_class=lambda x: None
)
mock_bpy.context = types.SimpleNamespace(window_manager=types.SimpleNamespace(windows=[]))
mock_bpy.ops = types.SimpleNamespace()
mock_bpy.app = types.SimpleNamespace(version=(4, 2, 0))

sys.modules["bpy"] = mock_bpy

from scripts import addon_runtime, extension_draw, operators, panels  # noqa: E402


@pytest.fixture
def pro_flag(monkeypatch):
    def set_flag(value):
        if value is None:
            monkeypatch.delenv(addon_runtime.PRO_ENV_VAR, raising=False)
        else:
            monkeypatch.setenv(addon_runtime.PRO_ENV_VAR, value)

    return set_flag


@pytest.fixture
def fake_bpy_utils(monkeypatch):
    utils = types.SimpleNamespace(register_class=MagicMock(), unregister_class=MagicMock())
    monkeypatch.setattr(operators, "bpy", types.SimpleNamespace(utils=utils))
    monkeypatch.setattr(operators, "_registered_classes", [])
    return utils


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, False), ("", False), ("0", False), ("no", False), ("1", True), (" TRUE ", True)],
)
def test_pro_enabled_reads_env(pro_flag, value, expected):
    pro_flag(value)

    assert addon_runtime.pro_enabled() is expected


def _registered(utils):
    return [call.args[0] for call in utils.register_class.call_args_list]


def test_register_skips_pro_operators_by_default(pro_flag, fake_bpy_utils):
    pro_flag(None)

    operators.register()

    assert _registered(fake_bpy_utils) == [operators.OBJECT_OT_import_plane_from_image]


def test_register_includes_pro_operators_when_enabled(pro_flag, fake_bpy_utils):
    pro_flag("1")

    operators.register()

    assert _registered(fake_bpy_utils) == [
        operators.OBJECT_OT_import_plane_from_image,
        *operators.PRO_CLASSES,
    ]


def test_unregister_mirrors_register_after_flag_change(pro_flag, fake_bpy_utils):
    pro_flag(None)
    operators.register()
    pro_flag("1")

    operators.unregister()

    unregistered = [call.args[0] for call in fake_bpy_utils.unregister_class.call_args_list]
    assert unregistered == [operators.OBJECT_OT_import_plane_from_image]


def _draw_panel():
    panel = panels.VIEW3D_PT_planetopbr_panel()
    panel.layout = MagicMock()
    context = MagicMock()
    context.preferences.addons = {}
    panel.draw(context)
    return panel.layout


def test_panel_hides_pro_button_by_default(pro_flag):
    pro_flag(None)

    layout = _draw_panel()

    layout.row.assert_not_called()
    drawn = [call.args[0] for call in layout.operator.call_args_list]
    assert drawn == ["object.import_plane_from_image"]


def test_panel_shows_pro_button_when_enabled(pro_flag):
    pro_flag("1")

    layout = _draw_panel()

    pro_row = layout.row.return_value
    assert pro_row.operator.call_args.args[0] == "object.import_plane_from_platform"
    assert pro_row.enabled is False


@pytest.mark.parametrize(("value", "hooked"), [(None, False), ("1", True)])
def test_extension_profile_box_follows_flag(monkeypatch, pro_flag, value, hooked):
    pro_flag(value)
    original = MagicMock()
    exui = types.SimpleNamespace(extension_draw_item=original)
    monkeypatch.setattr(extension_draw, "exui", exui)

    extension_draw.register()

    assert hasattr(exui, "extension_draw_item_original") is hooked
    assert (exui.extension_draw_item is original) is not hooked

    extension_draw.unregister()

    assert exui.extension_draw_item is original
