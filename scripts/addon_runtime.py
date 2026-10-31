"""Helpers for resolving the installed Blender extension package id."""

import os

try:
    from .. import __package__ as BASE_PACKAGE
except ImportError:
    BASE_PACKAGE = "planetopbr"


ADDON_KEYS = (
    BASE_PACKAGE,
    "planetopbr",
    "scripts",
)

PRO_ENV_VAR = "PLANETOPBR_ENABLE_PRO"


def pro_enabled():
    """PlaneToPBR Pro stays hidden until launch; set PLANETOPBR_ENABLE_PRO=1 to show it."""
    return os.getenv(PRO_ENV_VAR, "").strip().lower() in {"1", "true", "yes", "on"}


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
