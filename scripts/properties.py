import bpy
from bpy.props import StringProperty

def register():
    bpy.types.Scene.planetopbr_prompt = StringProperty(
        name="HF Prompt",
        description="Describe the material or surface",
        default="",
    )

    bpy.types.Scene.planetopbr_image_path = StringProperty(
        name="Image",
        description="Path to source image",
        default="",
        subtype='FILE_PATH'
    )

def unregister():
    del bpy.types.Scene.planetopbr_prompt
    del bpy.types.Scene.planetopbr_image_path
