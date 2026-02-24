import bpy
from bpy_extras.io_utils import ImportHelper
from .hf_client import call_hf_pbr
from .utils import import_plane_from_image

class OBJECT_OT_import_plane_from_image(bpy.types.Operator, ImportHelper):
    """Operator to import a plane with a PBR material using an image as reference."""
    bl_idname = "object.import_plane_from_image"
    bl_label = "Import Plane from Image"
    bl_options = {'REGISTER', 'UNDO'}

    directory: bpy.props.StringProperty(subtype="DIR_PATH")

    # 🔹 This adds the text input field
    hf_prompt: bpy.props.StringProperty(
        name="HF Prompt",
        description="Describe what material or surface this image represents",
        default="",
    )

    def execute(self, context):
        """Execute the operator and import the plane from the diffuse image."""
        #textures = load_pbr_textures(self.directory)
        textures = call_hf_pbr(self.filepath, prompt=self.hf_prompt)
        import_plane_from_image(textures)
        return {'FINISHED'}

    def invoke(self, context, event):
        """Invoke the directory selection dialog."""
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "hf_prompt")

def menu_func(self, context):
    """Add the operator to the 'Add Mesh' menu."""
    self.layout.operator(OBJECT_OT_import_plane_from_image.bl_idname)
