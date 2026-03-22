import bpy
from bpy.props import StringProperty

# ------------------------------------------------------------
# Scene Property Registration
# ------------------------------------------------------------

def register():
    """
    Register custom Scene properties used by the PlaneToPBR add-on.
    """
    # Text prompt sent to AI model
    # Used to describe the desired material/surface
    bpy.types.Scene.planetopbr_prompt = StringProperty(
        name="Prompt",
        description="Describe the material or surface",
        default="",
    )

    # File path to the source image
    # Uses FILE_PATH subtype so Blender shows a file browser
    bpy.types.Scene.planetopbr_image_path = StringProperty(
        name="Image",
        description="Path to source image",
        default="",
        subtype='FILE_PATH'
    )

    # Platform API email credential
    bpy.types.Scene.planetopbr_email = StringProperty(
        name="Email",
        description="Platform API email address",
        default="",
    )

    # Platform API password credential
    bpy.types.Scene.planetopbr_password = StringProperty(
        name="Password",
        description="Platform API password",
        default="",
        subtype='PASSWORD'
    )

def unregister():
    """
    Cleanly remove Scene properties when the add-on is disabled.
    Prevents orphaned properties in Blender.
    """
    del bpy.types.Scene.planetopbr_prompt
    del bpy.types.Scene.planetopbr_image_path
    del bpy.types.Scene.planetopbr_email
    del bpy.types.Scene.planetopbr_password
