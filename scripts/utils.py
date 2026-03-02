import bpy

def import_plane_from_image(textures):
    """Import a plane and apply the diffuse image as a texture."""

    if not isinstance(textures, dict):
        raise RuntimeError("Invalid textures payload.")

    diffuse_path = textures.get("diffuse")
    if not diffuse_path:
        raise RuntimeError("Diffuse texture missing.")

    try:
        img = bpy.data.images.load(diffuse_path)
    except Exception as e:
        raise RuntimeError(f"Failed to load diffuse image: {e}")

    if img.size[1] == 0:
        raise RuntimeError("Invalid image dimensions.")

    aspect_ratio = img.size[0] / img.size[1]
    width = 2.0
    height = width / aspect_ratio

    try:
        bpy.ops.mesh.primitive_plane_add(size=2, enter_editmode=False, location=(0, 0, 0))
        plane = bpy.context.active_object
    except Exception as e:
        raise RuntimeError(f"Failed to create plane: {e}")

    plane.scale = (width / 2, height / 2, 1)
    plane.name = "PBR_Plane"

    try:
        bpy.ops.object.shade_smooth()
    except Exception:
        pass  # Not critical

    mat = apply_pbr_textures(plane, textures)

    try:
        plane.data.materials.append(mat)
    except Exception as e:
        raise RuntimeError(f"Failed to assign material: {e}")

    add_modifiers(plane, textures)

def apply_pbr_textures(plane, textures):
    mat, nodes, links, bsdf, mapping = _create_base_material()

    if textures.get("diffuse"):
        _add_diffuse(nodes, links, bsdf, mapping, textures["diffuse"])

    if textures.get("roughness") and textures.get("mask"):
        _add_roughness(nodes, links, bsdf, mapping, textures)

    if textures.get("normal"):
        _add_normal(nodes, links, bsdf, mapping, textures["normal"])

    return mat

def add_modifiers(plane, textures):
    try:
        bpy.ops.object.modifier_add(type='SUBSURF')
        sub1 = plane.modifiers["Subdivision"]
        sub1.subdivision_type = 'SIMPLE'
        sub1.levels = 6
        sub1.render_levels = 6

        bpy.ops.object.modifier_add(type='SUBSURF')
        sub2 = plane.modifiers["Subdivision.001"]
        sub2.subdivision_type = 'SIMPLE'
        sub2.levels = 1
        sub2.render_levels = 1

        bpy.ops.object.modifier_add(type='DISPLACE')
        disp = plane.modifiers["Displace"]

    except Exception as e:
        raise RuntimeError(f"Failed to add modifiers: {e}")

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

    disp.texture_coords = 'UV'
    disp.strength = 1.0
    disp.mid_level = 0.5
# ------------------------------------------------------------
# Base Material Setup
# ------------------------------------------------------------

def _create_base_material():
    mat = bpy.data.materials.new(name="PBR_Material")
    mat.use_nodes = True

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    # Output
    output_node = nodes.new(type="ShaderNodeOutputMaterial")
    output_node.location = (1200, 0)

    # Principled BSDF
    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.location = (900, 0)
    links.new(bsdf.outputs["BSDF"], output_node.inputs["Surface"])

    # Texture Coordinate
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
    roughness_node = nodes.new(type="ShaderNodeTexImage")
    try:
        roughness_node.image = bpy.data.images.load(textures["roughness"])
    except Exception as e:
        raise RuntimeError(f"Failed to load roughness map: {e}")
    roughness_node.image.colorspace_settings.name = "Non-Color"
    roughness_node.location = (-400, 100)

    mask_node = nodes.new(type="ShaderNodeTexImage")
    mask_node.image = bpy.data.images.load(textures["mask"])
    mask_node.image.colorspace_settings.name = "Non-Color"
    mask_node.location = (-400, -100)

    mix_node = nodes.new(type="ShaderNodeMixRGB")
    mix_node.location = (100, 100)

    links.new(mapping.outputs["Vector"], roughness_node.inputs["Vector"])
    links.new(mapping.outputs["Vector"], mask_node.inputs["Vector"])

    links.new(roughness_node.outputs["Color"], mix_node.inputs["Color1"])
    mix_node.inputs["Color2"].default_value = (0.082, 0.082, 0.082, 1)
    links.new(mask_node.outputs["Color"], mix_node.inputs["Fac"])

    links.new(mix_node.outputs["Color"], bsdf.inputs["Roughness"])


# ------------------------------------------------------------
# Normal
# ------------------------------------------------------------

def _add_normal(nodes, links, bsdf, mapping, normal_path):
    normal_node = nodes.new(type="ShaderNodeTexImage")
    normal_node.image = bpy.data.images.load(normal_path)
    normal_node.image.colorspace_settings.name = "Non-Color"
    normal_node.location = (-400, -300)

    normal_map_node = nodes.new(type="ShaderNodeNormalMap")
    normal_map_node.location = (400, -300)

    links.new(mapping.outputs["Vector"], normal_node.inputs["Vector"])
    links.new(normal_node.outputs["Color"], normal_map_node.inputs["Color"])

    links.new(normal_map_node.outputs["Normal"], bsdf.inputs["Normal"])
