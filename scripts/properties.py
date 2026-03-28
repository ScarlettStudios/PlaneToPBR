import bpy
from bpy.props import BoolProperty, StringProperty


ADDON_PACKAGE = "planetopbr"


class PLANETOPBR_AddonPreferences(bpy.types.AddonPreferences):
    """Persistent add-on settings, including platform login state."""

    bl_idname = ADDON_PACKAGE

    platform_email = StringProperty(
        name="Email",
        description="Scarlett Studios account email address",
        default="",
    )

    platform_password = StringProperty(
        name="Password",
        description="Scarlett Studios account password",
        default="",
        subtype='PASSWORD',
    )

    platform_access_token = StringProperty(default="", options={'HIDDEN'})
    platform_refresh_token = StringProperty(default="", options={'HIDDEN'})
    platform_account_email = StringProperty(default="", options={'HIDDEN'})
    platform_logged_in = BoolProperty(default=False, options={'HIDDEN'})

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="PlaneToPBR Pro Login")

        if self.platform_logged_in and self.platform_access_token:
            account_email = self.platform_account_email or self.platform_email
            box.label(text=f"Signed in as {account_email}")
            box.operator("planetopbr.platform_logout", text="Log Out", icon='X')
        else:
            box.prop(self, "platform_email")
            box.prop(self, "platform_password")
            box.operator("planetopbr.platform_login", text="Log In", icon='CHECKMARK')

        layout.label(text="Hugging Face generation remains free.", icon='INFO')

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
