def register():
    from .scripts import operators, panels, properties

    properties.register()
    operators.register()
    panels.register()

def unregister():
    from .scripts import operators, panels, properties

    panels.unregister()
    operators.unregister()
    properties.unregister()
