import bpy
import threading
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty
from .hf_client import call_hf_pbr
from .utils import import_plane_from_image

class OBJECT_OT_import_plane_from_image(bpy.types.Operator, ImportHelper):
    """Operator to import a plane with a PBR material using an image as reference."""

    bl_idname = "object.import_plane_from_image"
    bl_label = "Import Plane from Image"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".png"
    filter_glob: StringProperty(default="*.png;*.jpg;*.jpeg",options={'HIDDEN'})

    _timer = None
    _thread = None
    _done = False
    _textures = None
    _progress = 0

    # ----------------------------
    # BACKGROUND THREAD FUNCTION
    # ----------------------------
    def _run_hf(self, filepath, prompt):
        try:
            self._textures = call_hf_pbr(filepath, prompt=prompt)
        except Exception as e:
            print("HF ERROR:", e)
            self._textures = None
        finally:
            self._done = True


    # ----------------------------
    # EXECUTE
    # ----------------------------
    def execute(self, context):
        prompt = context.scene.planetopbr_prompt

        self._done = False
        self._textures = None
        self._progress = 0

        # Start background thread
        self._thread = threading.Thread(
            target=self._run_hf,
            args=(self.filepath, prompt),
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

    def invoke(self, context, event):
        """Invoke the directory selection dialog."""
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


def register():
    bpy.utils.register_class(OBJECT_OT_import_plane_from_image)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_import_plane_from_image)
