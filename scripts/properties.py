import bpy
from bpy.props import StringProperty

def register():
    bpy.types.Scene.planetopbr_prompt = StringProperty(
        name="HF Prompt",
        description="Describe the material or surface",
        default="",
    )

def unregister():
    del bpy.types.Scene.planetopbr_prompt