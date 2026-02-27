bl_info = {
    "name": "planetopbr",
    "blender": (2, 80, 0),
    "category": "Object",
}

def register():
    import bpy
    from bpy.props import StringProperty
    from .scripts.operators import OBJECT_OT_import_plane_from_image
    from .scripts.operators import menu_func
    bpy.types.Scene.planetopbr_prompt = StringProperty(
        name="HF Prompt",
        description="Describe the material or surface",
        default=""
    )

    bpy.utils.register_class(OBJECT_OT_import_plane_from_image)
    bpy.types.VIEW3D_MT_mesh_add.append(menu_func)

def unregister():
    import bpy
    from .scripts.operators import OBJECT_OT_import_plane_from_image
    del bpy.types.Scene.planetopbr_prompt

    # Uncomment in next ticket
    #bpy.utils.unregister_class(VIEW3D_PT_planetopbr_panel)
    bpy.utils.unregister_class(OBJECT_OT_import_plane_from_image)
