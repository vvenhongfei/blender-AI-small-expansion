bl_info = {
    "name": "关键帧清除-右键增强",
    "author": "vvenhongfei",
    "version": (1, 0, 0),
    "blender": (4, 5, 0),
    "location": "Dope Sheet / Timeline / Graph Editor → 右键菜单",
    "description": "按位置/旋转/缩放及其轴向删除已选关键帧，支持多物体、骨骼、灯光、曲线等",
    "category": "Animation",
}

import bpy
from bpy.types import Operator, Menu
from bpy.utils import register_class, unregister_class

# =============================================================
# 工具函数
# =============================================================

def _iter_target_objects(context):
    """遍历选中物体或活动物体"""
    sel = [ob for ob in context.selected_objects if ob]
    if sel:
        return sel
    if context.active_object:
        return [context.active_object]
    return []

def _iter_fcurves_of_objects(objs):
    """遍历对象的 fcurves"""
    for ob in objs:
        ad = getattr(ob, "animation_data", None)
        if not (ad and ad.action):
            continue
        for fc in ad.action.fcurves:
            yield ob, fc

def _is_match_transform_channel(data_path, array_index, *, kinds: set, indices: set | None):
    """判断 fcurve 是否属于指定类型和分量"""
    base = ("location", "scale", "rotation_euler", "rotation_quaternion")
    if not any(k in data_path for k in base):
        return False
    matched_kind = None
    for k in kinds:
        if k in data_path:
            matched_kind = k
            break
    if matched_kind is None:
        return False
    if indices is None:
        return True
    return array_index in indices

def _delete_selected_keyframes_from_fcurve(obj, fcurve, *, kinds: set, indices: set | None) -> int:
    """删除单条 fcurve 的选中关键帧"""
    if not fcurve or not fcurve.keyframe_points:
        return 0
    if not _is_match_transform_channel(fcurve.data_path, fcurve.array_index, kinds=kinds, indices=indices):
        return 0
    kps = fcurve.keyframe_points
    sel_ids = [i for i, kp in enumerate(kps) if getattr(kp, "select_control_point", False)]
    if not sel_ids:
        return 0
    removed = 0
    for i in reversed(sel_ids):
        try:
            kps.remove(kps[i])
            removed += 1
        except Exception:
            pass
    return removed

def _delete_selected_keyframes(context, *, kinds: set, indices: set | None) -> int:
    """删除上下文对象的符合条件关键帧"""
    total = 0
    fcurves_to_remove = []
    for ob in _iter_target_objects(context):
        ad = getattr(ob, "animation_data", None)
        if not (ad and ad.action):
            continue
        for fc in list(ad.action.fcurves):
            removed = _delete_selected_keyframes_from_fcurve(ob, fc, kinds=kinds, indices=indices)
            total += removed
            if removed and len(fc.keyframe_points) == 0:
                fcurves_to_remove.append((ad.action.fcurves, fc))
    # 删除空曲线
    for fcurves, fc in fcurves_to_remove:
        try:
            fcurves.remove(fc)
        except Exception:
            pass
    return total

def _refresh_editors():
    """刷新编辑器"""
    wm = bpy.context.window_manager
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type in {"DOPESHEET_EDITOR", "GRAPH_EDITOR", "TIMELINE", "VIEW_3D"}:
                area.tag_redraw()
    scene = bpy.context.scene
    f = scene.frame_current
    scene.frame_current = f

# =============================================================
# Operator 定义（位置 / 缩放 / 旋转 / Euler / Quaternion）
# =============================================================

# 位置
class ANIM_OT_clean_loc_all(Operator):
    bl_idname = "anim.clean_loc_all"
    bl_label = "删除选中位置 · 全部XYZ"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = _delete_selected_keyframes(context, kinds={"location"}, indices={0,1,2})
        self.report({'INFO'}, f"已删除位置关键帧: {n}")
        _refresh_editors()
        return {'FINISHED'}

class ANIM_OT_clean_loc_x(Operator):
    bl_idname = "anim.clean_loc_x"
    bl_label = "删除选中位置 · X"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = _delete_selected_keyframes(context, kinds={"location"}, indices={0})
        self.report({'INFO'}, f"已删除X位置关键帧: {n}")
        _refresh_editors()
        return {'FINISHED'}

class ANIM_OT_clean_loc_y(Operator):
    bl_idname = "anim.clean_loc_y"
    bl_label = "删除选中位置 · Y"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = _delete_selected_keyframes(context, kinds={"location"}, indices={1})
        self.report({'INFO'}, f"已删除Y位置关键帧: {n}")
        _refresh_editors()
        return {'FINISHED'}

class ANIM_OT_clean_loc_z(Operator):
    bl_idname = "anim.clean_loc_z"
    bl_label = "删除选中位置 · Z"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = _delete_selected_keyframes(context, kinds={"location"}, indices={2})
        self.report({'INFO'}, f"已删除Z位置关键帧: {n}")
        _refresh_editors()
        return {'FINISHED'}

# 缩放
class ANIM_OT_clean_scale_all(Operator):
    bl_idname = "anim.clean_scale_all"
    bl_label = "删除选中缩放 · 全部XYZ"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = _delete_selected_keyframes(context, kinds={"scale"}, indices={0,1,2})
        self.report({'INFO'}, f"已删除缩放关键帧: {n}")
        _refresh_editors()
        return {'FINISHED'}

class ANIM_OT_clean_scale_x(Operator):
    bl_idname = "anim.clean_scale_x"
    bl_label = "删除选中缩放 · X"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = _delete_selected_keyframes(context, kinds={"scale"}, indices={0})
        self.report({'INFO'}, f"已删除X缩放关键帧: {n}")
        _refresh_editors()
        return {'FINISHED'}

class ANIM_OT_clean_scale_y(Operator):
    bl_idname = "anim.clean_scale_y"
    bl_label = "删除选中缩放 · Y"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = _delete_selected_keyframes(context, kinds={"scale"}, indices={1})
        self.report({'INFO'}, f"已删除Y缩放关键帧: {n}")
        _refresh_editors()
        return {'FINISHED'}

class ANIM_OT_clean_scale_z(Operator):
    bl_idname = "anim.clean_scale_z"
    bl_label = "删除选中缩放 · Z"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = _delete_selected_keyframes(context, kinds={"scale"}, indices={2})
        self.report({'INFO'}, f"已删除Z缩放关键帧: {n}")
        _refresh_editors()
        return {'FINISHED'}

# 旋转
class ANIM_OT_clean_rot_auto_all(Operator):
    bl_idname = "anim.clean_rot_auto_all"
    bl_label = "删除选中旋转 · 全部(Euler/Quat)"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = _delete_selected_keyframes(context, kinds={"rotation_euler", "rotation_quaternion"}, indices=None)
        self.report({'INFO'}, f"已删除旋转关键帧: {n}")
        _refresh_editors()
        return {'FINISHED'}

# Euler
class ANIM_OT_clean_rote_x(Operator):
    bl_idname = "anim.clean_rote_x"
    bl_label = "删除Euler X旋转"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = _delete_selected_keyframes(context, kinds={"rotation_euler"}, indices={0})
        self.report({'INFO'}, f"已删除Euler X旋转关键帧: {n}")
        _refresh_editors()
        return {'FINISHED'}

class ANIM_OT_clean_rote_y(Operator):
    bl_idname = "anim.clean_rote_y"
    bl_label = "删除Euler Y旋转"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = _delete_selected_keyframes(context, kinds={"rotation_euler"}, indices={1})
        self.report({'INFO'}, f"已删除Euler Y旋转关键帧: {n}")
        _refresh_editors()
        return {'FINISHED'}

class ANIM_OT_clean_rote_z(Operator):
    bl_idname = "anim.clean_rote_z"
    bl_label = "删除Euler Z旋转"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = _delete_selected_keyframes(context, kinds={"rotation_euler"}, indices={2})
        self.report({'INFO'}, f"已删除Euler Z旋转关键帧: {n}")
        _refresh_editors()
        return {'FINISHED'}

# Quaternion
class ANIM_OT_clean_rotq_all(Operator):
    bl_idname = "anim.clean_rotq_all"
    bl_label = "删除Quat WXYZ旋转"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = _delete_selected_keyframes(context, kinds={"rotation_quaternion"}, indices={0,1,2,3})
        self.report({'INFO'}, f"已删除四元数旋转关键帧: {n}")
        _refresh_editors()
        return {'FINISHED'}

class ANIM_OT_clean_rotq_w(Operator):
    bl_idname = "anim.clean_rotq_w"
    bl_label = "删除Quat W"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = _delete_selected_keyframes(context, kinds={"rotation_quaternion"}, indices={0})
        self.report({'INFO'}, f"已删除Quat W旋转关键帧: {n}")
        _refresh_editors()
        return {'FINISHED'}

class ANIM_OT_clean_rotq_x(Operator):
    bl_idname = "anim.clean_rotq_x"
    bl_label = "删除Quat X"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = _delete_selected_keyframes(context, kinds={"rotation_quaternion"}, indices={1})
        self.report({'INFO'}, f"已删除Quat X旋转关键帧: {n}")
        _refresh_editors()
        return {'FINISHED'}

class ANIM_OT_clean_rotq_y(Operator):
    bl_idname = "anim.clean_rotq_y"
    bl_label = "删除Quat Y"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = _delete_selected_keyframes(context, kinds={"rotation_quaternion"}, indices={2})
        self.report({'INFO'}, f"已删除Quat Y旋转关键帧: {n}")
        _refresh_editors()
        return {'FINISHED'}

class ANIM_OT_clean_rotq_z(Operator):
    bl_idname = "anim.clean_rotq_z"
    bl_label = "删除Quat Z"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = _delete_selected_keyframes(context, kinds={"rotation_quaternion"}, indices={3})
        self.report({'INFO'}, f"已删除Quat Z旋转关键帧: {n}")
        _refresh_editors()
        return {'FINISHED'}

# =============================================================
# 菜单
# =============================================================

class ANIM_MT_clean_location(Menu):
    bl_label = "位置关键帧清除"
    def draw(self, context):
        layout = self.layout
        layout.operator(ANIM_OT_clean_loc_all.bl_idname, text="全部XYZ位置")
        layout.separator()
        layout.operator(ANIM_OT_clean_loc_x.bl_idname, text="X位置")
        layout.operator(ANIM_OT_clean_loc_y.bl_idname, text="Y位置")
        layout.operator(ANIM_OT_clean_loc_z.bl_idname, text="Z位置")

class ANIM_MT_clean_rotation(Menu):
    bl_label = "旋转关键帧清除"
    def draw(self, context):
        layout = self.layout
        layout.label(text="Euler旋转")
        layout.separator()
        layout.operator(ANIM_OT_clean_rot_auto_all.bl_idname, text="全部(Euler/Quat)")
        layout.separator()
        layout.operator(ANIM_OT_clean_rote_x.bl_idname, text="X旋转")
        layout.operator(ANIM_OT_clean_rote_y.bl_idname, text="Y旋转")
        layout.operator(ANIM_OT_clean_rote_z.bl_idname, text="Z旋转")
        layout.separator()
        layout.label(text="Quaternion四元数")
        layout.separator()
        layout.operator(ANIM_OT_clean_rotq_all.bl_idname, text="全部WXYZ四元数")
        layout.separator()
        layout.operator(ANIM_OT_clean_rotq_w.bl_idname, text="W值")
        layout.operator(ANIM_OT_clean_rotq_x.bl_idname, text="X值")
        layout.operator(ANIM_OT_clean_rotq_y.bl_idname, text="Y值")
        layout.operator(ANIM_OT_clean_rotq_z.bl_idname, text="Z值")

class ANIM_MT_clean_scale(Menu):
    bl_label = "缩放关键帧清除"
    def draw(self, context):
        layout = self.layout
        layout.operator(ANIM_OT_clean_scale_all.bl_idname, text="全部XYZ缩放")
        layout.separator()
        layout.operator(ANIM_OT_clean_scale_x.bl_idname, text="X缩放")
        layout.operator(ANIM_OT_clean_scale_y.bl_idname, text="Y缩放")
        layout.operator(ANIM_OT_clean_scale_z.bl_idname, text="Z缩放")

def _draw_context_menu_block(self, context):
    layout = self.layout
    layout.separator()
    layout.label(text="选中关键帧清除：")
    col = layout.column(align=True)
    col.menu(ANIM_MT_clean_location.__name__, text="位置")
    col.menu(ANIM_MT_clean_rotation.__name__, text="旋转")
    col.menu(ANIM_MT_clean_scale.__name__, text="缩放")

# =============================================================
# 注册
# =============================================================

_classes = [
    ANIM_OT_clean_loc_all, ANIM_OT_clean_loc_x, ANIM_OT_clean_loc_y, ANIM_OT_clean_loc_z,
    ANIM_OT_clean_scale_all, ANIM_OT_clean_scale_x, ANIM_OT_clean_scale_y, ANIM_OT_clean_scale_z,
    ANIM_OT_clean_rot_auto_all,
    ANIM_OT_clean_rote_x, ANIM_OT_clean_rote_y, ANIM_OT_clean_rote_z,
    ANIM_OT_clean_rotq_all, ANIM_OT_clean_rotq_w, ANIM_OT_clean_rotq_x, ANIM_OT_clean_rotq_y, ANIM_OT_clean_rotq_z,
    ANIM_MT_clean_location, ANIM_MT_clean_rotation, ANIM_MT_clean_scale
]

def register():
    try:
        unregister()
    except:
        pass
    for cls in _classes:
        register_class(cls)
    # 右键菜单挂载
    if hasattr(bpy.types, 'DOPESHEET_MT_context_menu'):
        bpy.types.DOPESHEET_MT_context_menu.append(_draw_context_menu_block)
    if hasattr(bpy.types, 'TIMELINE_MT_context_menu'):
        bpy.types.TIMELINE_MT_context_menu.append(_draw_context_menu_block)
    if hasattr(bpy.types, 'GRAPH_MT_context_menu'):
        bpy.types.GRAPH_MT_context_menu.append(_draw_context_menu_block)
    print("[关键帧清除增强] 已注册。")

def unregister():
    try:
        if hasattr(bpy.types, 'DOPESHEET_MT_context_menu'):
            bpy.types.DOPESHEET_MT_context_menu.remove(_draw_context_menu_block)
    except: pass
    try:
        if hasattr(bpy.types, 'TIMELINE_MT_context_menu'):
            bpy.types.TIMELINE_MT_context_menu.remove(_draw_context_menu_block)
    except: pass
    try:
        if hasattr(bpy.types, 'GRAPH_MT_context_menu'):
            bpy.types.GRAPH_MT_context_menu.remove(_draw_context_menu_block)
    except: pass
    for cls in reversed(_classes):
        try:
            unregister_class(cls)
        except: pass
    print("[关键帧清除增强] 已卸载。")

if __name__ == "__main__":
    register()
