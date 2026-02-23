import os
import sys
import types

# Add repo root to sys.path
HERE = os.path.dirname(__file__)
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# --------------------------------------------------
# Mock bpy BEFORE importing utils
# --------------------------------------------------

mock_bpy = types.ModuleType("bpy")
sys.modules["bpy"] = mock_bpy

# Now import utils safely
from scripts import utils


def test_apply_pbr_textures_calls_expected_helpers(monkeypatch):
    """
    Ensure apply_pbr_textures orchestrates helper calls correctly.
    """

    # Fake material + node data
    fake_mat = object()
    fake_nodes = object()
    fake_links = object()
    fake_bsdf = object()
    fake_mapping = object()

    # Track calls
    called = {
        "diffuse": False,
        "roughness": False,
        "normal": False,
    }

    # Mock base material creator
    def mock_create_base_material():
        return fake_mat, fake_nodes, fake_links, fake_bsdf, fake_mapping

    # Mock helpers
    def mock_add_diffuse(*args, **kwargs):
        called["diffuse"] = True

    def mock_add_roughness(*args, **kwargs):
        called["roughness"] = True

    def mock_add_normal(*args, **kwargs):
        called["normal"] = True

    monkeypatch.setattr(utils, "_create_base_material", mock_create_base_material)
    monkeypatch.setattr(utils, "_add_diffuse", mock_add_diffuse)
    monkeypatch.setattr(utils, "_add_roughness", mock_add_roughness)
    monkeypatch.setattr(utils, "_add_normal", mock_add_normal)

    textures = {
        "diffuse": "diffuse.png",
        "roughness": "rough.png",
        "mask": "mask.png",
        "normal": "normal.png",
    }

    result = utils.apply_pbr_textures(None, textures)

    assert result is fake_mat
    assert called["diffuse"] is True
    assert called["roughness"] is True
    assert called["normal"] is True

def test_apply_pbr_textures_skips_missing_channels(monkeypatch):
    fake_mat = object()
    fake_nodes = object()
    fake_links = object()
    fake_bsdf = object()
    fake_mapping = object()

    monkeypatch.setattr(
        utils,
        "_create_base_material",
        lambda: (fake_mat, fake_nodes, fake_links, fake_bsdf, fake_mapping),
    )

    monkeypatch.setattr(utils, "_add_diffuse", lambda *a, **k: (_ for _ in ()).throw(Exception("Should not be called")))
    monkeypatch.setattr(utils, "_add_roughness", lambda *a, **k: (_ for _ in ()).throw(Exception("Should not be called")))
    monkeypatch.setattr(utils, "_add_normal", lambda *a, **k: (_ for _ in ()).throw(Exception("Should not be called")))

    textures = {}  # no channels

    result = utils.apply_pbr_textures(None, textures)
