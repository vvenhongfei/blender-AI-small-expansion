bl_info = {
    "name": "Tex Interp Config",
    "author": "vvenhongfei",
    "version": (2, 2),
    "blender": (4, 5, 0),
    "location": "Edit > Preferences > Add-ons > Tex Interp Config",
    "description": "Set default interpolation for new textures (supports中英文)",
    "category": "Material",
}

import bpy
import time
from bpy.app.handlers import persistent
from bpy.props import EnumProperty

# 存储已处理节点的指针ID和创建时间
processed_nodes = {}
NEW_NODE_TIMEOUT = 2.0  # 新节点判断超时时间（秒）

# 插值模式选项定义
interpolation_modes = [
    ("Linear", "Linear", "Linear interpolation (no smoothing)"),
    ("Closest", "Closest", "Closest pixel interpolation (blocky)"),
    ("Cubic", "Cubic", "Cubic interpolation (smooth)"),
    ("Smart", "Smart", "Adaptive interpolation based on texture"),
]

# 插件设置面板（含中英文说明）
class TEX_INTERP_CONFIG_PT_settings(bpy.types.AddonPreferences):
    bl_idname = __name__

    # 存储用户选择的默认插值模式
    default_interpolation: EnumProperty(
        name="Default Interpolation",
        description="Set default mode for new textures",
        items=interpolation_modes,
        default="Smart",
    )

    def draw(self, context):
        layout = self.layout
        
        # 英文说明
        layout.label(text="English:")
        box = layout.box()
        box.label(text="Sets default interpolation mode for newly added:")
        box.label(text="- Image Texture nodes")
        box.label(text="- Environment Texture nodes")
        box.label(text="Manual changes to existing nodes are preserved.")
        
        # 中文说明
        layout.separator()
        layout.label(text="中文:")
        box = layout.box()
        box.label(text="为新添加的纹理节点设置默认插值模式:")
        box.label(text="- 图像纹理节点")
        box.label(text="- 环境纹理节点")
        box.label(text="已存在节点的手动修改会被保留。")
        
        # 插值模式选择
        layout.separator()
        layout.label(text="Default Mode / 默认模式:（新增纹理默认插值）")
        layout.prop(self, "default_interpolation")


def get_user_preferred_mode():
    """获取用户在设置中选择的默认模式"""
    preferences = bpy.context.preferences.addons[__name__].preferences
    return preferences.default_interpolation


def is_new_node(node):
    """判断节点是否为新创建（基于时间戳）"""
    node_id = node.as_pointer()
    if node_id in processed_nodes:
        return time.time() - processed_nodes[node_id] < NEW_NODE_TIMEOUT
    processed_nodes[node_id] = time.time()
    return True


@persistent
def depsgraph_update_handler(dummy):
    """场景更新时触发，为新节点应用用户选择的默认插值"""
    try:
        preferred_mode = get_user_preferred_mode()
        for material in bpy.data.materials:
            if material.use_nodes and material.node_tree:
                for node in material.node_tree.nodes:
                    # 仅处理新创建的图像/环境纹理节点
                    if (node.type in {"TEX_IMAGE", "TEX_ENVIRONMENT"} 
                        and hasattr(node, "interpolation") 
                        and is_new_node(node)):
                        node.interpolation = preferred_mode
    except Exception as e:
        print(f"[Tex Interp Config Error] {str(e)}")


class MATERIAL_OT_set_existing_to_preferred(bpy.types.Operator):
    """将已有纹理批量设置为当前偏好的插值模式
    Set existing textures to current preferred mode"""
    bl_idname = "material.set_existing_to_preferred"
    bl_label = "Set Existing to Preferred"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        preferred_mode = get_user_preferred_mode()
        modified_count = 0
        try:
            for material in bpy.data.materials:
                if material.use_nodes and material.node_tree:
                    for node in material.node_tree.nodes:
                        if node.type in {"TEX_IMAGE", "TEX_ENVIRONMENT"} and hasattr(node, "interpolation"):
                            if node.interpolation != preferred_mode:
                                node.interpolation = preferred_mode
                                modified_count += 1
            self.report({"INFO"}, f"Modified {modified_count} textures to {preferred_mode}")
        except Exception as e:
            self.report({"ERROR"}, f"Failed: {str(e)}")
        return {"FINISHED"}


def material_context_menu(self, context):
    """材质右键菜单添加手动操作按钮"""
    self.layout.operator(MATERIAL_OT_set_existing_to_preferred.bl_idname)


def register():
    bpy.utils.register_class(TEX_INTERP_CONFIG_PT_settings)
    bpy.utils.register_class(MATERIAL_OT_set_existing_to_preferred)
    bpy.types.MATERIAL_MT_context_menu.append(material_context_menu)
    if depsgraph_update_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(depsgraph_update_handler)


def unregister():
    bpy.utils.unregister_class(TEX_INTERP_CONFIG_PT_settings)
    bpy.utils.unregister_class(MATERIAL_OT_set_existing_to_preferred)
    bpy.types.MATERIAL_MT_context_menu.remove(material_context_menu)
    if depsgraph_update_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(depsgraph_update_handler)
    processed_nodes.clear()


if __name__ == "__main__":
    register()
