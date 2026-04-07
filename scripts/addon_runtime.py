"""Helpers for resolving the installed Blender extension package id."""

try:
    from .. import __package__ as BASE_PACKAGE
except ImportError:
    BASE_PACKAGE = "planetopbr"


ADDON_KEYS = (
    BASE_PACKAGE,
    "planetopbr",
    "scripts",
)


def get_addon_preferences(context):
    addons = getattr(getattr(context, "preferences", None), "addons", None)

    if addons is None:
        return None

    for addon_key in ADDON_KEYS:
        addon_entry = addons.get(addon_key) if hasattr(addons, "get") else None
        if addon_entry is not None:
            prefs = getattr(addon_entry, "preferences", None)
            if prefs is not None:
                return prefs

    return None
