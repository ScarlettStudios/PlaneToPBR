import threading
import webbrowser
from queue import Empty, Queue

import bpy

from .addon_runtime import get_addon_preferences
from .platform_client import PlatformClient, PlatformClientError
from .utils import call_hf_pbr, call_platform_pbr, get_project_texture_dir, import_plane_from_image


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


def _fetch_platform_account_state(client):
    """Fetch account data in a worker without touching Blender state."""
    account = client.get_me()
    try:
        balance = client.get_balance()
        balance_tokens = int(balance.get("balance_tokens", 0))
    except (PlatformClientError, TypeError, ValueError):
        balance_tokens = 0
    return {"email": account.get("email", ""), "balance_tokens": balance_tokens}


def _apply_platform_account_state(prefs, account):
    prefs.platform_account_email = account["email"]
    prefs.platform_plan_label = "Free plan"
    prefs.platform_balance_tokens = account["balance_tokens"]


def _store_platform_tokens(prefs, auth_state):
    prefs.platform_access_token = auth_state.get("access_token", "")
    prefs.platform_refresh_token = auth_state.get("refresh_token", "")
    prefs.platform_logged_in = bool(prefs.platform_access_token)


def _cancel_browser_session(session_id):
    """Cancel remotely without delaying Blender's UI."""
    def cancel():
        try:
            PlatformClient().cancel_browser_login(session_id)
        except PlatformClientError:
            pass
    threading.Thread(target=cancel, daemon=True).start()


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
    _active_login = None

    def execute(self, context):
        prefs = None
        try:
            prefs = get_addon_preferences(context)
            if prefs is None:
                raise RuntimeError("PlaneToPBR preferences are unavailable.")

            if prefs.platform_login_in_progress:
                self.report({'ERROR'}, "PlaneToPBR Pro login is already in progress.")
                return {'CANCELLED'}

            self._client = PlatformClient()
            self._results = Queue()
            self._cancelled = threading.Event()
            self._request_lock = threading.Lock()
            self._request_pending = False
            PLANETOPBR_OT_platform_login._active_login = self
            prefs.platform_browser_session_id = ""
            prefs.platform_browser_authorize_url = ""
            prefs.platform_login_in_progress = True
            _redraw_preferences()
            wm = context.window_manager
            self._timer = wm.event_timer_add(1.0, window=context.window)
            wm.modal_handler_add(self)
            self._start_request("start", self._client.start_browser_login, mode=self.mode or "login")
            return {'RUNNING_MODAL'}
        except Exception as e:
            if prefs is not None:
                prefs.platform_browser_session_id = ""
                prefs.platform_browser_authorize_url = ""
                prefs.platform_login_in_progress = False
                _redraw_preferences()
            self._finish(context)
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

    def _start_request(self, kind, request, *args, **kwargs):
        self._request_pending = True
        results = self._results
        cancelled = self._cancelled
        request_lock = self._request_lock

        def run():
            try:
                value = request(*args, **kwargs)
                with request_lock:
                    if cancelled.is_set():
                        if kind == "start" and value.get("session_id"):
                            _cancel_browser_session(value["session_id"])
                        return
                    results.put((kind, value, None))
            except Exception as exc:
                results.put((kind, None, exc))

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def _complete_login(self, status):
        access_token = status.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise PlatformClientError("Approved browser login is missing an access token.")
        self._client.access_token = access_token
        self._client.refresh_token = status.get("refresh_token") or None
        try:
            account = _fetch_platform_account_state(self._client)
        except PlatformClientError:
            account = None
        return {"account": account, "auth_state": {
            "access_token": self._client.access_token or "",
            "refresh_token": self._client.refresh_token or "",
        }}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        prefs = get_addon_preferences(context)
        if prefs is None:
            self._finish(context)
            self.report({'ERROR'}, "PlaneToPBR preferences are unavailable.")
            return {'CANCELLED'}

        if PLANETOPBR_OT_platform_login._active_login is not self or not prefs.platform_login_in_progress:
            self._finish(context)
            return {'CANCELLED'}

        try:
            try:
                kind, value, error = self._results.get_nowait()
            except Empty:
                if not self._request_pending and prefs.platform_browser_session_id:
                    self._start_request("status", self._client.get_browser_login_status,
                                        prefs.platform_browser_session_id)
                return {'PASS_THROUGH'}

            self._request_pending = False
            if error is not None:
                raise error

            if kind == "start":
                session_id = value.get("session_id")
                authorize_url = value.get("authorize_url")
                if not session_id or not authorize_url:
                    raise PlatformClientError("Browser login session could not be started.")
                prefs.platform_browser_session_id = session_id
                prefs.platform_browser_authorize_url = authorize_url
                _open_browser_url(authorize_url)
                _redraw_preferences()
            elif kind == "account":
                _store_platform_tokens(prefs, value["auth_state"])
                if value["account"] is not None:
                    _apply_platform_account_state(prefs, value["account"])
                self._clear_browser_state(prefs)
                self._finish(context)
                self.report({'INFO'}, "PlaneToPBR Pro login complete.")
                return {'FINISHED'}
            elif value.get("status") == "approved":
                self._start_request("account", self._complete_login, value)
            elif value.get("status") in {"cancelled", "expired", "failed"}:
                state = value["status"]
                self._clear_browser_state(prefs)
                self._finish(context)
                self.report({'WARNING'}, f"PlaneToPBR Pro login {state}.")
                return {'CANCELLED'}
        except Exception as exc:
            self.cancel(context)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        return {'PASS_THROUGH'}

    @staticmethod
    def _clear_browser_state(prefs):
        prefs.platform_browser_session_id = ""
        prefs.platform_browser_authorize_url = ""
        prefs.platform_login_in_progress = False
        _redraw_preferences()

    def cancel(self, context):
        prefs = get_addon_preferences(context)
        if prefs is not None:
            session_id = prefs.platform_browser_session_id
            self._clear_browser_state(prefs)
            if session_id and self._client is not None:
                _cancel_browser_session(session_id)
        self._finish(context)

    def _finish(self, context):
        if PLANETOPBR_OT_platform_login._active_login is self:
            PLANETOPBR_OT_platform_login._active_login = None
        if hasattr(self, "_cancelled"):
            with self._request_lock:
                self._cancelled.set()
                while True:
                    try:
                        kind, value, error = self._results.get_nowait()
                    except Empty:
                        break
                    if kind == "start" and error is None and value.get("session_id"):
                        _cancel_browser_session(value["session_id"])
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

        active = PLANETOPBR_OT_platform_login._active_login
        if active is not None:
            active.cancel(context)
        else:
            session_id = prefs.platform_browser_session_id
            PLANETOPBR_OT_platform_login._clear_browser_state(prefs)
            if session_id:
                _cancel_browser_session(session_id)

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
            active = PLANETOPBR_OT_platform_login._active_login
            if active is not None:
                active.cancel(context)
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
    _account_state = None

    # ------------------------------------------------------------
    # Background Thread
    # ------------------------------------------------------------
    def _run_platform_api(self, filepath, prompt, access_token, refresh_token):
        """
        Runs in a separate thread to avoid blocking Blender UI.
        Calls the Platform API and stores results or error.
        """
        self._updated_auth_state = {"access_token": access_token, "refresh_token": refresh_token}
        self._account_state = None
        try:
            textures_dir = get_project_texture_dir()

            self._textures, self._updated_auth_state = call_platform_pbr(
                image_path=filepath,
                output_dir=textures_dir,
                prompt=prompt,
                access_token=access_token,
                refresh_token=refresh_token,
                auth_state=self._updated_auth_state,
            )
            client = PlatformClient()
            client.access_token = self._updated_auth_state["access_token"]
            client.refresh_token = self._updated_auth_state["refresh_token"]
            try:
                self._account_state = _fetch_platform_account_state(client)
            except PlatformClientError:
                pass
            finally:
                self._updated_auth_state.update(access_token=client.access_token or "",
                                                refresh_token=client.refresh_token or "")
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
            self._account_state = None

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

            if self._updated_auth_state:
                prefs = get_addon_preferences(context)
                if prefs is None:
                    self.report({'ERROR'}, "PlaneToPBR preferences are unavailable.")
                    return {'CANCELLED'}
                _store_platform_tokens(prefs, self._updated_auth_state)
                if self._account_state is not None:
                    _apply_platform_account_state(prefs, self._account_state)

            # Save rotated tokens even if generation or download failed.
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
