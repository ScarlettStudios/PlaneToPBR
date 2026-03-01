import bpy
import threading
# from bpy_extras.io_utils import ImportHelper
# from bpy.props import StringProperty
from .hf_client import call_hf_pbr
from .utils import import_plane_from_image

class OBJECT_OT_import_plane_from_image(bpy.types.Operator):
    """Operator to import a plane with a PBR material using an image as reference."""

    bl_idname = "object.import_plane_from_image"
    bl_label = "Import Plane from Image"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _thread = None
    _done = False
    _textures = None
    _progress = 0
    _error_message = None

    # ----------------------------
    # BACKGROUND THREAD FUNCTION
    # ----------------------------
    def _run_hf(self, filepath, prompt):
        try:
            self._textures = call_hf_pbr(filepath, prompt=prompt)
        except Exception as e:
            self._textures = None
            self._error_message = str(e)
        finally:
            self._done = True


    # ----------------------------
    # EXECUTE
    # ----------------------------
    def execute(self, context):
        prompt = context.scene.planetopbr_prompt
        image_path = context.scene.planetopbr_image_path

        if not image_path:
            self.report({'ERROR'}, "No image selected")
            return {'CANCELLED'}

        self._done = False
        self._textures = None
        self._progress = 0


        # Start background thread
        self._thread = threading.Thread(
            target=self._run_hf,
            args=(image_path, prompt),
            daemon=True
        )
        self._thread.start()

        # Start spinner
        wm = context.window_manager
        wm.progress_begin(0, 100)

        # Start modal timer
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)

        return {'RUNNING_MODAL'}

    # ----------------------------
    # MODAL LOOP
    # ----------------------------
    def modal(self, context, event):
        if event.type == 'TIMER':

            wm = context.window_manager

            if not self._done:
                # Animate spinner progress
                self._progress = (self._progress + 2) % 100
                wm.progress_update(self._progress)
                return {'PASS_THROUGH'}

            # Done
            wm.event_timer_remove(self._timer)
            wm.progress_end()

            if self._textures:
                import_plane_from_image(self._textures)
                self.report({'INFO'}, "PBR textures imported.")
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, "Failed to generate PBR textures.")
                return {'CANCELLED'}

        return {'PASS_THROUGH'}


# class OBJECT_OT_select_image(bpy.types.Operator, ImportHelper):
#     """Select an image file"""
#     bl_idname = "planetopbr.select_image"
#     bl_label = "Select Image"
#
#     filename_ext = ".png"
#     filter_glob: StringProperty(
#         default="*.png;*.jpg;*.jpeg",
#         options={'HIDDEN'}
#     )
#
#     def execute(self, context):
#         context.scene.planetopbr_image_path = self.filepath
#         return {'FINISHED'}

def register():
    bpy.utils.register_class(OBJECT_OT_import_plane_from_image)
    #bpy.utils.register_class(OBJECT_OT_select_image)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_import_plane_from_image)
    #bpy.utils.unregister_class(OBJECT_OT_select_image)
