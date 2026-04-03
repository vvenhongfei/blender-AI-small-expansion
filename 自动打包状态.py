bl_info = {
    "name": "自动打包状态 (修复版)",
    "author": "Your Name",
    "version": (6, 2, 0),
    "blender": (2, 80, 0),
    "location": "顶部Header",
    "description": "修复顶部栏重复按钮问题，精准定位状态开关",
    "category": "界面",
    "support": "COMMUNITY",
}

import bpy
from bpy.types import Operator, Panel
from bpy.utils import register_class, unregister_class

# ----------------------------
# 全局变量 (防止重复注册)
# ----------------------------
_header_appended = False

# ----------------------------
# 核心逻辑 (简化版)
# ----------------------------
class AutoPackCore:
    """核心逻辑封装"""
    
    @staticmethod
    def get_target_property():
        """获取当前版本 Blender 的自动打包属性对象和属性名"""
        try:
            prefs = bpy.context.preferences
            if hasattr(prefs, "filepaths") and hasattr(prefs.filepaths, "use_auto_pack"):
                return prefs.filepaths, "use_auto_pack"
        except AttributeError:
            pass

        try:
            if hasattr(bpy.data, "use_autopack"):
                return bpy.data, "use_autopack"
        except AttributeError:
            pass
            
        return None, None

    @staticmethod
    def get_status():
        obj, attr = AutoPackCore.get_target_property()
        if obj and attr:
            return getattr(obj, attr)
        return False

    @staticmethod
    def set_status(value):
        obj, attr = AutoPackCore.get_target_property()
        if obj and attr:
            setattr(obj, attr, bool(value))
            return True
        return False

    @staticmethod
    def toggle():
        current = AutoPackCore.get_status()
        new_status = not current
        success = AutoPackCore.set_status(new_status)
        if not success:
            try:
                if hasattr(bpy.ops.file, "autopack_toggle"):
                    bpy.ops.file.autopack_toggle()
                    return not current
            except Exception as e:
                print(f"[AutoPack] 原生切换失败: {e}")
        return new_status

# ----------------------------
# 操作符
# ----------------------------
class FIXED_AUTOPACK_OT_toggle(Operator):
    """切换自动打包状态"""
    bl_idname = "fixed_autopack.toggle"
    bl_label = "切换自动打包"
    bl_description = "点击切换自动打包状态"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        new_status = AutoPackCore.toggle()
        # 刷新所有相关区域
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type in {'TOPBAR', 'VIEW_3D'}:
                    area.tag_redraw()
        self.report({'INFO'}, f"自动打包已{'开启' if new_status else '关闭'}")
        return {'FINISHED'}

# ----------------------------
# UI 绘制 (顶部栏)
# ----------------------------
def draw_topbar_icon(self, context):
    # 【关键修复】检测区域对齐方式
    # 如果是对齐到右侧(RIGHT)，则不绘制，防止在右上角出现重复按钮
    if getattr(context.region, "alignment", "") == 'RIGHT':
        return

    layout = self.layout
    status = AutoPackCore.get_status()
    
    icon = 'CHECKMARK' if status else 'X'
    text = "自动打包:开" if status else "自动打包:关"
    
    row = layout.row(align=True)
    if not status:
        row.alert = True 
    
    row.operator("fixed_autopack.toggle", text=text, icon=icon)

# ----------------------------
# 注册逻辑
# ----------------------------
classes = (
    FIXED_AUTOPACK_OT_toggle,
)

def register():
    global _header_appended
    for cls in classes:
        register_class(cls)
    
    # 添加到顶部栏 (使用全局变量防止重复)
    if hasattr(bpy.types, "TOPBAR_HT_upper_bar"):
        if not _header_appended:
            bpy.types.TOPBAR_HT_upper_bar.append(draw_topbar_icon)
            _header_appended = True

def unregister():
    global _header_appended
    # 从顶部栏移除
    if hasattr(bpy.types, "TOPBAR_HT_upper_bar"):
        if _header_appended:
            try:
                bpy.types.TOPBAR_HT_upper_bar.remove(draw_topbar_icon)
                _header_appended = False
            except:
                pass
        
    for cls in reversed(classes):
        unregister_class(cls)

if __name__ == "__main__":
    register()
