import bpy
from bpy.props import StringProperty

# ------------------------------------------------------------
# Scene Property Registration
# ------------------------------------------------------------

def register():
    """
    Register custom Scene properties used by the PlaneToPBR add-on.
    """
    # Text prompt sent to Hugging Face model
    # Used to describe the desired material/surface
    bpy.types.Scene.planetopbr_prompt = StringProperty(
        name="HF Prompt",
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

def unregister():
    """
    Cleanly remove Scene properties when the add-on is disabled.
    Prevents orphaned properties in Blender.
    """
    del bpy.types.Scene.planetopbr_prompt
    del bpy.types.Scene.planetopbr_image_path
