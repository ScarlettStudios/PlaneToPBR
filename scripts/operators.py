import bpy
import threading

from .hf_client import call_hf_pbr
from .utils import import_plane_from_image

class OBJECT_OT_import_plane_from_image(bpy.types.Operator):
    """
    Blender Operator that:

    1. Sends an image to the Hugging Face Space
    2. Waits asynchronously for PBR map generation
    3. Imports a plane with the generated textures
    """

    bl_idname = "object.import_plane_from_image"
    bl_label = "Import Plane from Image"
    bl_options = {'REGISTER', 'UNDO'}

    # Runtime state variables
    _timer = None  # Blender event timer
    _thread = None  # Background worker thread
    _done = False  # Signals HF processing completion
    _textures = None  # Stores returned texture dictionary
    _progress = 0  # Fake progress indicator value
    _error_message = None  # Stores error from background thread

    # ------------------------------------------------------------
    # Background Thread
    # ------------------------------------------------------------
    def _run_hf(self, filepath, prompt):
        """
        Runs in a separate thread to avoid blocking Blender UI.

        Calls the HF Space and stores results or error.
        """
        try:
            self._textures = call_hf_pbr(filepath, prompt=prompt)
        except Exception as e:
            self._textures = None
            self._error_message = str(e)
        finally:
            # Signal modal loop that processing is finished
            self._done = True


    # ----------------------------
    # EXECUTE
    # ----------------------------
    def execute(self, context):
        """
        Entry point when the operator is invoked.
        Initializes background processing and starts modal loop.
        """
        try:
            prompt = context.scene.planetopbr_prompt
            image_path = context.scene.planetopbr_image_path

            # Ensure image is selected
            if not image_path:
                self.report({'ERROR'}, "No image selected")
                return {'CANCELLED'}

            # Reset runtime state
            self._done = False
            self._textures = None
            self._progress = 0
            self._error_message = None

            # Start background thread (non-blocking)
            self._thread = threading.Thread(
                target=self._run_hf,
                args=(image_path, prompt),
                daemon=True
            )
            self._thread.start()

            # Begin Blender progress UI
            wm = context.window_manager
            wm.progress_begin(0, 100)

            # Add modal timer to poll thread status
            self._timer = wm.event_timer_add(0.1, window=context.window)
            wm.modal_handler_add(self)

            return {'RUNNING_MODAL'}

        except Exception as e:
            self.report({'ERROR'}, f"Unexpected error: {e}")
            return {'CANCELLED'}

    # ----------------------------
    # MODAL LOOP
    # ----------------------------
    def modal(self, context, event):
        """
        Runs repeatedly while operator is active.

        - Updates progress bar
        - Checks if background thread is done
        - Imports textures when ready
        """
        if event.type == 'TIMER':
            wm = context.window_manager

            # While HF processing is still running
            if not self._done:
                self._progress = (self._progress + 2) % 100
                wm.progress_update(self._progress)
                return {'PASS_THROUGH'}

            # Processing finished → cleanup timer
            wm.event_timer_remove(self._timer)
            wm.progress_end()

            # If HF returned an error
            if self._error_message:
                self.report({'ERROR'}, self._error_message)
                return {'CANCELLED'}

            # Attempt to import generated textures
            try:
                if self._textures:
                    import_plane_from_image(self._textures)
                    self.report({'INFO'}, "PBR textures imported.")
                    return {'FINISHED'}
                else:
                    self.report({'ERROR'}, "Failed to generate PBR textures.")
                    return {'CANCELLED'}

            except Exception as e:
                self.report({'ERROR'}, f"Import failed: {e}")
                return {'CANCELLED'}

        return {'PASS_THROUGH'}


# ------------------------------------------------------------
# Registration
# ------------------------------------------------------------

def register():
    """Register the operator with Blender."""
    bpy.utils.register_class(OBJECT_OT_import_plane_from_image)

def unregister():
    """Unregister the operator from Blender."""
    bpy.utils.unregister_class(OBJECT_OT_import_plane_from_image)
