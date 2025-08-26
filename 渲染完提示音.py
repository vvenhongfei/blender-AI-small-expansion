bl_info = {
    "name": "渲染完成提示音",
    "description": "移除噪音波形，仅保留正弦波、锯齿波和方波",
    "author": "vvenhongfei",
    "version": (2, 1, 5),
    "blender": (4, 5, 0),
    "location": "属性窗口 -> 渲染输出",
    "category": "Render"
}

import bpy
import aud
import time
from bpy.app.handlers import persistent

# ---------------------------- 调试工具模块 ----------------------------
def dprint(message: str):
    """带开关的调试打印函数"""
    try:
        prefs = bpy.context.preferences.addons[__name__].preferences
        if prefs.developer_print:
            print(f"[渲染提示音] {message}")
    except:
        print(f"[渲染提示音] {message}")

# ---------------------------- 音频设备管理模块 ----------------------------
class AudioDeviceManager:
    _instance = None
    _retry_count = 0
    MAX_RETRIES = 5
    _first_render = True
    
    @classmethod
    def get_device(cls):
        """获取或创建音频设备"""
        if cls._instance is None or not cls.is_device_valid():
            cls._retry_count = 0
            cls._instance = cls._create_device()
        return cls._instance
    
    @classmethod
    def is_device_valid(cls):
        """检查设备是否有效"""
        try:
            return cls._instance is not None and cls._instance.volume is not None
        except:
            return False
    
    @classmethod
    def _create_device(cls):
        """创建音频设备，带重试机制"""
        for attempt in range(1, cls.MAX_RETRIES + 1):
            try:
                device = aud.Device()
                
                # 获取音量设置
                try:
                    prefs = bpy.context.preferences.addons[__name__].preferences
                    volume = prefs.default_volume
                except:
                    volume = 0.6
                
                device.volume = volume
                dprint(f"音频设备初始化成功 (尝试 {attempt}/{cls.MAX_RETRIES})")
                return device
            except Exception as e:
                dprint(f"音频设备初始化失败 ({attempt}/{cls.MAX_RETRIES}): {str(e)}")
                time.sleep(0.5 * attempt)
        dprint("所有尝试均失败，使用备用方案")
        return cls._fallback_device()
    
    @classmethod
    def _fallback_device(cls):
        """备用设备创建方案"""
        try:
            device = aud.Device()
            device.volume = 0.6
            dprint("备用设备初始化成功")
            return device
        except:
            dprint("备用设备初始化也失败")
            return None
    
    @classmethod
    def reset_device(cls):
        """重置音频设备"""
        dprint("重置音频设备...")
        cls._instance = None
        cls._first_render = True
        return cls.get_device()
    
    @classmethod
    def mark_first_render(cls):
        """标记首次渲染已完成"""
        cls._first_render = False
        
    @classmethod
    def update_volume(cls, volume):
        """更新设备音量（限制范围）"""
        volume_clamped = max(0.0, min(1.0, volume))
        if cls.is_device_valid():
            try:
                cls._instance.volume = volume_clamped
                return True
            except Exception as e:
                dprint(f"更新音量失败: {str(e)}")
        return False

# ---------------------------- 声音生成模块（已移除噪音波形） ----------------------------
def create_sound():
    """创建提示音，仅包含正弦波、锯齿波和方波"""
    try:
        # 获取用户设置
        try:
            prefs = bpy.context.preferences.addons[__name__].preferences
            sound_type = prefs.sound_type
            frequency = prefs.frequency
            duration = prefs.duration
            fadeout = prefs.fadeout
            user_loop_count = prefs.loop_count  # 用户设置的循环总次数
            dprint(f"用户设置 - 波形: {sound_type}, 循环次数: {user_loop_count}次")
        except Exception as e:
            dprint(f"获取设置失败: {e}，使用默认参数")
            sound_type = 'SINE'
            frequency = 330
            duration = 0.3
            fadeout = 0.15
            user_loop_count = 2
        
        # 1. 通用参数处理
        frequency = max(100, min(1500, frequency))
        duration = max(0.2, min(3.0, duration))
        max_fadeout = duration * 0.8
        fadeout = max(0.05, min(fadeout, max_fadeout))
        
        # 2. 循环次数计算
        repeat_count = max(0, user_loop_count - 1)  # 计算重复次数
        dprint(f"循环转换 - 用户设置{user_loop_count}次 → 实际重复{repeat_count}次")
        
        # 3. 波形生成（已移除噪音选项）
        if sound_type == 'SINE':
            sound = aud.Sound.sine(frequency, 48000)
            dprint("使用正弦波生成声音")
            
        elif sound_type == 'SAWTOOTH':
            sound = aud.Sound.sawtooth(frequency, 48000)
            dprint("使用锯齿波生成声音")
            
        elif sound_type == 'SQUARE':
            sound = aud.Sound.square(frequency, 48000)
            dprint("使用方波生成声音")
            
        else:
            sound = aud.Sound.sine(frequency, 48000)
            dprint(f"未知波形类型: {sound_type}，使用正弦波替代")
        
        # 4. 声音处理
        sound = sound.limit(0, duration)
        dprint(f"应用时长: {duration}秒")
        
        sound = sound.fadeout(duration - fadeout, fadeout)
        dprint(f"应用淡出: {fadeout}秒")
        
        sound = sound.loop(repeat_count)
        dprint(f"应用循环: {repeat_count}次重复")
        
        return sound
        
    except Exception as e:
        dprint(f"创建声音失败: {str(e)}")
        # 备用声音
        return aud.Sound.sine(330, 48000).limit(0, 0.3).fadeout(0.15, 0.15).loop(1)  # 总2次

# ---------------------------- 声音播放模块 ----------------------------
def safe_play_sound(force_retry=False):
    """安全播放提示音"""
    if AudioDeviceManager._first_render or force_retry:
        AudioDeviceManager.reset_device()
        AudioDeviceManager.mark_first_render()
    
    device = AudioDeviceManager.get_device()
    if not device:
        dprint("无法播放提示音：没有可用的音频设备")
        return False
    
    try:
        sound = create_sound()
        device.stopAll()  # 停止所有可能的残留声音
        handle = device.play(sound)
        
        if handle and hasattr(handle, 'status'):
            dprint("提示音播放已触发")
            return True
        else:
            dprint("播放句柄无效")
            return False
    except Exception as e:
        dprint(f"播放提示音失败: {str(e)}")
        return False

def play_delayed_sound():
    """延迟播放声音，带重试机制"""
    if safe_play_sound():
        dprint("提示音播放成功")
        return None
    
    # 首次重试
    def retry_first():
        if safe_play_sound(force_retry=True):
            dprint("提示音在首次重试后播放成功")
            return None
        
        # 第二次重试
        def retry_second():
            if safe_play_sound(force_retry=True):
                dprint("提示音在第二次重试后播放成功")
                return None
                
            # 第三次重试
            def retry_third():
                try:
                    prefs = bpy.context.preferences.addons[__name__].preferences
                    prefs.default_volume = 0.8
                except:
                    pass
                    
                if safe_play_sound(force_retry=True):
                    dprint("提示音在第三次重试后播放成功")
                    return None
                    
                dprint("所有尝试都失败，无法播放提示音")
                return None
                
            bpy.app.timers.register(retry_third, first_interval=2.0)
            return None
            
        bpy.app.timers.register(retry_second, first_interval=1.0)
        return None
        
    bpy.app.timers.register(retry_first, first_interval=0.5)
    return None

# ---------------------------- 事件处理器模块 ----------------------------
@persistent
def render_complete_handler(scene):
    """渲染完成事件处理器"""
    dprint("检测到渲染完成事件")
    
    try:
        prefs = bpy.context.preferences.addons[__name__].preferences
        if not prefs.enable_render_sound:
            dprint("根据设置，不播放提示音")
            return
    except Exception as e:
        dprint(f"检查播放设置时出错: {str(e)}，继续播放提示音")
    
    # 确保设备已初始化并更新音量
    device = AudioDeviceManager.get_device()
    if not device:
        dprint("音频设备未就绪，尝试初始化...")
        device = AudioDeviceManager.reset_device()
    
    # 更新音量
    try:
        prefs = bpy.context.preferences.addons[__name__].preferences
        AudioDeviceManager.update_volume(prefs.default_volume)
    except:
        AudioDeviceManager.update_volume(0.6)
    
    # 延迟播放
    dprint("准备播放提示音...")
    bpy.app.timers.register(play_delayed_sound, first_interval=0.1, persistent=False)

# ---------------------------- Handler管理模块 ----------------------------
HANDLERS = [
    (render_complete_handler, bpy.app.handlers.render_complete),
]

def register_handlers(dummy=None):
    """注册并管理handlers，避免重复注册"""
    if bpy.app.background:
        return

    for func, handler_list in HANDLERS:
        func_name = func.__name__
        for existing in list(handler_list):
            if getattr(existing, "__name__", None) == func_name:
                handler_list.remove(existing)
                dprint(f"已移除旧handler: {func_name}")
        handler_list.append(func)
        dprint(f"已注册新handler: {func_name}")

    self_name = register_handlers.__name__
    for existing in list(bpy.app.handlers.load_post):
        if getattr(existing, "__name__", None) == self_name:
            bpy.app.handlers.load_post.remove(existing)
            dprint(f"已从load_post移除: {self_name}")
    bpy.app.handlers.load_post.append(register_handlers)
    dprint(f"已在load_post注册: {self_name}")

# ---------------------------- 操作类模块 ----------------------------
class ResetAudioDeviceOperator(bpy.types.Operator):
    bl_idname = "render.reset_audio_device"
    bl_label = "重置音频设备"
    bl_description = "重新初始化音频设备"
    
    def execute(self, context):
        device = AudioDeviceManager.reset_device()
        if device:
            self.report({'INFO'}, "音频设备重置成功")
        else:
            self.report({'WARNING'}, "音频设备重置失败，请检查系统音频")
        return {'FINISHED'}

class TestSoundOperator(bpy.types.Operator):
    bl_idname = "render.test_sound"
    bl_label = "测试提示音"
    bl_description = "播放当前设置的提示音，验证循环次数"
    
    def execute(self, context):
        try:
            prefs = bpy.context.preferences.addons[__name__].preferences
            loop_count = prefs.loop_count
            sound_type = prefs.sound_type
            result = safe_play_sound(force_retry=True)
            if result:
                self.report({'INFO'}, f"{sound_type} 提示音已播放（设置次数: {loop_count}次）")
            else:
                self.report({'WARNING'}, f"{sound_type} 提示音播放失败")
        except Exception as e:
            self.report({'ERROR'}, f"测试提示音出错: {str(e)}")
        return {'FINISHED'}

class OpenSoundSettingsOperator(bpy.types.Operator):
    bl_idname = "render.open_sound_settings"
    bl_label = "打开设置"
    bl_description = "打开插件设置面板"
    
    def execute(self, context):
        bpy.ops.preferences.addon_show(module=__name__)
        return {'FINISHED'}

# ---------------------------- 界面面板模块 ----------------------------
class RenderSoundPanel(bpy.types.Panel):
    bl_label = "渲染完成提示音"
    bl_idname = "OBJECT_PT_render_sound"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "output"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        
        # 插件状态
        box = layout.box()
        box.label(text="插件状态", icon='INFO')
        
        # 设备状态
        device = AudioDeviceManager.get_device()
        row = box.row()
        row.label(text="音频设备: ")
        status_icon = 'CHECKMARK' if device else 'ERROR'
        status_text = "已就绪" if device else "未初始化"
        row.label(text=status_text, icon=status_icon)
        
        # 快速设置
        box = layout.box()
        box.label(text="提示设置", icon='PLAY')
        
        try:
            prefs = bpy.context.preferences.addons[__name__].preferences
            row = box.row()
            row.prop(prefs, "enable_render_sound", text="启用渲染完成提示")
            
            row = box.row()
            row.prop(prefs, "sound_type", text="波形类型")  # 已不含噪音选项
            
            row = box.row()
            row.prop(prefs, "loop_count", text="循环次数")
            
            row = box.row()
            row.prop(prefs, "default_volume", text="音量")
        except:
            box.label(text="无法加载设置", icon='ERROR')
        
        # 操作按钮
        col = layout.column(align=True)
        col.operator("render.test_sound", text="测试提示音", icon='SOUND')
        col.operator("render.reset_audio_device", text="重置音频设备", icon='FILE_REFRESH')
        col.operator("render.open_sound_settings", text="高级设置...", icon='PREFERENCES')
        
        if AudioDeviceManager._first_render:
            layout.label(text="首次渲染将初始化音频设备", icon='INFO')

# ---------------------------- 偏好设置模块（已移除噪音波形） ----------------------------
class RenderSoundPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__
    
    enable_render_sound: bpy.props.BoolProperty(
        name="启用渲染完成提示",
        default=True
    )
    
    default_volume: bpy.props.FloatProperty(
        name="默认音量",
        default=0.6,
        min=0.0,
        max=1.0,
        step=10,
        precision=2,
        description="提示音的默认音量（0.0-1.0）"
    )
    
    sound_type: bpy.props.EnumProperty(
        name="提示音类型",
        items=[
            ('SINE', "正弦波", "平滑圆润的基础波形"),
            ('SAWTOOTH', "锯齿波", "带有金属感的波形"),
            ('SQUARE', "方波", "颗粒感明显的波形")
            # 已移除噪音选项
        ],
        default='SINE'
    )
    
    frequency: bpy.props.IntProperty(
        name="频率",
        default=330,
        min=100,
        max=1500,
        description="提示音频率(Hz)，100-1500为舒适范围"
    )
    
    duration: bpy.props.FloatProperty(
        name="单音持续时间",
        default=0.3,
        min=0.2,
        max=3.0,
        step=10,
        precision=2,
        description="单个提示音的持续时间(秒)"
    )
    
    fadeout: bpy.props.FloatProperty(
        name="淡出时间",
        default=0.15,
        min=0.05,
        max=1.0,
        step=10,
        precision=2,
        description="提示音结束时的淡出时间(秒)"
    )
    
    loop_count: bpy.props.IntProperty(
        name="循环总次数",
        default=2,
        min=1,
        max=6,
        description="所有声音类型将严格遵循的播放总次数（1-6次）"
    )
    
    developer_print: bpy.props.BoolProperty(
        name="启用调试打印",
        description="在控制台显示详细的处理过程",
        default=False
    )
    
    def draw(self, context):
        layout = self.layout
        
        box = layout.box()
        box.label(text="提示音触发设置", icon='SETTINGS')
        box.prop(self, "enable_render_sound")
        
        box = layout.box()
        box.label(text="提示音参数设置", icon='SOUND')
        box.prop(self, "sound_type")  # 已不含噪音选项
        box.prop(self, "frequency")
        box.prop(self, "duration")
        box.prop(self, "fadeout")
        box.prop(self, "loop_count")
        box.prop(self, "default_volume")
        
        box = layout.box()
        box.label(text="重要说明", icon='INFO')
        box.label(text="• 所有声音类型使用相同的参数处理逻辑")
        box.label(text="• 循环次数对所有波形生效，设置值即实际播放次数")
        
        layout.label(text="开发者选项", icon='CONSOLE')
        layout.prop(self, "developer_print")

# ---------------------------- 插件生命周期管理 ----------------------------
def register():
    if bpy.app.background:
        return

    bpy.utils.register_class(RenderSoundPreferences)
    bpy.utils.register_class(RenderSoundPanel)
    bpy.utils.register_class(ResetAudioDeviceOperator)
    bpy.utils.register_class(TestSoundOperator)
    bpy.utils.register_class(OpenSoundSettingsOperator)
    
    prefs = bpy.context.preferences.addons.get(__name__).preferences
    if prefs:
        AudioDeviceManager.get_device()
    
    dprint("注册渲染完成提示音插件...")
    register_handlers()
    dprint("渲染完成提示音插件初始化完成")

def unregister():
    if bpy.app.background:
        return

    dprint("卸载渲染完成提示音插件...")
    for func, handler_list in HANDLERS:
        func_name = func.__name__
        for existing in list(handler_list):
            if getattr(existing, "__name__", None) == func_name:
                handler_list.remove(existing)
                dprint(f"已移除handler: {func_name}")
                break
    
    self_name = register_handlers.__name__
    for existing in list(bpy.app.handlers.load_post):
        if getattr(existing, "__name__", None) == self_name:
            bpy.app.handlers.load_post.remove(existing)
            dprint(f"已从load_post移除: {self_name}")
            break
    
    bpy.utils.unregister_class(RenderSoundPreferences)
    bpy.utils.unregister_class(RenderSoundPanel)
    bpy.utils.unregister_class(ResetAudioDeviceOperator)
    bpy.utils.unregister_class(TestSoundOperator)
    bpy.utils.unregister_class(OpenSoundSettingsOperator)
    
    if AudioDeviceManager._instance:
        try:
            AudioDeviceManager._instance.stopAll()
        except:
            pass
        AudioDeviceManager._instance = None
    
    dprint("渲染完成提示音插件已卸载")

if __name__ == "__main__":
    register()
    