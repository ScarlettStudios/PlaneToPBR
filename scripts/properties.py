import bpy
from bpy.props import BoolProperty, StringProperty


ADDON_MODULE_CANDIDATES = (
    "planetopbr",
    __name__.split(".")[0],
    __package__.split(".")[0] if __package__ else "",
)


class PLANETOPBR_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = "planetopbr"

    planetopbr_email = StringProperty(
        name="Email",
        description="Platform API email address",
        default="",
    )

    planetopbr_password = StringProperty(
        name="Password",
        description="Platform API password",
        default="",
        subtype='PASSWORD'
    )

    planetopbr_access_token = StringProperty(
        name="Access Token",
        description="Stored Platform API access token for session reuse",
        default="",
        options={'HIDDEN'}
    )

    planetopbr_refresh_token = StringProperty(
        name="Refresh Token",
        description="Stored Platform API refresh token for session restore",
        default="",
        options={'HIDDEN'}
    )

    planetopbr_logged_in = BoolProperty(
        name="Logged In",
        description="Whether the stored Platform API credentials were successfully verified",
        default=False,
    )

    planetopbr_login_status = StringProperty(
        name="Login Status",
        description="Last login result shown in preferences",
        default="Not logged in",
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Platform API Login")
        layout.prop(self, "planetopbr_email")
        layout.prop(self, "planetopbr_password")

        row = layout.row(align=True)
        row.operator("planetopbr.login_platform", icon='LOCKED')
        row.operator("planetopbr.logout_platform", icon='UNLOCKED')

        layout.label(text=self.planetopbr_login_status, icon='INFO')


def store_platform_session(preferences, email, client, status=None):
    preferences.planetopbr_email = email
    preferences.planetopbr_access_token = client.access_token or ""
    preferences.planetopbr_refresh_token = client.refresh_token or ""
    preferences.planetopbr_logged_in = bool(preferences.planetopbr_access_token or preferences.planetopbr_refresh_token)
    preferences.planetopbr_login_status = status or f"Logged in as {email}"


def clear_platform_session(preferences, status="Not logged in", clear_password=False):
    preferences.planetopbr_access_token = ""
    preferences.planetopbr_refresh_token = ""
    preferences.planetopbr_logged_in = False
    preferences.planetopbr_login_status = status
    if clear_password:
        preferences.planetopbr_password = ""


def get_addon_preferences(context=None):
    preferences_owner = context.preferences if context else bpy.context.preferences
    addons = getattr(preferences_owner, "addons", None)
    if addons is None:
        raise RuntimeError("Blender add-on preferences are unavailable.")

    for module_name in ADDON_MODULE_CANDIDATES:
        if not module_name:
            continue

        addon = addons.get(module_name) if hasattr(addons, "get") else None
        if addon and getattr(addon, "preferences", None):
            return addon.preferences

    addon_values = addons.values() if hasattr(addons, "values") else []
    for addon in addon_values:
        prefs = getattr(addon, "preferences", None)
        if prefs and hasattr(prefs, "planetopbr_logged_in"):
            return prefs

    raise RuntimeError("PlaneToPBR add-on preferences could not be found.")

# ------------------------------------------------------------
# Scene Property Registration
# ------------------------------------------------------------

def register():
    """
    Register custom Scene properties used by the PlaneToPBR add-on.
    """
    bpy.utils.register_class(PLANETOPBR_AddonPreferences)

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

def unregister():
    """
    Cleanly remove Scene properties when the add-on is disabled.
    Prevents orphaned properties in Blender.
    """
    del bpy.types.Scene.planetopbr_prompt
    del bpy.types.Scene.planetopbr_image_path
    bpy.utils.unregister_class(PLANETOPBR_AddonPreferences)
