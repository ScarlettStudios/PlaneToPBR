import bpy
import threading

from .hf_client import call_hf_pbr
from .platform_client import PlatformAuthError, PlatformClient
from .properties import (
    clear_platform_session,
    get_addon_preferences,
    store_platform_session,
)
from .utils import import_plane_from_image, get_project_texture_dir, call_platform_pbr


def _build_platform_client(preferences):
    client = PlatformClient()
    access_token = preferences.planetopbr_access_token.strip()
    refresh_token = preferences.planetopbr_refresh_token.strip()
    client.access_token = access_token or None
    client.refresh_token = refresh_token or None
    return client


def _restore_platform_session(preferences):
    client = _build_platform_client(preferences)

    if client.access_token or client.refresh_token:
        try:
            if client.access_token:
                client.get_me()
            else:
                client.refresh_access_token()
                client.get_me()

            store_platform_session(preferences, preferences.planetopbr_email.strip(), client)
            return client
        except PlatformAuthError:
            clear_platform_session(preferences, status="Saved session expired. Log in again.")

    email = preferences.planetopbr_email.strip()
    password = preferences.planetopbr_password
    if not email or not password:
        raise PlatformAuthError("No saved session is available. Log in from Preferences.")

    client = PlatformClient()
    client.login(email=email, password=password)
    store_platform_session(preferences, email, client)
    return client


class PLANETOPBR_OT_login_platform(bpy.types.Operator):
    bl_idname = "planetopbr.login_platform"
    bl_label = "Log In"
    bl_description = "Verify Platform API credentials and unlock Pro generation"

    def execute(self, context):
        preferences = get_addon_preferences(context)

        try:
            email = preferences.planetopbr_email.strip()
            password = preferences.planetopbr_password

            if not email or not password:
                preferences.planetopbr_logged_in = False
                preferences.planetopbr_login_status = "Enter both email and password."
                self.report({'ERROR'}, "Enter both email and password")
                return {'CANCELLED'}

            client = PlatformClient()
            client.login(email=email, password=password)
            store_platform_session(preferences, email, client)
            self.report({'INFO'}, "Platform login successful")
            return {'FINISHED'}

        except Exception as exc:
            clear_platform_session(preferences, status=f"Login failed: {exc}")
            self.report({'ERROR'}, f"Login failed: {exc}")
            return {'CANCELLED'}


class PLANETOPBR_OT_logout_platform(bpy.types.Operator):
    bl_idname = "planetopbr.logout_platform"
    bl_label = "Log Out"
    bl_description = "Lock Pro generation until credentials are verified again"

    def execute(self, context):
        preferences = get_addon_preferences(context)
        clear_platform_session(preferences)
        self.report({'INFO'}, "Platform login cleared")
        return {'FINISHED'}

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
    _session_tokens = None  # Stores refreshed session tokens from background thread

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

    # ------------------------------------------------------------
    # Background Thread
    # ------------------------------------------------------------
    def _run_platform_api(self, filepath, prompt, client):
        """
        Runs in a separate thread to avoid blocking Blender UI.
        Calls the Platform API and stores results or error.
        """
        try:
            textures_dir = get_project_texture_dir()

            self._textures = call_platform_pbr(
                image_path=filepath,
                output_dir=textures_dir,
                prompt=prompt,
                client=client,
            )
            self._session_tokens = {
                "access_token": client.access_token or "",
                "refresh_token": client.refresh_token or "",
            }
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

            preferences = get_addon_preferences(context)
            client = _restore_platform_session(preferences)

            # Reset runtime state
            self._platform_done = False
            self._textures = None
            self._progress = 0
            self._error_message = None
            self._session_tokens = None

            # Start platform API background thread (non-blocking)
            self._platform_thread = threading.Thread(
                target=self._run_platform_api,
                args=(image_path, prompt, client),
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
            preferences = get_addon_preferences(context)

            # While Platform API processing is still running
            if not self._platform_done:
                self._progress = (self._progress + 2) % 100
                wm.progress_update(self._progress)
                return {'PASS_THROUGH'}

            # Processing finished → cleanup timer
            wm.event_timer_remove(self._timer)
            wm.progress_end()

            if self._session_tokens:
                preferences.planetopbr_access_token = self._session_tokens["access_token"]
                preferences.planetopbr_refresh_token = self._session_tokens["refresh_token"]
                preferences.planetopbr_logged_in = True
                if preferences.planetopbr_email.strip():
                    preferences.planetopbr_login_status = f"Logged in as {preferences.planetopbr_email.strip()}"

            # If Platform API returned an error
            if self._error_message:
                if "Login is required" in self._error_message or "expired" in self._error_message.lower():
                    clear_platform_session(preferences, status="Session expired. Log in again.")
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
    """Register the operators with Blender."""
    bpy.utils.register_class(PLANETOPBR_OT_login_platform)
    bpy.utils.register_class(PLANETOPBR_OT_logout_platform)
    bpy.utils.register_class(OBJECT_OT_import_plane_from_image)
    bpy.utils.register_class(OBJECT_OT_import_plane_from_platform)

def unregister():
    """Unregister the operators from Blender."""
    bpy.utils.unregister_class(OBJECT_OT_import_plane_from_platform)
    bpy.utils.unregister_class(OBJECT_OT_import_plane_from_image)
    bpy.utils.unregister_class(PLANETOPBR_OT_logout_platform)
    bpy.utils.unregister_class(PLANETOPBR_OT_login_platform)
