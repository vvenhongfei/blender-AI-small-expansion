bl_info = {
    "name": "Curve Shape Keys Mirror (曲线形态键镜像工具)",
    "author": "vvenhongfei+GPT-5",
    "version": (1, 0, 0),
    "blender": (4, 5, 2),
    "location": "3D View > N Panel > Curve Mirror SK",
    "description": "一键镜像曲线及其所有形态键，修复镜像后方向/手柄问题；支持 Bezier/Poly/NURBS。",
    "category": "Object",
}

import bpy
from mathutils import Vector
import math  # 导入math模块用于数学计算

AXIS_MAP = {
    'X': Vector((-1.0, 1.0, 1.0)),
    'Y': Vector((1.0, -1.0, 1.0)),
    'Z': Vector((1.0, 1.0, -1.0)),
}

def mirror_vec(v: Vector, axis: str):
    """在对象局部坐标下对 xyz 进行镜像；NURBS 的 w（若有）保持不变。"""
    s = AXIS_MAP[axis]
    if len(v) == 3:
        return Vector((v.x * s.x, v.y * s.y, v.z * s.z))
    elif len(v) == 4:
        # NURBS: (x, y, z, w) -> 仅镜像 xyz，保持 w
        return Vector((v.x * s.x, v.y * s.y, v.z * s.z, v.w))
    else:
        return v.copy()

def swap_bezier_handles(bp):
    """交换贝塞尔左右手柄，常用于镜像后保持曲线方向的视觉一致性。"""
    hl = bp.handle_left.copy()
    hr = bp.handle_right.copy()
    bp.handle_left = hr
    bp.handle_right = hl

def foreach_curve_point(spline, keyblock_data, start_index):
    """迭代一个 spline 的点，并返回 (索引, data_point, 类型字符串)"""
    if spline.type == 'BEZIER':
        for i, _p in enumerate(spline.bezier_points):
            yield start_index + i, keyblock_data[start_index + i], 'BEZIER'
        return start_index + len(spline.bezier_points)
    else:
        # POLY 或 NURBS
        for i, _p in enumerate(spline.points):
            yield start_index + i, keyblock_data[start_index + i], 'POINT'
        return start_index + len(spline.points)

def mirror_keyblock(curve, keyblock, axis='X', swap_handles=False):
    """对某个形态键（KeyBlock）的所有点进行镜像"""
    idx = 0
    for spline in curve.splines:
        if spline.type == 'BEZIER':
            for _ in spline.bezier_points:
                bp = keyblock.data[idx]
                bp.co = mirror_vec(bp.co, axis)
                bp.handle_left  = mirror_vec(bp.handle_left, axis)
                bp.handle_right = mirror_vec(bp.handle_right, axis)
                if swap_handles:
                    swap_bezier_handles(bp)
                # 修正 Tilt：旋转-180度（使用弧度制）
                try:
                    bp.tilt -= math.pi  # 减去π弧度（即-180度）
                except AttributeError:
                    pass
                idx += 1
        else:
            for _ in spline.points:
                pp = keyblock.data[idx]
                pp.co = mirror_vec(pp.co, axis)
                # 修正 Tilt：旋转-180度（使用弧度制）
                try:
                    pp.tilt -= math.pi  # 减去π弧度（即-180度）
                except AttributeError:
                    pass
                idx += 1

def reverse_spline_direction_for_all_keys(curve, keyblocks):
    """反转每条 spline 的点序，确保一致性"""
    for kb in keyblocks:
        idx = 0
        for sp in curve.splines:
            if sp.type == 'BEZIER':
                count = len(sp.bezier_points)
                segment = [kb.data[idx + i].copy() for i in range(count)]
                segment.reverse()
                for i in range(count):
                    kb.data[idx + i].co = segment[i].co
                    try:
                        kb.data[idx + i].tilt = segment[i].tilt
                    except AttributeError:
                        pass
                    kb.data[idx + i].handle_left  = segment[i].handle_left
                    kb.data[idx + i].handle_right = segment[i].handle_right
                idx += count
            else:
                count = len(sp.points)
                segment = [kb.data[idx + i].copy() for i in range(count)]
                segment.reverse()
                for i in range(count):
                    kb.data[idx + i].co = segment[i].co
                    try:
                        kb.data[idx + i].tilt = segment[i].tilt
                    except AttributeError:
                        pass
                idx += count

class CURVE_OT_mirror_shapekeys(bpy.types.Operator):
    bl_idname = "curve.mirror_shapekeys"
    bl_label = "镜像曲线形态键"
    bl_options = {'REGISTER', 'UNDO'}

    axis: bpy.props.EnumProperty(
        name="镜像轴",
        items=[('X', 'X', '沿 X 轴镜像'),
               ('Y', 'Y', '沿 Y 轴镜像'),
               ('Z', 'Z', '沿 Z 轴镜像')],
        default='X'
    )
    make_copy: bpy.props.BoolProperty(
        name="创建镜像副本对象",
        description="勾选：复制一个新对象写入镜像结果；不勾选：在当前对象就地覆盖",
        default=True
    )
    swap_handles: bpy.props.BoolProperty(
        name="交换贝塞尔手柄",
        description="镜像后将 handle_left 与 handle_right 互换，缓解方向/切线错位",
        default=True
    )
    reverse_direction: bpy.props.BoolProperty(
        name="尝试反转曲线方向（高级）",
        description="对所有形态键统一反转每条曲线的点序；仅在方向仍有问题时启用",
        default=False
    )

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'CURVE':
            self.report({'ERROR'}, "请选择一个曲线（Curve）对象")
            return {'CANCELLED'}

        key = getattr(obj.data, "shape_keys", None)
        if not key or not key.key_blocks:
            self.report({'ERROR'}, "该曲线没有形态键（Shape Keys）")
            return {'CANCELLED'}

        # 目标对象
        if self.make_copy:
            # 复制对象与数据（确保数据独立）
            new_data = obj.data.copy()
            new_obj = obj.copy()
            new_obj.data = new_data
            new_obj.name = obj.name + "_MIR"
            new_data.name = obj.data.name + "_MIR"
            context.collection.objects.link(new_obj)
            dst = new_obj
        else:
            dst = obj

        # 对每个形态键做镜像
        key = dst.data.shape_keys
        blocks = list(key.key_blocks)
        for kb in blocks:
            mirror_keyblock(dst.data, kb,
                            axis=self.axis,
                            swap_handles=self.swap_handles)

        # 高级：反转每条曲线方向
        if self.reverse_direction:
            reverse_spline_direction_for_all_keys(dst.data, blocks)

        # 自动刷新视图，不需要手动调用 update
        context.view_layer.objects.active = dst

        if self.make_copy:
            # 将新对象与源对象的位移/旋转/缩放保持一致
            dst.scale = obj.scale.copy()
            dst.rotation_euler = obj.rotation_euler.copy()
            dst.location = obj.location.copy()

        # 选中并激活新对象（若创建副本）
        if self.make_copy:
            for o in context.selected_objects:
                o.select_set(False)
            dst.select_set(True)

        self.report({'INFO'}, f"镜像完成：{dst.name}  |  轴: {self.axis}")
        return {'FINISHED'}

class VIEW3D_PT_curve_mirror_sk(bpy.types.Panel):
    bl_label = "Curve Mirror SK"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Curve Mirror SK"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.label(text="镜像曲线形态键")
        col.prop(context.scene, "cmsk_axis", text="镜像轴")
        col.prop(context.scene, "cmsk_make_copy", text="创建镜像副本对象")
        col.prop(context.scene, "cmsk_swap_handles", text="交换贝塞尔手柄")
        col.prop(context.scene, "cmsk_reverse_direction", text="反转曲线方向（高级）")

        op = col.operator("curve.mirror_shapekeys", text="执行镜像", icon='MOD_MIRROR')
        op.axis = context.scene.cmsk_axis
        op.make_copy = context.scene.cmsk_make_copy
        op.swap_handles = context.scene.cmsk_swap_handles
        op.reverse_direction = context.scene.cmsk_reverse_direction

def _ensure_scene_props():
    sce = bpy.types.Scene
    if not hasattr(sce, "cmsk_axis"):
        sce.cmsk_axis = bpy.props.EnumProperty(
            name="Axis",
            items=[('X', 'X', ''), ('Y', 'Y', ''), ('Z', 'Z', '')],
            default='X'
        )
    if not hasattr(sce, "cmsk_make_copy"):
        sce.cmsk_make_copy = bpy.props.BoolProperty(
            name="Make Copy", default=True
        )
    if not hasattr(sce, "cmsk_swap_handles"):
        sce.cmsk_swap_handles = bpy.props.BoolProperty(
            name="Swap Handles", default=True
        )
    if not hasattr(sce, "cmsk_reverse_direction"):
        sce.cmsk_reverse_direction = bpy.props.BoolProperty(
            name="Reverse Direction", default=False
        )

classes = (
    CURVE_OT_mirror_shapekeys,
    VIEW3D_PT_curve_mirror_sk,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    _ensure_scene_props()

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()
