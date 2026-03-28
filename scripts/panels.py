import bpy
from .addon_runtime import get_addon_preferences

class VIEW3D_PT_planetopbr_panel(bpy.types.Panel):
    """
    UI Panel for the PlaneToPBR add-on.
    """
    # Panel display settings
    bl_label = "Plane to PBR"
    bl_idname = "VIEW3D_PT_planetopbr"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PlaneToPBR"

    def draw(self, context):
        """
        Draw the panel layout inside the 3D View sidebar.
        """
        layout = self.layout
        scene = context.scene

        # ------------------------------------------------------------
        # AI Settings Section
        # ------------------------------------------------------------
        box = layout.box()
        box.label(text="AI Settings")

        # Prompt field (string property defined elsewhere)
        box.prop(scene, "planetopbr_prompt")

        layout.separator()

        # ------------------------------------------------------------
        # Image Selection
        # ------------------------------------------------------------

        # Simple file path property (uses subtype='FILE_PATH')
        # This replaces the custom folder button approach.
        layout.prop(scene, "planetopbr_image_path", text="Image")

        layout.separator()

        # ------------------------------------------------------------
        # Generate Buttons
        # ------------------------------------------------------------

        # HuggingFace button
        layout.operator(
            "object.import_plane_from_image",
            text="Generate PBR (HuggingFace)",
            icon='COMMUNITY'
        )

        # Platform API button
        layout.operator(
            "object.import_plane_from_platform",
            text="Generate PBR Pro (GPU)",
            icon='WORLD'
        )

        prefs = get_addon_preferences(context)
        if prefs and prefs.platform_logged_in and prefs.platform_access_token:
            layout.label(
                text=f"PBR Pro signed in as {prefs.platform_account_email or prefs.platform_email}",
                icon='CHECKMARK'
            )
        else:
            layout.label(text="PBR Pro login is in Add-on Preferences.", icon='INFO')

# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

def register():
    """Register the PlaneToPBR panel."""
    bpy.utils.register_class(VIEW3D_PT_planetopbr_panel)

def unregister():
    """Unregister the PlaneToPBR panel."""
    bpy.utils.unregister_class(VIEW3D_PT_planetopbr_panel)
