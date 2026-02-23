bl_info = {
    "name": "planetopbr",
    "blender": (2, 80, 0),
    "category": "Object",
}

import bpy

from .operators import (
    OBJECT_OT_import_plane_from_image,
    menu_func,
)

def register():
    print("PLANETOPBR register() CALLED")
    bpy.utils.register_class(OBJECT_OT_import_plane_from_image)
    bpy.types.VIEW3D_MT_mesh_add.append(menu_func)

def unregister():
    print("PLANETOPBR unregister() CALLED")
    bpy.types.VIEW3D_MT_mesh_add.remove(menu_func)
    bpy.utils.unregister_class(OBJECT_OT_import_plane_from_image)
