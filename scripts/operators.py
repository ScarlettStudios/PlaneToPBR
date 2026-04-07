import bpy
import threading
import webbrowser

from .addon_runtime import get_addon_preferences
from .utils import import_plane_from_image, get_project_texture_dir, call_hf_pbr, call_platform_pbr
from .platform_client import PlatformClient, PlatformClientError


def _redraw_preferences():
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type != "PREFERENCES":
                continue
            for region in area.regions:
                if region.type in {"WINDOW", "UI"}:
                    region.tag_redraw()


def _sync_platform_account_state(prefs, client):
    account = client.get_me()
    prefs.platform_account_email = account.get("email", "")
    prefs.platform_plan_label = "Free plan"

    try:
        balance = client.get_balance()
        prefs.platform_balance_tokens = int(balance.get("balance_tokens", 0))
    except PlatformClientError:
        prefs.platform_balance_tokens = 0


def _open_browser_url(url):
    opened = False
    try:
        result = bpy.ops.wm.url_open(url=url)
        opened = 'FINISHED' in result
    except Exception:
        opened = False

    if not opened:
        opened = bool(webbrowser.open(url, new=2))

    if not opened:
        raise RuntimeError(f"Unable to open browser automatically. Open this URL manually: {url}")


class PLANETOPBR_OT_platform_login(bpy.types.Operator):
    """Authenticate the Scarlett Studios platform account through the browser."""

    bl_idname = "planetopbr.platform_login"
    bl_label = "PlaneToPBR Platform Login"

    mode: bpy.props.StringProperty(default="login", options={'HIDDEN'})

    _timer = None
    _client = None

    def execute(self, context):
        try:
            prefs = get_addon_preferences(context)
            if prefs is None:
                raise RuntimeError("PlaneToPBR preferences are unavailable.")

            if prefs.platform_login_in_progress:
                self.report({'ERROR'}, "PlaneToPBR Pro login is already in progress.")
                return {'CANCELLED'}

            self._client = PlatformClient()
            session = self._client.start_browser_login(mode=self.mode or "login")
            authorize_url = session.get("authorize_url")
            session_id = session.get("session_id")

            if not authorize_url or not session_id:
                raise RuntimeError("Browser login session could not be started.")

            prefs.platform_browser_session_id = session_id
            prefs.platform_browser_authorize_url = authorize_url
            prefs.platform_login_in_progress = True
            _redraw_preferences()

            _open_browser_url(authorize_url)

            wm = context.window_manager
            self._timer = wm.event_timer_add(1.0, window=context.window)
            wm.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        except Exception as e:
            if prefs is not None:
                prefs.platform_browser_session_id = ""
                prefs.platform_browser_authorize_url = ""
                prefs.platform_login_in_progress = False
                _redraw_preferences()
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        prefs = get_addon_preferences(context)
        if prefs is None:
            self._finish(context)
            self.report({'ERROR'}, "PlaneToPBR preferences are unavailable.")
            return {'CANCELLED'}

        session_id = prefs.platform_browser_session_id
        if not session_id:
            self._finish(context)
            return {'CANCELLED'}

        try:
            status = self._client.get_browser_login_status(session_id)
        except Exception as exc:
            prefs.platform_login_in_progress = False
            prefs.platform_browser_session_id = ""
            prefs.platform_browser_authorize_url = ""
            _redraw_preferences()
            self._finish(context)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        state = status.get("status")
        if state == "approved":
            prefs.platform_access_token = status.get("access_token", "")
            prefs.platform_refresh_token = status.get("refresh_token", "")
            prefs.platform_browser_session_id = ""
            prefs.platform_browser_authorize_url = ""
            prefs.platform_login_in_progress = False
            prefs.platform_logged_in = bool(prefs.platform_access_token)

            if prefs.platform_logged_in:
                try:
                    self._client.access_token = prefs.platform_access_token
                    self._client.refresh_token = prefs.platform_refresh_token
                    _sync_platform_account_state(prefs, self._client)
                except PlatformClientError:
                    pass

            _redraw_preferences()
            self._finish(context)
            self.report({'INFO'}, "PlaneToPBR Pro login complete.")
            return {'FINISHED'}

        if state == "cancelled":
            prefs.platform_browser_session_id = ""
            prefs.platform_browser_authorize_url = ""
            prefs.platform_login_in_progress = False
            _redraw_preferences()
            self._finish(context)
            self.report({'WARNING'}, "PlaneToPBR Pro login was cancelled.")
            return {'CANCELLED'}

        return {'PASS_THROUGH'}

    def cancel(self, context):
        prefs = get_addon_preferences(context)
        if prefs is not None:
            session_id = prefs.platform_browser_session_id
            prefs.platform_browser_session_id = ""
            prefs.platform_browser_authorize_url = ""
            prefs.platform_login_in_progress = False
            _redraw_preferences()
            if session_id and self._client is not None:
                try:
                    self._client.cancel_browser_login(session_id)
                except Exception:
                    pass
        self._finish(context)

    def _finish(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None


class PLANETOPBR_OT_platform_signup(bpy.types.Operator):
    """Start a browser sign-up flow for PlaneToPBR Pro."""

    bl_idname = "planetopbr.platform_signup"
    bl_label = "PlaneToPBR Platform Sign Up"

    def execute(self, context):
        return bpy.ops.planetopbr.platform_login(mode="register")


class PLANETOPBR_OT_platform_cancel_login(bpy.types.Operator):
    """Cancel an in-progress browser login."""

    bl_idname = "planetopbr.platform_cancel_login"
    bl_label = "PlaneToPBR Platform Cancel Login"

    def execute(self, context):
        prefs = get_addon_preferences(context)
        if prefs is None:
            self.report({'ERROR'}, "PlaneToPBR preferences are unavailable.")
            return {'CANCELLED'}

        session_id = prefs.platform_browser_session_id
        prefs.platform_browser_session_id = ""
        prefs.platform_browser_authorize_url = ""
        prefs.platform_login_in_progress = False
        _redraw_preferences()

        if session_id:
            try:
                PlatformClient().cancel_browser_login(session_id)
            except Exception:
                pass

        self.report({'INFO'}, "PlaneToPBR Pro login cancelled.")
        return {'FINISHED'}


class PLANETOPBR_OT_platform_open_browser(bpy.types.Operator):
    """Open the active browser auth URL again."""

    bl_idname = "planetopbr.platform_open_browser"
    bl_label = "PlaneToPBR Platform Open Browser"

    def execute(self, context):
        prefs = get_addon_preferences(context)
        if prefs is None or not prefs.platform_browser_authorize_url:
            self.report({'ERROR'}, "No browser login URL is available.")
            return {'CANCELLED'}

        try:
            _open_browser_url(prefs.platform_browser_authorize_url)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        self.report({'INFO'}, "Opened browser login page.")
        return {'FINISHED'}


class PLANETOPBR_OT_platform_logout(bpy.types.Operator):
    """Clear the persisted Scarlett Studios platform session."""

    bl_idname = "planetopbr.platform_logout"
    bl_label = "PlaneToPBR Platform Logout"

    def execute(self, context):
        try:
            prefs = get_addon_preferences(context)
            if prefs is None:
                raise RuntimeError("PlaneToPBR preferences are unavailable.")
            prefs.platform_access_token = ""
            prefs.platform_refresh_token = ""
            prefs.platform_account_email = ""
            prefs.platform_plan_label = "Free plan"
            prefs.platform_balance_tokens = 0
            prefs.platform_browser_session_id = ""
            prefs.platform_browser_authorize_url = ""
            prefs.platform_login_in_progress = False
            prefs.platform_logged_in = False
            _redraw_preferences()
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

            prefs = get_addon_preferences(context)
            if prefs is None:
                raise RuntimeError("PlaneToPBR preferences are unavailable.")
            access_token = getattr(prefs, "platform_access_token", "")
            refresh_token = getattr(prefs, "platform_refresh_token", "")

            if not access_token:
                self.report({'ERROR'}, "PlaneToPBR Pro login required in Preferences > Get Extensions.")
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
                prefs = get_addon_preferences(context)
                if prefs is None:
                    raise RuntimeError("PlaneToPBR preferences are unavailable.")
                prefs.platform_access_token = self._updated_auth_state.get("access_token", "")
                prefs.platform_refresh_token = self._updated_auth_state.get("refresh_token", "")
                prefs.platform_logged_in = bool(prefs.platform_access_token)
                if prefs.platform_logged_in:
                    client = PlatformClient()
                    client.access_token = prefs.platform_access_token
                    client.refresh_token = prefs.platform_refresh_token
                    try:
                        _sync_platform_account_state(prefs, client)
                    except PlatformClientError:
                        pass

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
    bpy.utils.register_class(PLANETOPBR_OT_platform_signup)
    bpy.utils.register_class(PLANETOPBR_OT_platform_cancel_login)
    bpy.utils.register_class(PLANETOPBR_OT_platform_open_browser)
    bpy.utils.register_class(PLANETOPBR_OT_platform_logout)
    bpy.utils.register_class(OBJECT_OT_import_plane_from_image)
    bpy.utils.register_class(OBJECT_OT_import_plane_from_platform)

def unregister():
    """Unregister the operators from Blender."""
    bpy.utils.unregister_class(OBJECT_OT_import_plane_from_platform)
    bpy.utils.unregister_class(OBJECT_OT_import_plane_from_image)
    bpy.utils.unregister_class(PLANETOPBR_OT_platform_logout)
    bpy.utils.unregister_class(PLANETOPBR_OT_platform_open_browser)
    bpy.utils.unregister_class(PLANETOPBR_OT_platform_cancel_login)
    bpy.utils.unregister_class(PLANETOPBR_OT_platform_signup)
    bpy.utils.unregister_class(PLANETOPBR_OT_platform_login)
