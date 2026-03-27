import bpy

from .properties import get_addon_preferences

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
        preferences = get_addon_preferences(context)

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

        # HuggingFace button
        layout.operator(
            "object.import_plane_from_image",
            text="Generate PBR (HuggingFace)",
            icon='COMMUNITY'
        )

        pro_box = layout.box()
        pro_box.label(text="Pro")
        if preferences.planetopbr_logged_in:
            pro_box.label(text="Logged in", icon='CHECKMARK')
        else:
            pro_box.label(text="Log in from Preferences to unlock", icon='LOCKED')

        pro_row = pro_box.row()
        pro_row.enabled = preferences.planetopbr_logged_in
        pro_row.operator(
            "object.import_plane_from_platform",
            text="Generate PBR (Pro)",
            icon='WORLD'
        )

# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

def register():
    """Register the PlaneToPBR panel."""
    bpy.utils.register_class(VIEW3D_PT_planetopbr_panel)

def unregister():
    """Unregister the PlaneToPBR panel."""
    bpy.utils.unregister_class(VIEW3D_PT_planetopbr_panel)
