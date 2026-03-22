import os
import sys
import types
import pytest
from unittest.mock import patch, mock_open

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

def test_import_plane_invalid_payload(monkeypatch):
    from scripts import utils

    with pytest.raises(RuntimeError, match="Invalid textures payload"):
        utils.import_plane_from_image(None)

    with pytest.raises(RuntimeError, match="Invalid textures payload"):
        utils.import_plane_from_image([])

def test_import_plane_missing_diffuse(monkeypatch):
    from scripts import utils

    with pytest.raises(RuntimeError, match="Diffuse texture missing"):
        utils.import_plane_from_image({})

def test_import_plane_image_load_failure(monkeypatch):
    from scripts import utils

    class FakeImages:
        def load(self, path):
            raise Exception("load failed")

    monkeypatch.setattr(utils.bpy, "data", types.SimpleNamespace(images=FakeImages()), raising=False, )

    textures = {"diffuse": "fake.png"}

    with pytest.raises(RuntimeError, match="Failed to load diffuse image"):
        utils.import_plane_from_image(textures)

def test_import_plane_zero_height(monkeypatch):
    from scripts import utils

    class FakeImage:
        size = (1024, 0)

    class FakeImages:
        def load(self, path):
            return FakeImage()

    monkeypatch.setattr(utils.bpy,"data",types.SimpleNamespace(images=FakeImages()),raising=False,)

    textures = {"diffuse": "fake.png"}

    with pytest.raises(RuntimeError, match="Invalid image dimensions"):
        utils.import_plane_from_image(textures)

def test_import_plane_success_minimal(monkeypatch):
    class FakeImage:
        size = (1024, 1024)

    class FakeImages:
        def load(self, path):
            return FakeImage()

    class FakePlane:
        def __init__(self):
            self.scale = None
            self.name = None
            self.data = types.SimpleNamespace(materials=[])

    fake_plane = FakePlane()

    class FakeOps:
        class mesh:
            @staticmethod
            def primitive_plane_add(**kwargs):
                pass

        class object:
            @staticmethod
            def shade_smooth():
                pass

    monkeypatch.setattr(utils.bpy,"data",types.SimpleNamespace(images=FakeImages()),raising=False,)
    monkeypatch.setattr(utils.bpy, "ops", FakeOps, raising=False)
    monkeypatch.setattr(utils.bpy, "context", types.SimpleNamespace(active_object=fake_plane), raising=False)

    monkeypatch.setattr(utils, "apply_pbr_textures", lambda *a, **k: object())
    monkeypatch.setattr(utils, "add_modifiers", lambda *a, **k: None)

    textures = {"diffuse": "fake.png"}

    utils.import_plane_from_image(textures)

    assert fake_plane.name == "PBR_Plane"

def test_get_project_texture_dir_no_file(monkeypatch):
    """Test that get_project_texture_dir raises error when project not saved."""
    monkeypatch.setattr(utils.bpy, "data", types.SimpleNamespace(filepath=""), raising=False)

    with pytest.raises(RuntimeError, match="Please save the Blender project"):
        utils.get_project_texture_dir()

def test_get_project_texture_dir_success(monkeypatch, tmp_path):
    """Test that get_project_texture_dir creates and returns correct path."""
    project_dir = str(tmp_path / "project")
    os.makedirs(project_dir, exist_ok=True)

    monkeypatch.setattr(utils.bpy, "data", types.SimpleNamespace(filepath="/fake/file.blend"), raising=False)
    monkeypatch.setattr(utils.bpy, "path", types.SimpleNamespace(abspath=lambda x: project_dir), raising=False)

    result = utils.get_project_texture_dir()

    expected = os.path.join(project_dir, "PlaneToPBR_textures")
    assert result == expected
    assert os.path.exists(expected)

def test_import_plane_create_failure(monkeypatch):
    """Test that import_plane_from_image handles plane creation failure."""
    class FakeImage:
        size = (1024, 1024)

    class FakeImages:
        def load(self, path):
            return FakeImage()

    class FakeOps:
        class mesh:
            @staticmethod
            def primitive_plane_add(**kwargs):
                raise Exception("Failed to create plane")

    monkeypatch.setattr(utils.bpy, "data", types.SimpleNamespace(images=FakeImages()), raising=False)
    monkeypatch.setattr(utils.bpy, "ops", FakeOps, raising=False)

    textures = {"diffuse": "fake.png"}

    with pytest.raises(RuntimeError, match="Failed to create plane"):
        utils.import_plane_from_image(textures)

def test_import_plane_material_assignment_failure(monkeypatch):
    """Test that import_plane_from_image handles material assignment failure."""
    class FakeImage:
        size = (1024, 1024)

    class FakeImages:
        def load(self, path):
            return FakeImage()

    class FakeMaterials:
        def append(self, mat):
            raise Exception("Material assignment failed")

    class FakePlane:
        def __init__(self):
            self.scale = None
            self.name = None
            self.data = types.SimpleNamespace(materials=FakeMaterials())

    fake_plane = FakePlane()

    class FakeOps:
        class mesh:
            @staticmethod
            def primitive_plane_add(**kwargs):
                pass

        class object:
            @staticmethod
            def shade_smooth():
                pass

    monkeypatch.setattr(utils.bpy, "data", types.SimpleNamespace(images=FakeImages()), raising=False)
    monkeypatch.setattr(utils.bpy, "ops", FakeOps, raising=False)
    monkeypatch.setattr(utils.bpy, "context", types.SimpleNamespace(active_object=fake_plane), raising=False)

    monkeypatch.setattr(utils, "apply_pbr_textures", lambda *a, **k: object())
    monkeypatch.setattr(utils, "add_modifiers", lambda *a, **k: None)

    textures = {"diffuse": "fake.png"}

    with pytest.raises(RuntimeError, match="Failed to assign material"):
        utils.import_plane_from_image(textures)

def test_add_modifiers_success(monkeypatch):
    """Test that add_modifiers adds subdivision and displacement modifiers."""
    modifiers_added = []

    class FakeModifier:
        def __init__(self, name):
            self.name = name
            self.subdivision_type = None
            self.levels = None
            self.render_levels = None
            self.texture = None
            self.texture_coords = None
            self.strength = None
            self.mid_level = None

    class FakeModifiers:
        def __getitem__(self, key):
            mod = FakeModifier(key)
            modifiers_added.append(mod)
            return mod

    class FakePlane:
        modifiers = FakeModifiers()

    class FakeOps:
        class object:
            @staticmethod
            def modifier_add(type):
                pass

    monkeypatch.setattr(utils.bpy, "ops", FakeOps, raising=False)

    textures = {}
    plane = FakePlane()

    utils.add_modifiers(plane, textures)

    assert len(modifiers_added) == 3
    assert modifiers_added[0].subdivision_type == 'SIMPLE'
    assert modifiers_added[0].levels == 6
    assert modifiers_added[1].levels == 1
    assert modifiers_added[2].texture_coords == 'UV'
    assert modifiers_added[2].strength == 1.0

def test_add_modifiers_failure(monkeypatch):
    """Test that add_modifiers handles modifier creation failure."""
    class FakeOps:
        class object:
            @staticmethod
            def modifier_add(type):
                raise Exception("Modifier add failed")

    monkeypatch.setattr(utils.bpy, "ops", FakeOps, raising=False)

    with pytest.raises(RuntimeError, match="Failed to add modifiers"):
        utils.add_modifiers(object(), {})

def test_add_modifiers_with_depth(monkeypatch):
    """Test that add_modifiers loads and applies depth texture."""
    class FakeImage:
        colorspace_settings = types.SimpleNamespace(name=None)

    class FakeImages:
        def load(self, path):
            return FakeImage()

    class FakeTexture:
        def __init__(self, name, type):
            self.image = None

    class FakeTextures:
        def new(self, name, type):
            return FakeTexture(name, type)

    class FakeModifier:
        def __init__(self):
            self.texture = None
            self.texture_coords = None
            self.strength = None
            self.mid_level = None
            self.subdivision_type = None
            self.levels = None
            self.render_levels = None

    class FakeModifiers:
        def __getitem__(self, key):
            return FakeModifier()

    class FakePlane:
        modifiers = FakeModifiers()

    class FakeOps:
        class object:
            @staticmethod
            def modifier_add(type):
                pass

    monkeypatch.setattr(utils.bpy, "ops", FakeOps, raising=False)
    monkeypatch.setattr(utils.bpy, "data", types.SimpleNamespace(
        images=FakeImages(),
        textures=FakeTextures()
    ), raising=False)

    textures = {"depth": "depth.png"}
    plane = FakePlane()

    utils.add_modifiers(plane, textures)

def test_add_modifiers_depth_load_failure(monkeypatch):
    """Test that add_modifiers handles depth texture load failure."""
    class FakeImages:
        def load(self, path):
            raise Exception("Image load failed")

    class FakeTextures:
        def new(self, name, type):
            return types.SimpleNamespace(image=None)

    class FakeModifier:
        def __init__(self):
            self.texture = None
            self.subdivision_type = None
            self.levels = None
            self.render_levels = None

    class FakeModifiers:
        def __getitem__(self, key):
            return FakeModifier()

    class FakePlane:
        modifiers = FakeModifiers()

    class FakeOps:
        class object:
            @staticmethod
            def modifier_add(type):
                pass

    monkeypatch.setattr(utils.bpy, "ops", FakeOps, raising=False)
    monkeypatch.setattr(utils.bpy, "data", types.SimpleNamespace(
        images=FakeImages(),
        textures=FakeTextures()
    ), raising=False)

    textures = {"depth": "depth.png"}
    plane = FakePlane()

    with pytest.raises(RuntimeError, match="Failed to load depth texture"):
        utils.add_modifiers(plane, textures)

def test_create_base_material_success(monkeypatch):
    """Test that _create_base_material creates proper node setup."""
    class FakeNode:
        def __init__(self, node_type):
            self.type = node_type
            self.location = None
            # Provide all outputs/inputs that might be accessed
            self.outputs = {
                "BSDF": object(),
                "UV": object(),
                "Vector": object()
            }
            self.inputs = {
                "Surface": object(),
                "Vector": object()
            }

    class FakeNodes:
        def __init__(self):
            self.created = []

        def new(self, type):
            node = FakeNode(type)
            self.created.append(node)
            return node

        def clear(self):
            pass

    class FakeLinks:
        def __init__(self):
            self.links_created = []

        def new(self, output, input):
            self.links_created.append((output, input))

    fake_nodes = FakeNodes()
    fake_links = FakeLinks()

    class FakeMaterial:
        def __init__(self, name):
            self.name = name
            self.use_nodes = None
            self.node_tree = types.SimpleNamespace(nodes=fake_nodes, links=fake_links)

    class FakeMaterials:
        def new(self, name):
            return FakeMaterial(name)

    monkeypatch.setattr(utils.bpy, "data", types.SimpleNamespace(materials=FakeMaterials()), raising=False)

    mat, nodes, links, bsdf, mapping = utils._create_base_material()

    assert mat.name == "PBR_Material"
    assert mat.use_nodes is True
    assert len(fake_nodes.created) == 4  # Output, BSDF, TexCoord, Mapping
    assert len(fake_links.links_created) == 2  # BSDF->Output, TexCoord->Mapping

def test_create_base_material_failure(monkeypatch):
    """Test that _create_base_material handles creation failure."""
    class FakeMaterials:
        def new(self, name):
            raise Exception("Material creation failed")

    monkeypatch.setattr(utils.bpy, "data", types.SimpleNamespace(materials=FakeMaterials()), raising=False)

    with pytest.raises(RuntimeError, match="Failed to create base material"):
        utils._create_base_material()

def test_add_diffuse_load_failure(monkeypatch):
    """Test that _add_diffuse handles texture load failure."""
    class FakeImages:
        def load(self, path):
            raise Exception("Image load failed")

    class FakeNode:
        def __init__(self):
            self.image = None
            self.location = None
            self.inputs = {"Vector": object()}
            self.outputs = {"Color": object()}

    class FakeNodes:
        def new(self, type):
            return FakeNode()

    monkeypatch.setattr(utils.bpy, "data", types.SimpleNamespace(images=FakeImages()), raising=False)

    nodes = FakeNodes()
    links = types.SimpleNamespace(new=lambda a, b: None)
    bsdf = types.SimpleNamespace(inputs={"Base Color": object()})
    mapping = types.SimpleNamespace(outputs={"Vector": object()})

    with pytest.raises(RuntimeError, match="Failed to load diffuse texture node"):
        utils._add_diffuse(nodes, links, bsdf, mapping, "fake.png")

def test_add_roughness_roughness_load_failure(monkeypatch):
    """Test that _add_roughness handles roughness texture load failure."""
    call_count = [0]

    class FakeImages:
        def load(self, path):
            call_count[0] += 1
            if call_count[0] == 1:  # First call (roughness)
                raise Exception("Roughness load failed")
            return types.SimpleNamespace(colorspace_settings=types.SimpleNamespace(name=None))

    class FakeNode:
        def __init__(self):
            self.image = None
            self.location = None
            self.inputs = {"Vector": object(), "Color1": object(), "Color2": object(), "Fac": object()}
            self.outputs = {"Color": object()}

    class FakeNodes:
        def new(self, type):
            return FakeNode()

    monkeypatch.setattr(utils.bpy, "data", types.SimpleNamespace(images=FakeImages()), raising=False)

    nodes = FakeNodes()
    links = types.SimpleNamespace(new=lambda a, b: None)
    bsdf = types.SimpleNamespace(inputs={"Roughness": object()})
    mapping = types.SimpleNamespace(outputs={"Vector": object()})
    textures = {"roughness": "rough.png", "mask": "mask.png"}

    with pytest.raises(RuntimeError, match="Failed to load roughness map"):
        utils._add_roughness(nodes, links, bsdf, mapping, textures)

def test_add_roughness_mask_load_failure(monkeypatch):
    """Test that _add_roughness handles mask texture load failure."""
    call_count = [0]

    class FakeImages:
        def load(self, path):
            call_count[0] += 1
            if call_count[0] == 2:  # Second call (mask)
                raise Exception("Mask load failed")
            return types.SimpleNamespace(colorspace_settings=types.SimpleNamespace(name=None))

    class FakeNode:
        def __init__(self):
            self.image = None
            self.location = None
            self.inputs = {"Vector": object(), "Color1": object(), "Color2": object(), "Fac": object()}
            self.outputs = {"Color": object()}

    class FakeNodes:
        def new(self, type):
            return FakeNode()

    monkeypatch.setattr(utils.bpy, "data", types.SimpleNamespace(images=FakeImages()), raising=False)

    nodes = FakeNodes()
    links = types.SimpleNamespace(new=lambda a, b: None)
    bsdf = types.SimpleNamespace(inputs={"Roughness": object()})
    mapping = types.SimpleNamespace(outputs={"Vector": object()})
    textures = {"roughness": "rough.png", "mask": "mask.png"}

    with pytest.raises(RuntimeError, match="Failed to load mask map"):
        utils._add_roughness(nodes, links, bsdf, mapping, textures)

def test_add_normal_load_failure(monkeypatch):
    """Test that _add_normal handles normal map load failure."""
    class FakeImages:
        def load(self, path):
            raise Exception("Normal map load failed")

    class FakeNode:
        def __init__(self):
            self.image = None
            self.location = None
            self.inputs = {"Vector": object(), "Color": object()}
            self.outputs = {"Color": object(), "Normal": object()}

    class FakeNodes:
        def new(self, type):
            return FakeNode()

    monkeypatch.setattr(utils.bpy, "data", types.SimpleNamespace(images=FakeImages()), raising=False)

    nodes = FakeNodes()
    links = types.SimpleNamespace(new=lambda a, b: None)
    bsdf = types.SimpleNamespace(inputs={"Normal": object()})
    mapping = types.SimpleNamespace(outputs={"Vector": object()})

    with pytest.raises(RuntimeError, match="Failed to load normal map"):
        utils._add_normal(nodes, links, bsdf, mapping, "normal.png")


# ------------------------------------------------------------
# call_hf_pbr tests
# ------------------------------------------------------------

@patch("scripts.utils._download_results")
@patch("scripts.utils._poll_queue")
@patch("scripts.utils._join_queue")
@patch("scripts.utils._upload_file")
@patch("scripts.utils._resolve_fn_index")
@patch("scripts.utils.os.path.exists", return_value=True)
@patch("builtins.open", new_callable=mock_open, read_data=b"imagebytes")
def test_call_hf_pbr_success(
        mock_file,
        mock_exists,
        mock_resolve,
        mock_upload,
        mock_join,
        mock_poll,
        mock_download,
):
    mock_resolve.return_value = 0
    mock_upload.return_value = "/tmp/uploaded.png"
    mock_join.return_value = "event123"

    mock_poll.return_value = [
        {"url": "d"},
        {"url": "n"},
        {"url": "r"},
        {"url": "m"},
    ]

    mock_download.return_value = {
        "depth": "d",
        "normal": "n",
        "roughness": "r",
        "mask": "m",
        "diffuse": "diffuse.png",
    }

    result = utils.call_hf_pbr("fake.png", "/tmp", prompt="brick")

    assert "depth" in result
    assert result["diffuse"] == "diffuse.png"

    mock_resolve.assert_called_once()
    mock_upload.assert_called_once()
    mock_join.assert_called_once()
    mock_poll.assert_called_once()
    mock_download.assert_called_once()


@patch("scripts.utils._resolve_fn_index")
@patch("scripts.utils.os.path.exists", return_value=True)
@patch("builtins.open", new_callable=mock_open, read_data=b"imagebytes")
def test_call_hf_pbr_wraps_exception(
        mock_file,
        mock_exists,
        mock_resolve,
):
    mock_resolve.side_effect = Exception("boom")

    with pytest.raises(RuntimeError) as ctx:
        utils.call_hf_pbr("fake.png", "/tmp")

    assert "PBR generation failed" in str(ctx.value)
