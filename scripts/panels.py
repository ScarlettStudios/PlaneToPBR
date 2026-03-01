import bpy

class VIEW3D_PT_planetopbr_panel(bpy.types.Panel):
    bl_label = "Plane to PBR"
    bl_idname = "VIEW3D_PT_planetopbr"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PlaneToPBR"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        box = layout.box()
        box.label(text="AI Settings")
        box.prop(scene, "planetopbr_prompt")

        layout.separator()

        # Image row (label + path + folder icon)
        # row = layout.row(align=True)
        # row.prop(scene, "planetopbr_image_path", text="Image")
        # row.operator(
        #     "planetopbr.select_image",
        #     text="",
        #     icon='FILE_FOLDER'
        # )
        layout.prop(scene, "planetopbr_image_path", text="Image")

        layout.separator()

        layout.operator(
            "object.import_plane_from_image",
            text="Generate PBR Plane",
            icon='MATERIAL'
        )

def register():
    bpy.utils.register_class(VIEW3D_PT_planetopbr_panel)

def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_planetopbr_panel)
