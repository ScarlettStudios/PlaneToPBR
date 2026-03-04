import bpy

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
        # Generate Button
        # ------------------------------------------------------------

        # Calls the async operator that:
        # 1. Sends image to HF
        # 2. Waits for results
        # 3. Imports plane with textures
        layout.operator(
            "object.import_plane_from_image",
            text="Generate PBR Plane",
            icon='MATERIAL'
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
