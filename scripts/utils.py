import os
import time
import zipfile
import urllib.error
import socket
from datetime import datetime
import bpy
from .platform_client import PlatformClient, PlatformClientError
from .hf_client import (
    _resolve_fn_index,
    _upload_file,
    _join_queue,
    _poll_queue,
    _download_results,
)

def import_plane_from_image(textures):
    """
    Create a plane in the scene and apply a full PBR material setup
    based on the provided texture dictionary.
    """

    if not isinstance(textures, dict):
        raise RuntimeError("Invalid textures payload.")

    # Ensure we at least have a diffuse texture
    diffuse_path = textures.get("diffuse")
    if not diffuse_path:
        raise RuntimeError("Diffuse texture missing.")

    # ------------------------------------------------------------
    # Load diffuse image to calculate aspect ratio
    # ------------------------------------------------------------
    try:
        img = bpy.data.images.load(diffuse_path)
    except Exception as e:
        raise RuntimeError(f"Failed to load diffuse image: {e}")

    # Prevent divide-by-zero errors
    if img.size[1] == 0:
        raise RuntimeError("Invalid image dimensions.")

    # Maintain correct aspect ratio when scaling plane
    aspect_ratio = img.size[0] / img.size[1]
    width = 2.0
    height = width / aspect_ratio

    # ------------------------------------------------------------
    # Create base mesh plane
    # ------------------------------------------------------------
    try:
        bpy.ops.mesh.primitive_plane_add(size=2, enter_editmode=False, location=(0, 0, 0))
        plane = bpy.context.active_object
    except Exception as e:
        raise RuntimeError(f"Failed to create plane: {e}")

    # Scale plane to match texture proportions
    plane.scale = (width / 2, height / 2, 1)
    plane.name = "PBR_Plane"

    # Smooth shading (non-critical if it fails)
    try:
        bpy.ops.object.shade_smooth()
    except Exception:
        pass  # Not critical

    # ------------------------------------------------------------
    # Create and apply PBR material
    # ------------------------------------------------------------
    mat = apply_pbr_textures(plane, textures)

    try:
        plane.data.materials.append(mat)
    except Exception as e:
        raise RuntimeError(f"Failed to assign material: {e}")

    # ------------------------------------------------------------
    # Add subdivision + displacement modifiers
    # ------------------------------------------------------------
    add_modifiers(plane, textures)

def get_project_texture_dir():
    """
    Return the PlaneToPBR texture output directory
    inside the current Blender project folder.
    """

    if not bpy.data.filepath:
        raise RuntimeError(
            "Please save the Blender project before generating textures."
        )

    project_dir = bpy.path.abspath("//")
    textures_dir = os.path.join(project_dir, "PlaneToPBR_textures")

    os.makedirs(textures_dir, exist_ok=True)

    return textures_dir


def call_hf_pbr(image_path, output_dir, prompt=""):
    """
    Call the Hugging Face Space to generate PBR textures.

    Handles upload, job submission, polling, and download.
    Returns a dictionary of texture file paths.

    Args:
        image_path: Path to input image
        output_dir: Directory to save extracted textures
        prompt: Text prompt for PBR generation

    Returns:
        dict: Texture paths (diffuse, depth, normal, roughness, mask)

    Raises:
        RuntimeError: On processing failures
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fn_index = _resolve_fn_index("predict")
        session_hash = __import__("uuid").uuid4().hex

        if not os.path.exists(image_path):
            raise RuntimeError(f"Input image not found: {image_path}")

        with open(image_path, "rb") as f:
            raw_bytes = f.read()

        uploaded_path = _upload_file(image_path, raw_bytes)
        filename = os.path.basename(image_path)

        payload = {
            "data": [
                {
                    "path": uploaded_path,
                    "orig_name": filename,
                    "size": len(raw_bytes),
                    "mime_type": "image/png",
                },
                prompt or "",
            ],
            "event_data": None,
            "fn_index": fn_index,
            "session_hash": session_hash,
        }

        _join_queue(payload)
        output = _poll_queue(session_hash)

        if not output:
            raise RuntimeError("Hugging Face Space returned no result.")

        diffuse_path = os.path.join(output_dir, f"diffuse_{timestamp}.png")
        with open(diffuse_path, "wb") as out:
            out.write(raw_bytes)

        return _download_results(output, output_dir, timestamp, diffuse_path)

    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error contacting Hugging Face Space: {e}")
    except socket.timeout:
        raise RuntimeError("Request to Hugging Face Space timed out.")
    except Exception as e:
        raise RuntimeError(f"PBR generation failed: {e}")


def call_platform_pbr(image_path, output_dir, prompt, email, password):
    """
    Call the ScarlettStudios Platform API to generate PBR textures.

    Handles login, job creation, polling, download, and extraction.
    Returns a dictionary of texture file paths.

    Args:
        image_path: Path to input image
        output_dir: Directory to save extracted textures
        prompt: Text prompt for PBR generation
        email: Platform API email credential
        password: Platform API password credential

    Returns:
        dict: Texture paths (base_color, normal, roughness, metallic)

    Raises:
        PlatformClientError: On API failures
        RuntimeError: On processing failures
    """
    # Initialize platform client
    client = PlatformClient()

    # Login
    client.login(email=email, password=password)

    # Create PBR job
    job_response = client.create_pbr_job(
        image_path=image_path,
        prompt=prompt,
        output_format="png",
        return_mask=True
    )

    job_id = job_response.get("job_id")
    if not job_id:
        raise PlatformClientError("No job_id returned from create_pbr_job")

    # Poll for job completion
    max_attempts = 60
    attempt = 0
    while attempt < max_attempts:
        status_response = client.get_job_status(job_id)
        status = status_response.get("status")

        if status == "completed":
            download_url = status_response.get("download_url")
            if not download_url:
                raise PlatformClientError("Job completed but no download_url provided")

            # Download results
            output_zip = os.path.join(output_dir, f"{job_id}.zip")
            client.download_results(download_url, output_zip)

            # Extract textures
            extract_dir = os.path.join(output_dir, job_id)
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(output_zip, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # Build texture dictionary (adjust based on actual file naming)
            return {
                "base_color": os.path.join(extract_dir, "base_color.png"),
                "normal": os.path.join(extract_dir, "normal.png"),
                "roughness": os.path.join(extract_dir, "roughness.png"),
                "metallic": os.path.join(extract_dir, "metallic.png"),
            }

        elif status == "failed":
            error_msg = status_response.get("error", "Job failed without error message")
            raise PlatformClientError(f"PBR job failed: {error_msg}")

        # Still processing, wait and retry
        time.sleep(2)
        attempt += 1

    raise PlatformClientError("Job polling timeout: max attempts reached")

def apply_pbr_textures(plane, textures):
    """
    Build a node-based Principled BSDF material and attach
     available texture maps.
    """
    # Create base node structure
    mat, nodes, links, bsdf, mapping = _create_base_material()

    # Add diffuse/base color
    if textures.get("diffuse"):
        _add_diffuse(nodes, links, bsdf, mapping, textures["diffuse"])

    # Add roughness blended with mask
    if textures.get("roughness") and textures.get("mask"):
        _add_roughness(nodes, links, bsdf, mapping, textures)

    # Add normal map
    if textures.get("normal"):
        _add_normal(nodes, links, bsdf, mapping, textures["normal"])

    return mat

def add_modifiers(plane, textures):
    """
    Add subdivision and displacement modifiers to the plane.
    Depth texture (if provided) is used for displacement.
    """
    try:
        # High-level subdivision for displacement detail
        bpy.ops.object.modifier_add(type='SUBSURF')
        sub1 = plane.modifiers["Subdivision"]
        sub1.subdivision_type = 'SIMPLE'
        sub1.levels = 6
        sub1.render_levels = 6

        # Secondary subdivision layer
        bpy.ops.object.modifier_add(type='SUBSURF')
        sub2 = plane.modifiers["Subdivision.001"]
        sub2.subdivision_type = 'SIMPLE'
        sub2.levels = 1
        sub2.render_levels = 1

        # Displacement modifier
        bpy.ops.object.modifier_add(type='DISPLACE')
        disp = plane.modifiers["Displace"]

    except Exception as e:
        raise RuntimeError(f"Failed to add modifiers: {e}")

    # Apply depth map as displacement texture
    if textures.get("depth"):
        try:
            displacement_texture = bpy.data.textures.new(
                name="DisplacementTexture", type='IMAGE'
            )
            displacement_texture.image = bpy.data.images.load(textures["depth"])
            displacement_texture.image.colorspace_settings.name = 'Non-Color'
            disp.texture = displacement_texture
        except Exception as e:
            raise RuntimeError(f"Failed to load depth texture: {e}")

    # Configure displacement settings
    disp.texture_coords = 'UV'
    disp.strength = 1.0
    disp.mid_level = 0.5
# ------------------------------------------------------------
# Base Material Setup
# ------------------------------------------------------------

def _create_base_material():
    """
    Create a clean Principled BSDF node setup:
        Texture Coordinate → Mapping → Texture Nodes → BSDF → Output
    """
    try:
        mat = bpy.data.materials.new(name="PBR_Material")
        mat.use_nodes = True
    except Exception as e:
        raise RuntimeError(f"Failed to create base material: {e}")

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    # Material Output node
    output_node = nodes.new(type="ShaderNodeOutputMaterial")
    output_node.location = (1200, 0)

    # Principled BSDF
    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.location = (900, 0)
    links.new(bsdf.outputs["BSDF"], output_node.inputs["Surface"])

    # UV Coordinate
    tex_coord = nodes.new(type="ShaderNodeTexCoord")
    tex_coord.location = (-800, 0)

    # Mapping
    mapping = nodes.new(type="ShaderNodeMapping")
    mapping.location = (-600, 0)
    links.new(tex_coord.outputs["UV"], mapping.inputs["Vector"])

    return mat, nodes, links, bsdf, mapping


# ------------------------------------------------------------
# Diffuse
# ------------------------------------------------------------

def _add_diffuse(nodes, links, bsdf, mapping, diffuse_path):
    """
    Connect diffuse texture to Principled Base Color.
    """
    try:
        diffuse_node = nodes.new(type="ShaderNodeTexImage")
        diffuse_node.image = bpy.data.images.load(diffuse_path)
    except Exception as e:
        raise RuntimeError(f"Failed to load diffuse texture node: {e}")

    diffuse_node.location = (-400, 300)

    links.new(mapping.outputs["Vector"], diffuse_node.inputs["Vector"])
    links.new(diffuse_node.outputs["Color"], bsdf.inputs["Base Color"])


# ------------------------------------------------------------
# Roughness + Mask Blend
# ------------------------------------------------------------

def _add_roughness(nodes, links, bsdf, mapping, textures):
    """
    Blend roughness map with mask to control surface reflectivity.
    """
    roughness_node = nodes.new(type="ShaderNodeTexImage")

    try:
        roughness_node.image = bpy.data.images.load(textures["roughness"])
    except Exception as e:
        raise RuntimeError(f"Failed to load roughness map: {e}")
    roughness_node.image.colorspace_settings.name = "Non-Color"
    roughness_node.location = (-400, 100)

    mask_node = nodes.new(type="ShaderNodeTexImage")
    try:
        mask_node.image = bpy.data.images.load(textures["mask"])
    except Exception as e:
        raise RuntimeError(f"Failed to load mask map: {e}")
    mask_node.image.colorspace_settings.name = "Non-Color"
    mask_node.location = (-400, -100)

    # Mix node blends roughness with a constant fallback value

    mix_node = nodes.new(type="ShaderNodeMixRGB")
    mix_node.location = (100, 100)

    links.new(mapping.outputs["Vector"], roughness_node.inputs["Vector"])
    links.new(mapping.outputs["Vector"], mask_node.inputs["Vector"])

    links.new(roughness_node.outputs["Color"], mix_node.inputs["Color1"])
    # Default fallback roughness value
    mix_node.inputs["Color2"].default_value = (0.082, 0.082, 0.082, 1)
    links.new(mask_node.outputs["Color"], mix_node.inputs["Fac"])

    links.new(mix_node.outputs["Color"], bsdf.inputs["Roughness"])


# ------------------------------------------------------------
# Normal
# ------------------------------------------------------------

def _add_normal(nodes, links, bsdf, mapping, normal_path):
    """
    Add normal map to Principled BSDF Normal input.
    """
    normal_node = nodes.new(type="ShaderNodeTexImage")
    try:
        normal_node.image = bpy.data.images.load(normal_path)
    except Exception as e:
        raise RuntimeError(f"Failed to load normal map: {e}")
    normal_node.image.colorspace_settings.name = "Non-Color"
    normal_node.location = (-400, -300)

    normal_map_node = nodes.new(type="ShaderNodeNormalMap")
    normal_map_node.location = (400, -300)

    links.new(mapping.outputs["Vector"], normal_node.inputs["Vector"])
    links.new(normal_node.outputs["Color"], normal_map_node.inputs["Color"])

    links.new(normal_map_node.outputs["Normal"], bsdf.inputs["Normal"])
