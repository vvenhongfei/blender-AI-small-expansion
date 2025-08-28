bl_info = {
    "name": "关键帧清除-右键增强",
    "author": "vvenhongfei",
    "version": (1, 0, 0),
    "blender": (4, 5, 0),
    "location": "Pose Mode → N侧边栏/右键菜单；Dope Sheet/Timeline/Graph → 右键菜单",
    "description": "合并：骨骼（Pose）精确选中关键帧清除 + 右键增强的选中关键帧按通道删除，支持多物体/骨骼/灯光/曲线等",
    "category": "Animation",
}

import bpy
from bpy.types import Operator, Panel, Menu
from bpy.utils import register_class, unregister_class

# ------------------------------
# 通用刷新函数
# ------------------------------
def refresh_animation_views():
    """刷新时间线/曲线/3D视图，展示最新关键帧状态"""
    wm = bpy.context.window_manager
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type in ('TIMELINE', 'GRAPH_EDITOR', 'DOPESHEET_EDITOR', 'VIEW_3D'):
                area.tag_redraw()
    # 触发场景更新
    scene = bpy.context.scene
    current_frame = scene.frame_current
    scene.frame_current = current_frame

# ------------------------------
# 来自“骨骼专用”插件的函数
# ------------------------------
def get_selected_keyframes(armature):
    """获取 armature.action 中被手动选中的关键帧 (返回 (fcurve, idx, kp) 列表)"""
    selected_kfs = []
    if not (armature and getattr(armature, "animation_data", None) and armature.animation_data.action):
        return selected_kfs

    for fcurve in armature.animation_data.action.fcurves:
        if "pose.bones[" in fcurve.data_path and fcurve.keyframe_points:
            for idx, kp in enumerate(fcurve.keyframe_points):
                if getattr(kp, "select_control_point", False):
                    selected_kfs.append((fcurve, idx, kp))
    return selected_kfs

def delete_selected_keyframes_for_armature(armature, target_bones, data_path_keyword, indices=None):
    """
    从 armature.animation_data.action 中删除选中的关键帧
    data_path_keyword: 'location' / 'scale' / 'rotation_quaternion' / 'rotation_euler'
    indices: None 或集合 {0,1,2,3}
    """
    deleted_count = 0
    selected_kfs = get_selected_keyframes(armature)

    for fcurve, kp_idx, kp in reversed(selected_kfs):
        # 索引有效性检查
        if kp_idx < 0 or kp_idx >= len(fcurve.keyframe_points):
            continue
        if fcurve.keyframe_points[kp_idx] != kp:
            continue
        # data_path 筛选
        if data_path_keyword not in fcurve.data_path:
            continue
        # channel index 筛选
        if indices is not None and fcurve.array_index not in indices:
            continue
        try:
            fcurve.keyframe_points.remove(kp)
            deleted_count += 1
            # 清理空曲线
            if len(fcurve.keyframe_points) == 0:
                try:
                    armature.animation_data.action.fcurves.remove(fcurve)
                except Exception:
                    pass
        except Exception:
            continue
    return deleted_count

# ------------------------------
# 来自“右键增强”插件的通用 fcurve 删除逻辑
# ------------------------------
def _iter_target_objects(context):
    """遍历选中物体或活动物体（优先返回选中列表）"""
    sel = [ob for ob in context.selected_objects if ob]
    if sel:
        return sel
    if context.active_object:
        return [context.active_object]
    return []

def _iter_fcurves_of_objects(objs):
    for ob in objs:
        ad = getattr(ob, "animation_data", None)
        if not (ad and ad.action):
            continue
        for fc in ad.action.fcurves:
            yield ob, fc

def _is_match_transform_channel(data_path, array_index, *, kinds: set, indices: set | None):
    """判断 fcurve 是否属于请求的 kinds（字符串集合）"""
    # kinds 中元素形如 "location", "scale", "rotation_euler", "rotation_quaternion"
    if not any(k in data_path for k in ("location", "scale", "rotation_euler", "rotation_quaternion")):
        return False
    matched = False
    for k in kinds:
        if k in data_path:
            matched = True
            break
    if not matched:
        return False
    if indices is None:
        return True
    return array_index in indices

def _delete_selected_keyframes_from_fcurve(obj, fcurve, *, kinds: set, indices: set | None) -> int:
    """删除单条 fcurve 上被选中的关键帧（对象通用）"""
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

def _delete_selected_keyframes_for_objects(context, *, kinds: set, indices: set | None) -> int:
    """在选中对象/活动对象上删除符合条件的选中关键帧"""
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

# ------------------------------
# 统一删除接口：自动选择 armature(骨骼) 专用 或 通用对象逻辑
# ------------------------------
def delete_selected_keyframes_auto(context, *, kinds: set, indices: set | None):
    """
    智能选择删除函数：
    - 如果当前处于 Pose 模式且 active object 是 Armature，则使用 armature 专用删除（更精准）
    - 否则使用对象通用 fcurve 删除逻辑
    返回实际删除数量（整数）
    """
    obj = context.object
    # 判断是否 Pose 模式的骨骼清理
    if obj and obj.type == 'ARMATURE' and context.mode == 'POSE':
        armature = obj
        target_bones = context.selected_pose_bones or armature.pose.bones
        total = 0
        # kinds 里可能含有多个条目（例如 rotation_euler 和 rotation_quaternion），逐项删除
        for k in kinds:
            # map k -> data_path keyword (we keep same names)
            data_path_keyword = k
            total += delete_selected_keyframes_for_armature(armature, target_bones, data_path_keyword, indices)
        return total
    else:
        # 通用对象/多物体删除
        return _delete_selected_keyframes_for_objects(context, kinds=kinds, indices=indices)

# ------------------------------
# --- POSE 专用 Operators & 面板 (来自第一份插件)
# ------------------------------
class POSE_OT_clear_location_all(Operator):
    bl_idname = "pose.clear_location_all"
    bl_label = "全部位置"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'ARMATURE' and context.mode == 'POSE'

    def execute(self, context):
        armature = context.object
        target_bones = context.selected_pose_bones or armature.pose.bones
        deleted = delete_selected_keyframes_for_armature(armature, target_bones, "location", [0,1,2])
        if deleted == 0:
            self.report({'INFO'}, "未选中任何位置关键帧")
        else:
            self.report({'INFO'}, f"成功删除 {deleted} 个位置关键帧（选中项）")
        refresh_animation_views()
        return {'FINISHED'}

class POSE_OT_clear_location_x(Operator):
    bl_idname = "pose.clear_location_x"
    bl_label = "X位置"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'ARMATURE' and context.mode == 'POSE'
    def execute(self, context):
        armature = context.object
        target_bones = context.selected_pose_bones or armature.pose.bones
        deleted = delete_selected_keyframes_for_armature(armature, target_bones, "location", [0])
        if deleted == 0:
            self.report({'INFO'}, "未选中任何X位置关键帧")
        else:
            self.report({'INFO'}, f"成功删除 {deleted} 个X位置关键帧（选中项）")
        refresh_animation_views()
        return {'FINISHED'}

class POSE_OT_clear_location_y(Operator):
    bl_idname = "pose.clear_location_y"
    bl_label = "Y位置"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'ARMATURE' and context.mode == 'POSE'
    def execute(self, context):
        armature = context.object
        target_bones = context.selected_pose_bones or armature.pose.bones
        deleted = delete_selected_keyframes_for_armature(armature, target_bones, "location", [1])
        if deleted == 0:
            self.report({'INFO'}, "未选中任何Y位置关键帧")
        else:
            self.report({'INFO'}, f"成功删除 {deleted} 个Y位置关键帧（选中项）")
        refresh_animation_views()
        return {'FINISHED'}

class POSE_OT_clear_location_z(Operator):
    bl_idname = "pose.clear_location_z"
    bl_label = "Z位置"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'ARMATURE' and context.mode == 'POSE'
    def execute(self, context):
        armature = context.object
        target_bones = context.selected_pose_bones or armature.pose.bones
        deleted = delete_selected_keyframes_for_armature(armature, target_bones, "location", [2])
        if deleted == 0:
            self.report({'INFO'}, "未选中任何Z位置关键帧")
        else:
            self.report({'INFO'}, f"成功删除 {deleted} 个Z位置关键帧（选中项）")
        refresh_animation_views()
        return {'FINISHED'}

class POSE_OT_clear_rot_quat_all(Operator):
    bl_idname = "pose.clear_rot_quat_all"
    bl_label = "全部Quat旋转"  # 统一名称：添加Quat标识
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'ARMATURE' and context.mode == 'POSE'
    def execute(self, context):
        armature = context.object
        target_bones = context.selected_pose_bones or armature.pose.bones
        deleted = delete_selected_keyframes_for_armature(armature, target_bones, "rotation_quaternion", [0,1,2,3])
        if deleted == 0:
            self.report({'INFO'}, "未选中任何旋转关键帧")
        else:
            self.report({'INFO'}, f"成功删除 {deleted} 个旋转关键帧（选中项）")
        refresh_animation_views()
        return {'FINISHED'}

class POSE_OT_clear_rot_quat_w(Operator):
    bl_idname = "pose.clear_rot_quat_w"
    bl_label = "Quat W旋转"  # 统一名称：添加Quat标识
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'ARMATURE' and context.mode == 'POSE'
    def execute(self, context):
        armature = context.object
        target_bones = context.selected_pose_bones or armature.pose.bones
        deleted = delete_selected_keyframes_for_armature(armature, target_bones, "rotation_quaternion", [0])
        if deleted == 0:
            self.report({'INFO'}, "未选中任何W旋转关键帧")
        else:
            self.report({'INFO'}, f"成功删除 {deleted} 个W旋转关键帧（选中项）")
        refresh_animation_views()
        return {'FINISHED'}

class POSE_OT_clear_rot_quat_x(Operator):
    bl_idname = "pose.clear_rot_quat_x"
    bl_label = "Quat X旋转"  # 统一名称：添加Quat标识
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'ARMATURE' and context.mode == 'POSE'
    def execute(self, context):
        armature = context.object
        target_bones = context.selected_pose_bones or armature.pose.bones
        deleted = delete_selected_keyframes_for_armature(armature, target_bones, "rotation_quaternion", [1])
        if deleted == 0:
            self.report({'INFO'}, "未选中任何X旋转关键帧")
        else:
            self.report({'INFO'}, f"成功删除 {deleted} 个X旋转关键帧（选中项）")
        refresh_animation_views()
        return {'FINISHED'}

class POSE_OT_clear_rot_quat_y(Operator):
    bl_idname = "pose.clear_rot_quat_y"
    bl_label = "Quat Y旋转"  # 统一名称：添加Quat标识
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'ARMATURE' and context.mode == 'POSE'
    def execute(self, context):
        armature = context.object
        target_bones = context.selected_pose_bones or armature.pose.bones
        deleted = delete_selected_keyframes_for_armature(armature, target_bones, "rotation_quaternion", [2])
        if deleted == 0:
            self.report({'INFO'}, "未选中任何Y旋转关键帧")
        else:
            self.report({'INFO'}, f"成功删除 {deleted} 个Y旋转关键帧（选中项）")
        refresh_animation_views()
        return {'FINISHED'}

class POSE_OT_clear_rot_quat_z(Operator):
    bl_idname = "pose.clear_rot_quat_z"
    bl_label = "Quat Z旋转"  # 统一名称：添加Quat标识
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'ARMATURE' and context.mode == 'POSE'
    def execute(self, context):
        armature = context.object
        target_bones = context.selected_pose_bones or armature.pose.bones
        deleted = delete_selected_keyframes_for_armature(armature, target_bones, "rotation_quaternion", [3])
        if deleted == 0:
            self.report({'INFO'}, "未选中任何Z旋转关键帧")
        else:
            self.report({'INFO'}, f"成功删除 {deleted} 个Z旋转关键帧（选中项）")
        refresh_animation_views()
        return {'FINISHED'}

class POSE_OT_clear_scale_all(Operator):
    bl_idname = "pose.clear_scale_all"
    bl_label = "全部缩放"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'ARMATURE' and context.mode == 'POSE'
    def execute(self, context):
        armature = context.object
        target_bones = context.selected_pose_bones or armature.pose.bones
        deleted = delete_selected_keyframes_for_armature(armature, target_bones, "scale", [0,1,2])
        if deleted == 0:
            self.report({'INFO'}, "未选中任何缩放关键帧")
        else:
            self.report({'INFO'}, f"成功删除 {deleted} 个缩放关键帧（选中项）")
        refresh_animation_views()
        return {'FINISHED'}

class POSE_OT_clear_scale_x(Operator):
    bl_idname = "pose.clear_scale_x"
    bl_label = "X缩放"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'ARMATURE' and context.mode == 'POSE'
    def execute(self, context):
        armature = context.object
        target_bones = context.selected_pose_bones or armature.pose.bones
        deleted = delete_selected_keyframes_for_armature(armature, target_bones, "scale", [0])
        if deleted == 0:
            self.report({'INFO'}, "未选中任何X缩放关键帧")
        else:
            self.report({'INFO'}, f"成功删除 {deleted} 个X缩放关键帧（选中项）")
        refresh_animation_views()
        return {'FINISHED'}

class POSE_OT_clear_scale_y(Operator):
    bl_idname = "pose.clear_scale_y"
    bl_label = "Y缩放"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'ARMATURE' and context.mode == 'POSE'
    def execute(self, context):
        armature = context.object
        target_bones = context.selected_pose_bones or armature.pose.bones
        deleted = delete_selected_keyframes_for_armature(armature, target_bones, "scale", [1])
        if deleted == 0:
            self.report({'INFO'}, "未选中任何Y缩放关键帧")
        else:
            self.report({'INFO'}, f"成功删除 {deleted} 个Y缩放关键帧（选中项）")
        refresh_animation_views()
        return {'FINISHED'}

class POSE_OT_clear_scale_z(Operator):
    bl_idname = "pose.clear_scale_z"
    bl_label = "Z缩放"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'ARMATURE' and context.mode == 'POSE'
    def execute(self, context):
        armature = context.object
        target_bones = context.selected_pose_bones or armature.pose.bones
        deleted = delete_selected_keyframes_for_armature(armature, target_bones, "scale", [2])
        if deleted == 0:
            self.report({'INFO'}, "未选中任何Z缩放关键帧")
        else:
            self.report({'INFO'}, f"成功删除 {deleted} 个Z缩放关键帧（选中项）")
        refresh_animation_views()
        return {'FINISHED'}

# POSE 面板（来自第一份）
class VIEW3D_PT_KeyframeCleanerPanel(Panel):
    bl_label = "选中关键帧精准清除"
    bl_idname = "VIEW3D_PT_keyframe_cleaner"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "动画"
    bl_context = "posemode"

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="使用说明:", icon='INFO')
        box.label(text="1. 在时间线/曲线编辑器中选中关键帧")
        box.label(text="2. 点击下方按钮删除选中项")
        box.label(text="（支持框选、间隔选中的关键帧）")

        # 位置
        col = layout.column(align=True)
        col.label(text="位置关键帧:", icon='ORIENTATION_LOCAL')
        col.operator(POSE_OT_clear_location_all.bl_idname)
        row = col.row(align=True)
        row.operator(POSE_OT_clear_location_x.bl_idname)
        row.operator(POSE_OT_clear_location_y.bl_idname)
        row.operator(POSE_OT_clear_location_z.bl_idname)

        # 旋转
        col.separator()
        col.label(text="旋转关键帧:", icon='ORIENTATION_GIMBAL')
        col.operator(POSE_OT_clear_rot_quat_all.bl_idname)
        row = col.row(align=True)
        row.operator(POSE_OT_clear_rot_quat_w.bl_idname)
        row.operator(POSE_OT_clear_rot_quat_x.bl_idname)
        row.operator(POSE_OT_clear_rot_quat_y.bl_idname)
        row.operator(POSE_OT_clear_rot_quat_z.bl_idname)

        # 缩放
        col.separator()
        col.label(text="缩放关键帧:", icon='FULLSCREEN_ENTER')
        col.operator(POSE_OT_clear_scale_all.bl_idname)
        row = col.row(align=True)
        row.operator(POSE_OT_clear_scale_x.bl_idname)
        row.operator(POSE_OT_clear_scale_y.bl_idname)
        row.operator(POSE_OT_clear_scale_z.bl_idname)

# ------------------------------
# --- 右键增强 Operators & Menus (来自第二份)
# 使用通用 delete_selected_keyframes_auto 做桥接
# ------------------------------
# 位置 Operators (通用/多物体)
class ANIM_OT_clean_loc_all(Operator):
    bl_idname = "anim.clean_loc_all"
    bl_label = "删除选中位置 · 全部XYZ"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = delete_selected_keyframes_auto(context, kinds={"location"}, indices={0,1,2})
        self.report({'INFO'}, f"已删除位置关键帧: {n}")
        refresh_animation_views()
        return {'FINISHED'}

class ANIM_OT_clean_loc_x(Operator):
    bl_idname = "anim.clean_loc_x"
    bl_label = "删除选中位置 · X"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = delete_selected_keyframes_auto(context, kinds={"location"}, indices={0})
        self.report({'INFO'}, f"已删除X位置关键帧: {n}")
        refresh_animation_views()
        return {'FINISHED'}

class ANIM_OT_clean_loc_y(Operator):
    bl_idname = "anim.clean_loc_y"
    bl_label = "删除选中位置 · Y"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = delete_selected_keyframes_auto(context, kinds={"location"}, indices={1})
        self.report({'INFO'}, f"已删除Y位置关键帧: {n}")
        refresh_animation_views()
        return {'FINISHED'}

class ANIM_OT_clean_loc_z(Operator):
    bl_idname = "anim.clean_loc_z"
    bl_label = "删除选中位置 · Z"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = delete_selected_keyframes_auto(context, kinds={"location"}, indices={2})
        self.report({'INFO'}, f"已删除Z位置关键帧: {n}")
        refresh_animation_views()
        return {'FINISHED'}

# 缩放 Operators
class ANIM_OT_clean_scale_all(Operator):
    bl_idname = "anim.clean_scale_all"
    bl_label = "删除选中缩放 · 全部XYZ"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = delete_selected_keyframes_auto(context, kinds={"scale"}, indices={0,1,2})
        self.report({'INFO'}, f"已删除缩放关键帧: {n}")
        refresh_animation_views()
        return {'FINISHED'}

class ANIM_OT_clean_scale_x(Operator):
    bl_idname = "anim.clean_scale_x"
    bl_label = "删除选中缩放 · X"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = delete_selected_keyframes_auto(context, kinds={"scale"}, indices={0})
        self.report({'INFO'}, f"已删除X缩放关键帧: {n}")
        refresh_animation_views()
        return {'FINISHED'}

class ANIM_OT_clean_scale_y(Operator):
    bl_idname = "anim.clean_scale_y"
    bl_label = "删除选中缩放 · Y"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = delete_selected_keyframes_auto(context, kinds={"scale"}, indices={1})
        self.report({'INFO'}, f"已删除Y缩放关键帧: {n}")
        refresh_animation_views()
        return {'FINISHED'}

class ANIM_OT_clean_scale_z(Operator):
    bl_idname = "anim.clean_scale_z"
    bl_label = "删除选中缩放 · Z"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = delete_selected_keyframes_auto(context, kinds={"scale"}, indices={2})
        self.report({'INFO'}, f"已删除Z缩放关键帧: {n}")
        refresh_animation_views()
        return {'FINISHED'}

# 旋转 Operators（自动支持 Euler/Quat）
class ANIM_OT_clean_rot_auto_all(Operator):
    bl_idname = "anim.clean_rot_auto_all"
    bl_label = "删除选中旋转 · 全部(Euler/Quat)"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = delete_selected_keyframes_auto(context, kinds={"rotation_euler", "rotation_quaternion"}, indices=None)
        self.report({'INFO'}, f"已删除旋转关键帧: {n}")
        refresh_animation_views()
        return {'FINISHED'}

# Euler
class ANIM_OT_clean_rote_x(Operator):
    bl_idname = "anim.clean_rote_x"
    bl_label = "删除Euler X旋转"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = delete_selected_keyframes_auto(context, kinds={"rotation_euler"}, indices={0})
        self.report({'INFO'}, f"已删除Euler X旋转关键帧: {n}")
        refresh_animation_views()
        return {'FINISHED'}

class ANIM_OT_clean_rote_y(Operator):
    bl_idname = "anim.clean_rote_y"
    bl_label = "删除Euler Y旋转"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = delete_selected_keyframes_auto(context, kinds={"rotation_euler"}, indices={1})
        self.report({'INFO'}, f"已删除Euler Y旋转关键帧: {n}")
        refresh_animation_views()
        return {'FINISHED'}

class ANIM_OT_clean_rote_z(Operator):
    bl_idname = "anim.clean_rote_z"
    bl_label = "删除Euler Z旋转"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = delete_selected_keyframes_auto(context, kinds={"rotation_euler"}, indices={2})
        self.report({'INFO'}, f"已删除Euler Z旋转关键帧: {n}")
        refresh_animation_views()
        return {'FINISHED'}

# Quaternion
class ANIM_OT_clean_rotq_all(Operator):
    bl_idname = "anim.clean_rotq_all"
    bl_label = "删除Quat WXYZ旋转"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = delete_selected_keyframes_auto(context, kinds={"rotation_quaternion"}, indices={0,1,2,3})
        self.report({'INFO'}, f"已删除四元数旋转关键帧: {n}")
        refresh_animation_views()
        return {'FINISHED'}

class ANIM_OT_clean_rotq_w(Operator):
    bl_idname = "anim.clean_rotq_w"
    bl_label = "删除Quat W"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = delete_selected_keyframes_auto(context, kinds={"rotation_quaternion"}, indices={0})
        self.report({'INFO'}, f"已删除Quat W旋转关键帧: {n}")
        refresh_animation_views()
        return {'FINISHED'}

class ANIM_OT_clean_rotq_x(Operator):
    bl_idname = "anim.clean_rotq_x"
    bl_label = "删除Quat X"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = delete_selected_keyframes_auto(context, kinds={"rotation_quaternion"}, indices={1})
        self.report({'INFO'}, f"已删除Quat X旋转关键帧: {n}")
        refresh_animation_views()
        return {'FINISHED'}

class ANIM_OT_clean_rotq_y(Operator):
    bl_idname = "anim.clean_rotq_y"
    bl_label = "删除Quat Y"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = delete_selected_keyframes_auto(context, kinds={"rotation_quaternion"}, indices={2})
        self.report({'INFO'}, f"已删除Quat Y旋转关键帧: {n}")
        refresh_animation_views()
        return {'FINISHED'}

class ANIM_OT_clean_rotq_z(Operator):
    bl_idname = "anim.clean_rotq_z"
    bl_label = "删除Quat Z"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        n = delete_selected_keyframes_auto(context, kinds={"rotation_quaternion"}, indices={3})
        self.report({'INFO'}, f"已删除Quat Z旋转关键帧: {n}")
        refresh_animation_views()
        return {'FINISHED'}

# 菜单（右键增强）
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
        obj = context.object
        # 判断是否为骨骼姿态模式
        is_pose_mode = obj and obj.type == 'ARMATURE' and context.mode == 'POSE'
        
        # 物体模式显示Euler旋转
        if not is_pose_mode:
            layout.label(text="Euler旋转")
            layout.separator()
            layout.operator(ANIM_OT_clean_rot_auto_all.bl_idname, text="全部Euler旋转")
            layout.separator()
            layout.operator(ANIM_OT_clean_rote_x.bl_idname, text="X旋转")
            layout.operator(ANIM_OT_clean_rote_y.bl_idname, text="Y旋转")
            layout.operator(ANIM_OT_clean_rote_z.bl_idname, text="Z旋转")
        
        # 骨骼姿态模式显示Quaternion四元数
        else:
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

# 右键（POSE 模式）扩展（来自第一份）
def draw_pose_context_menu(self, context):
    if context.mode != 'POSE':
        return
    layout = self.layout
    layout.separator()
    layout.label(text="选中关键帧清除:")
    col = layout.column(align=True)
    col.menu("POSE_MT_clear_location_menu", text="位置")
    col.menu("POSE_MT_clear_rotation_menu", text="旋转")
    col.menu("POSE_MT_clear_scale_menu", text="缩放")

# 为 POSE 菜单复用第一份的子菜单类名（将其加入注册）
class POSE_MT_clear_location_menu(Menu):
    bl_label = "位置关键帧清除"
    def draw(self, context):
        layout = self.layout
        layout.operator(POSE_OT_clear_location_all.bl_idname)
        layout.separator()
        layout.operator(POSE_OT_clear_location_x.bl_idname)
        layout.operator(POSE_OT_clear_location_y.bl_idname)
        layout.operator(POSE_OT_clear_location_z.bl_idname)

class POSE_MT_clear_rotation_menu(Menu):
    bl_label = "旋转关键帧清除"
    def draw(self, context):
        layout = self.layout
        layout.operator(POSE_OT_clear_rot_quat_all.bl_idname)
        layout.separator()
        layout.operator(POSE_OT_clear_rot_quat_w.bl_idname)
        layout.operator(POSE_OT_clear_rot_quat_x.bl_idname)
        layout.operator(POSE_OT_clear_rot_quat_y.bl_idname)
        layout.operator(POSE_OT_clear_rot_quat_z.bl_idname)

class POSE_MT_clear_scale_menu(Menu):
    bl_label = "缩放关键帧清除"
    def draw(self, context):
        layout = self.layout
        layout.operator(POSE_OT_clear_scale_all.bl_idname)
        layout.separator()
        layout.operator(POSE_OT_clear_scale_x.bl_idname)
        layout.operator(POSE_OT_clear_scale_y.bl_idname)
        layout.operator(POSE_OT_clear_scale_z.bl_idname)

# ------------------------------
# 注册表
# ------------------------------
_classes = [
    # POSE 专用（第一份）
    POSE_OT_clear_location_all, POSE_OT_clear_location_x, POSE_OT_clear_location_y, POSE_OT_clear_location_z,
    POSE_OT_clear_rot_quat_all, POSE_OT_clear_rot_quat_w, POSE_OT_clear_rot_quat_x, POSE_OT_clear_rot_quat_y, POSE_OT_clear_rot_quat_z,
    POSE_OT_clear_scale_all, POSE_OT_clear_scale_x, POSE_OT_clear_scale_y, POSE_OT_clear_scale_z,
    POSE_MT_clear_location_menu, POSE_MT_clear_rotation_menu, POSE_MT_clear_scale_menu,
    VIEW3D_PT_KeyframeCleanerPanel,
    # 右键增强（第二份）
    ANIM_OT_clean_loc_all, ANIM_OT_clean_loc_x, ANIM_OT_clean_loc_y, ANIM_OT_clean_loc_z,
    ANIM_OT_clean_scale_all, ANIM_OT_clean_scale_x, ANIM_OT_clean_scale_y, ANIM_OT_clean_scale_z,
    ANIM_OT_clean_rot_auto_all,
    ANIM_OT_clean_rote_x, ANIM_OT_clean_rote_y, ANIM_OT_clean_rote_z,
    ANIM_OT_clean_rotq_all, ANIM_OT_clean_rotq_w, ANIM_OT_clean_rotq_x, ANIM_OT_clean_rotq_y, ANIM_OT_clean_rotq_z,
    ANIM_MT_clean_location, ANIM_MT_clean_rotation, ANIM_MT_clean_scale
]

def register():
    # 防止重复注册尝试清理
    try:
        unregister()
    except Exception:
        pass
    for cls in _classes:
        try:
            register_class(cls)
        except Exception:
            print("注册类失败:", cls)
    # 右键菜单挂载（Dope Sheet / Timeline / Graph）
    if hasattr(bpy.types, 'DOPESHEET_MT_context_menu'):
        bpy.types.DOPESHEET_MT_context_menu.append(_draw_context_menu_block)
    if hasattr(bpy.types, 'TIMELINE_MT_context_menu'):
        bpy.types.TIMELINE_MT_context_menu.append(_draw_context_menu_block)
    if hasattr(bpy.types, 'GRAPH_MT_context_menu'):
        bpy.types.GRAPH_MT_context_menu.append(_draw_context_menu_block)
    # Pose 右键菜单挂载（3D视图 Pose 模式右键）
    if hasattr(bpy.types, 'VIEW3D_MT_pose_context_menu'):
        bpy.types.VIEW3D_MT_pose_context_menu.append(draw_pose_context_menu)
    print("[关键帧清除 — 合并增强版] 已注册。")

def unregister():
    # 移除右键挂载
    try:
        if hasattr(bpy.types, 'DOPESHEET_MT_context_menu'):
            bpy.types.DOPESHEET_MT_context_menu.remove(_draw_context_menu_block)
    except Exception:
        pass
    try:
        if hasattr(bpy.types, 'TIMELINE_MT_context_menu'):
            bpy.types.TIMELINE_MT_context_menu.remove(_draw_context_menu_block)
    except Exception:
        pass
    try:
        if hasattr(bpy.types, 'GRAPH_MT_context_menu'):
            bpy.types.GRAPH_MT_context_menu.remove(_draw_context_menu_block)
    except Exception:
        pass
    try:
        if hasattr(bpy.types, 'VIEW3D_MT_pose_context_menu'):
            bpy.types.VIEW3D_MT_pose_context_menu.remove(draw_pose_context_menu)
    except Exception:
        pass
    for cls in reversed(_classes):
        try:
            unregister_class(cls)
        except Exception:
            pass
    print("[关键帧清除 — 合并增强版] 已卸载。")

if __name__ == "__main__":
    register()
