import bpy
from bpy.props import BoolProperty, StringProperty
from .addon_runtime import BASE_PACKAGE


class PLANETOPBR_AddonPreferences(bpy.types.AddonPreferences):
    """Persistent add-on settings, including platform login state."""

    bl_idname = BASE_PACKAGE

    platform_access_token = StringProperty(default="", options={'HIDDEN'})
    platform_refresh_token = StringProperty(default="", options={'HIDDEN'})
    platform_account_email = StringProperty(default="", options={'HIDDEN'})
    platform_logged_in = BoolProperty(default=False, options={'HIDDEN'})
    platform_login_in_progress = BoolProperty(default=False, options={'HIDDEN'})
    platform_browser_session_id = StringProperty(default="", options={'HIDDEN'})

    def draw(self, context):
        pass

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

    bpy.utils.register_class(PLANETOPBR_AddonPreferences)

def unregister():
    """
    Cleanly remove Scene properties when the add-on is disabled.
    Prevents orphaned properties in Blender.
    """
    del bpy.types.Scene.planetopbr_prompt
    del bpy.types.Scene.planetopbr_image_path
    bpy.utils.unregister_class(PLANETOPBR_AddonPreferences)
