def register():
    from .scripts import extension_draw, operators, panels, properties

    properties.register()
    operators.register()
    panels.register()
    extension_draw.register()

def unregister():
    from .scripts import extension_draw, operators, panels, properties

    extension_draw.unregister()
    panels.unregister()
    operators.unregister()
    properties.unregister()
