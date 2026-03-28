import bpy
import threading

from .utils import import_plane_from_image, get_project_texture_dir, call_hf_pbr, call_platform_pbr
from .platform_client import PlatformClient, PlatformClientError


ADDON_KEYS = (
    "planetopbr",
    __package__.split(".")[0] if __package__ else __name__.split(".")[0],
)


def _get_addon_preferences(context):
    addons = getattr(getattr(context, "preferences", None), "addons", None)

    if addons is None:
        raise RuntimeError("Unable to access Blender add-on preferences.")

    for addon_key in ADDON_KEYS:
        addon_entry = addons.get(addon_key) if hasattr(addons, "get") else None
        if addon_entry is not None and getattr(addon_entry, "preferences", None) is not None:
            return addon_entry.preferences

    raise RuntimeError("PlaneToPBR preferences are unavailable.")


class PLANETOPBR_OT_platform_login(bpy.types.Operator):
    """Authenticate the Scarlett Studios platform account from add-on preferences."""

    bl_idname = "planetopbr.platform_login"
    bl_label = "PlaneToPBR Platform Login"

    def execute(self, context):
        try:
            prefs = _get_addon_preferences(context)
            email = getattr(prefs, "platform_email", "").strip()
            password = getattr(prefs, "platform_password", "")

            if not email or not password:
                self.report({'ERROR'}, "Enter your email and password in Add-on Preferences.")
                return {'CANCELLED'}

            client = PlatformClient()
            client.login(email=email, password=password)

            try:
                account = client.get_me()
                account_email = account.get("email") or email
            except PlatformClientError:
                account_email = email

            prefs.platform_email = account_email
            prefs.platform_account_email = account_email
            prefs.platform_access_token = client.access_token or ""
            prefs.platform_refresh_token = client.refresh_token or ""
            prefs.platform_logged_in = True
            prefs.platform_password = ""

            self.report({'INFO'}, f"Signed in as {account_email}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}


class PLANETOPBR_OT_platform_logout(bpy.types.Operator):
    """Clear the persisted Scarlett Studios platform session."""

    bl_idname = "planetopbr.platform_logout"
    bl_label = "PlaneToPBR Platform Logout"

    def execute(self, context):
        try:
            prefs = _get_addon_preferences(context)
            prefs.platform_access_token = ""
            prefs.platform_refresh_token = ""
            prefs.platform_account_email = ""
            prefs.platform_password = ""
            prefs.platform_logged_in = False
            self.report({'INFO'}, "Logged out of PlaneToPBR Pro.")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

class OBJECT_OT_import_plane_from_image(bpy.types.Operator):
    """
    Blender Operator that:

    1. Sends an image to the Hugging Face Space
    2. Waits asynchronously for PBR map generation
    3. Imports a plane with the generated textures
    """

    bl_idname = "object.import_plane_from_image"
    bl_label = "Import Plane from Image (HF)"
    bl_options = {'REGISTER', 'UNDO'}

    # Runtime state variables
    _timer = None  # Blender event timer
    _thread = None  # Background worker thread (HF)
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
            textures_dir = get_project_texture_dir()

            self._textures = call_hf_pbr(
                image_path=filepath,
                output_dir=textures_dir,
                prompt=prompt
            )
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

            # Start HF background thread (non-blocking)
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


class OBJECT_OT_import_plane_from_platform(bpy.types.Operator):
    """
    Blender Operator that:

    1. Sends an image to the ScarlettStudios Platform API
    2. Waits asynchronously for PBR map generation
    3. Imports a plane with the generated textures
    """

    bl_idname = "object.import_plane_from_platform"
    bl_label = "Import Plane from Image (Platform)"
    bl_options = {'REGISTER', 'UNDO'}

    # Runtime state variables
    _timer = None  # Blender event timer
    _platform_thread = None  # Background worker thread (Platform API)
    _platform_done = False  # Signals Platform API processing completion
    _textures = None  # Stores returned texture dictionary
    _progress = 0  # Fake progress indicator value
    _error_message = None  # Stores error from background thread
    _updated_auth_state = None  # Stores refreshed auth tokens

    # ------------------------------------------------------------
    # Background Thread
    # ------------------------------------------------------------
    def _run_platform_api(self, filepath, prompt, access_token, refresh_token):
        """
        Runs in a separate thread to avoid blocking Blender UI.
        Calls the Platform API and stores results or error.
        """
        try:
            textures_dir = get_project_texture_dir()

            self._textures, self._updated_auth_state = call_platform_pbr(
                image_path=filepath,
                output_dir=textures_dir,
                prompt=prompt,
                access_token=access_token,
                refresh_token=refresh_token,
            )
        except Exception as e:
            self._textures = None
            self._error_message = str(e)
        finally:
            # Signal modal loop that processing is finished
            self._platform_done = True


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

            prefs = _get_addon_preferences(context)
            access_token = getattr(prefs, "platform_access_token", "")
            refresh_token = getattr(prefs, "platform_refresh_token", "")

            if not access_token:
                self.report({'ERROR'}, "PlaneToPBR Pro login required in Add-on Preferences.")
                return {'CANCELLED'}

            # Reset runtime state
            self._platform_done = False
            self._textures = None
            self._progress = 0
            self._error_message = None
            self._updated_auth_state = None

            # Start platform API background thread (non-blocking)
            self._platform_thread = threading.Thread(
                target=self._run_platform_api,
                args=(image_path, prompt, access_token, refresh_token),
                daemon=True
            )
            self._platform_thread.start()

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
        """
        if event.type == 'TIMER':
            wm = context.window_manager

            # While Platform API processing is still running
            if not self._platform_done:
                self._progress = (self._progress + 2) % 100
                wm.progress_update(self._progress)
                return {'PASS_THROUGH'}

            # Processing finished → cleanup timer
            wm.event_timer_remove(self._timer)
            wm.progress_end()

            # If Platform API returned an error
            if self._error_message:
                self.report({'ERROR'}, self._error_message)
                return {'CANCELLED'}

            if self._updated_auth_state:
                prefs = _get_addon_preferences(context)
                prefs.platform_access_token = self._updated_auth_state.get("access_token", "")
                prefs.platform_refresh_token = self._updated_auth_state.get("refresh_token", "")
                prefs.platform_logged_in = bool(prefs.platform_access_token)

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
    """Register the operators with Blender."""
    bpy.utils.register_class(PLANETOPBR_OT_platform_login)
    bpy.utils.register_class(PLANETOPBR_OT_platform_logout)
    bpy.utils.register_class(OBJECT_OT_import_plane_from_image)
    bpy.utils.register_class(OBJECT_OT_import_plane_from_platform)

def unregister():
    """Unregister the operators from Blender."""
    bpy.utils.unregister_class(OBJECT_OT_import_plane_from_platform)
    bpy.utils.unregister_class(OBJECT_OT_import_plane_from_image)
    bpy.utils.unregister_class(PLANETOPBR_OT_platform_logout)
    bpy.utils.unregister_class(PLANETOPBR_OT_platform_login)
