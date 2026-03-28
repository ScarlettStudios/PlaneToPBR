import bpy

from .addon_runtime import get_addon_preferences
from .platform_client import DEFAULT_BASE_URL

TARGET_PKG_ID = "planetopbr"
PUBLIC_BASE_URL = DEFAULT_BASE_URL[:-3] if DEFAULT_BASE_URL.endswith("/v1") else DEFAULT_BASE_URL

try:
    import bl_pkg.bl_extension_ui as exui
except ImportError:
    exui = None


def _draw_planetopbr_extension_ui(layout, context):
    prefs = get_addon_preferences(context)
    if prefs is None:
        return

    box = layout.box()
    box.label(text="PlaneToPBR Profile", icon='USER')

    if prefs.platform_login_in_progress:
        box.label(text="Login through browser", icon='INFO')
        box.label(text="in progress.")
        actions = box.row(align=True)
        actions.operator("planetopbr.platform_open_browser", text="Open Browser", icon='URL')
        actions.operator("planetopbr.platform_cancel_login", text="Cancel", icon='X')
        return

    if prefs.platform_logged_in and prefs.platform_access_token:
        if prefs.platform_account_email:
            box.label(text=f"Me: {prefs.platform_account_email}")
        box.label(text=f"My plan: {prefs.platform_plan_label or 'Free plan'}")
        box.label(text=f"Remaining: {prefs.platform_balance_tokens} tokens")
        box.separator()
        box.operator("wm.url_open", text="Buy Tokens", icon='URL').url = f"{PUBLIC_BASE_URL}/buy"
        box.operator("wm.url_open", text="See My Account", icon='URL').url = f"{PUBLIC_BASE_URL}/account"
        box.operator("planetopbr.platform_logout", text="Logout", icon='X')
        return

    box.operator("planetopbr.platform_login", text="Login", icon='URL')
    box.operator("planetopbr.platform_signup", text="Sign up", icon='URL')
    box.label(text="Sign up to use PlaneToPBR Pro.")
    box.label(text="Hugging Face generation remains free.")


def extension_draw_item_override(
    layout,
    *,
    pkg_id,
    item_local,
    item_remote,
    is_enabled,
    is_outdated,
    show,
    mark,
    repo_index,
    repo_item,
    operation_in_progress,
    extensions_warnings,
    show_developer_ui=False,
):
    kwargs = dict(
        pkg_id=pkg_id,
        item_local=item_local,
        item_remote=item_remote,
        is_enabled=is_enabled,
        is_outdated=is_outdated,
        show=show,
        mark=mark,
        repo_index=repo_index,
        repo_item=repo_item,
        operation_in_progress=operation_in_progress,
        extensions_warnings=extensions_warnings,
    )

    if bpy.app.version >= (4, 4):
        kwargs["show_developer_ui"] = show_developer_ui

    exui.extension_draw_item_original(layout, **kwargs)

    if pkg_id == TARGET_PKG_ID and show:
        layout.separator(type='LINE')
        _draw_planetopbr_extension_ui(layout, bpy.context)

    return True


def register():
    if exui is None or hasattr(exui, "extension_draw_item_original"):
        return
    exui.extension_draw_item_original = exui.extension_draw_item
    exui.extension_draw_item = extension_draw_item_override


def unregister():
    if exui is None or not hasattr(exui, "extension_draw_item_original"):
        return
    exui.extension_draw_item = exui.extension_draw_item_original
    del exui.extension_draw_item_original
