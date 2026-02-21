bl_info = {
    "name": "planetopbr",
    "blender": (2, 80, 0),
    "category": "Object",
}

def register():
    import bpy
    from .operators import OBJECT_OT_import_plane_from_image
    bpy.utils.register_class(OBJECT_OT_import_plane_from_image)

def unregister():
    import bpy
    from .operators import OBJECT_OT_import_plane_from_image
    bpy.utils.unregister_class(OBJECT_OT_import_plane_from_image)
