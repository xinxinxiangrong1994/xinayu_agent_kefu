"""闲鱼智能客服 - 可视化界面（新版侧边栏布局）"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import asyncio
import sys
import os
import json
import ctypes
from pathlib import Path

# 确保能找到其他模块
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv, set_key
from loguru import logger
from logger_setup import set_gui_conversation_callback, rebind_console_output
from config import DEFAULT_STATUS_MAPPING, DEFAULT_COZE_VARS, Config


def _extract_status_mapping_values(value):
    """从状态映射值中提取 mapped 和 system_msg 字段"""
    if isinstance(value, dict):
        return value.get('mapped', ''), value.get('system_msg', '')
    return value, ''


class XianyuGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("闲鱼智能客服 RPA")
        self.root.geometry("1200x750")
        self.root.minsize(1000, 650)
        self.root.resizable(True, True)

        # 状态变量
        self.is_running = False
        self.handler = None
        self.loop = None
        self.thread = None
        self.show_debug_logs = False
        self.log_handler_id = None

        # 控制台窗口状态
        self.console_visible = False
        self._init_console_control()

        # Coze变量配置
        self.coze_vars_config = {}
        self.status_mapping = {}
        self.prompt_content = ''
        self.title_grab_length = 15  # 默认抓取标题字符数
        self.vars_config_path = Path(__file__).parent / "coze_vars_config.json"

        # 加载当前配置
        self.env_path = Path(__file__).parent / ".env"
        load_dotenv(self.env_path)

        self._load_coze_vars_config()

        # 当前页面
        self.current_page = None
        self.pages = {}
        self.nav_buttons = {}

        # 创建主界面
        self._create_main_layout()
        self._load_config()

        # 重定向日志到界面
        self._setup_logging()

        # 注册对话记录回调
        self._register_conversation_callback()

        # 默认显示概览页
        self._show_page("overview")

    def _create_main_layout(self):
        """创建主布局：左侧导航 + 右侧内容"""
        # 主容器
        main_container = ttk.Frame(self.root)
        main_container.pack(fill="both", expand=True)

        # ===== 左侧导航栏 =====
        self.nav_frame = tk.Frame(main_container, bg="#1a5fb4", width=140)
        self.nav_frame.pack(side="left", fill="y")
        self.nav_frame.pack_propagate(False)

        # Logo/标题区域
        logo_frame = tk.Frame(self.nav_frame, bg="#1a5fb4", height=60)
        logo_frame.pack(fill="x")
        logo_frame.pack_propagate(False)

        tk.Label(
            logo_frame,
            text="闲鱼RPA",
            font=("Microsoft YaHei", 14, "bold"),
            fg="white",
            bg="#1a5fb4"
        ).pack(expand=True)

        # 导航按钮
        nav_items = [
            ("overview", "概览"),
            ("reply_settings", "回复设置"),
            ("memory", "跨窗口记忆"),
            ("merge", "多消息合并"),
            ("coze_sessions", "会话管理"),
            ("sync_products", "同步商品"),
            ("system_settings", "系统设置"),
        ]

        for page_id, text in nav_items:
            btn = tk.Button(
                self.nav_frame,
                text=text,
                font=("Microsoft YaHei", 10),
                fg="white",
                bg="#1a5fb4",
                activebackground="#3584e4",
                activeforeground="white",
                bd=0,
                pady=12,
                cursor="hand2",
                command=lambda p=page_id: self._show_page(p)
            )
            btn.pack(fill="x")
            self.nav_buttons[page_id] = btn

            # 鼠标悬停效果
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg="#3584e4") if b != self.nav_buttons.get(self.current_page) else None)
            btn.bind("<Leave>", lambda e, b=btn, p=page_id: b.config(bg="#1a5fb4") if p != self.current_page else None)

        # ===== 右侧内容区域 =====
        self.content_frame = ttk.Frame(main_container)
        self.content_frame.pack(side="right", fill="both", expand=True)

        # 创建各个页面
        self._create_overview_page()
        self._create_reply_settings_page()
        self._create_memory_page()
        self._create_merge_page()
        self._create_coze_sessions_page()
        self._create_sync_products_page()
        self._create_system_settings_page()

    def _show_page(self, page_id):
        """切换显示页面"""
        # 隐藏所有页面
        for page in self.pages.values():
            page.pack_forget()

        # 更新导航按钮样式
        for pid, btn in self.nav_buttons.items():
            if pid == page_id:
                btn.config(bg="#3584e4")
            else:
                btn.config(bg="#1a5fb4")

        # 显示目标页面
        self.current_page = page_id
        if page_id in self.pages:
            self.pages[page_id].pack(fill="both", expand=True)

            # 如果是Coze会话页，自动刷新列表
            if page_id == "coze_sessions" and hasattr(self, '_refresh_coze_sessions'):
                self._refresh_coze_sessions()

            # 如果是同步商品页，自动刷新列表
            if page_id == "sync_products" and hasattr(self, '_refresh_products_list'):
                self._refresh_products_list()

    # ==================== 概览页 ====================
    def _create_overview_page(self):
        """创建概览页"""
        page = ttk.Frame(self.content_frame)
        self.pages["overview"] = page

        # 顶部控制栏
        control_frame = ttk.Frame(page)
        control_frame.pack(fill="x", padx=20, pady=15)

        # 启动/停止按钮
        self.start_btn = ttk.Button(
            control_frame,
            text="启动",
            command=self._toggle_running,
            width=12
        )
        self.start_btn.pack(side="left", padx=5)

        # 状态标签
        self.status_var = tk.StringVar(value="已停止")
        self.status_label = tk.Label(
            control_frame,
            textvariable=self.status_var,
            font=("Microsoft YaHei", 10),
            fg="gray"
        )
        self.status_label.pack(side="left", padx=20)

        # 清空所有会话按钮
        ttk.Button(
            control_frame,
            text="清空所有会话",
            command=self._clear_all_sessions,
            width=12
        ).pack(side="right", padx=5)

        # 控制台显示/隐藏按钮
        self.console_btn = ttk.Button(
            control_frame,
            text="显示控制台",
            command=self._toggle_console,
            width=10
        )
        self.console_btn.pack(side="right", padx=5)

        # 运行日志区域
        log_frame = ttk.LabelFrame(page, text="运行日志", padding=10)
        log_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # 创建 Notebook（对话记录/系统日志）
        self.log_notebook = ttk.Notebook(log_frame)
        self.log_notebook.pack(fill="both", expand=True)

        # Tab 1: 对话记录表格
        conv_tab = ttk.Frame(self.log_notebook)
        self.log_notebook.add(conv_tab, text="对话记录")

        # 对话记录表格
        conv_columns = ('time', 'level', 'type', 'username', 'content', 'conv_id', 'order_status')
        self.conv_tree = ttk.Treeview(conv_tab, columns=conv_columns, show='headings', height=15)
        self.conv_tree.heading('time', text='时间')
        self.conv_tree.heading('level', text='级别')
        self.conv_tree.heading('type', text='类型')
        self.conv_tree.heading('username', text='用户名')
        self.conv_tree.heading('content', text='内容')
        self.conv_tree.heading('conv_id', text='会话ID')
        self.conv_tree.heading('order_status', text='订单状态')

        self.conv_tree.column('time', width=70, minwidth=60, anchor='center')
        self.conv_tree.column('level', width=50, minwidth=40, anchor='center')
        self.conv_tree.column('type', width=50, minwidth=40, anchor='center')
        self.conv_tree.column('username', width=100, minwidth=80, anchor='center')
        self.conv_tree.column('content', width=400, minwidth=250, anchor='w')
        self.conv_tree.column('conv_id', width=160, minwidth=120, anchor='center')
        self.conv_tree.column('order_status', width=80, minwidth=60, anchor='center')

        conv_scrollbar = ttk.Scrollbar(conv_tab, orient="vertical", command=self.conv_tree.yview)
        self.conv_tree.configure(yscrollcommand=conv_scrollbar.set)
        self.conv_tree.pack(side="left", fill="both", expand=True)
        conv_scrollbar.pack(side="right", fill="y")

        # 设置行颜色
        self.conv_tree.tag_configure('user', background='#e3f2fd')
        self.conv_tree.tag_configure('ai', background='#f3e5f5')
        self.conv_tree.tag_configure('info', background='#ffffff')
        self.conv_tree.tag_configure('warning', background='#fff8e1')
        self.conv_tree.tag_configure('error', background='#ffebee')

        # Tab 2: 系统日志
        sys_tab = ttk.Frame(self.log_notebook)
        self.log_notebook.add(sys_tab, text="系统日志")

        self.log_text = scrolledtext.ScrolledText(
            sys_tab,
            height=15,
            font=("Consolas", 9),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
            state="disabled"
        )
        self.log_text.pack(fill="both", expand=True)

        # 配置日志颜色标签
        self.log_text.tag_configure("INFO", foreground="#4ec9b0")
        self.log_text.tag_configure("DEBUG", foreground="#808080")
        self.log_text.tag_configure("WARNING", foreground="#dcdcaa")
        self.log_text.tag_configure("ERROR", foreground="#f14c4c")
        self.log_text.tag_configure("SUCCESS", foreground="#6a9955")
        self.log_text.tag_configure("TIME", foreground="#569cd6")

        # 日志控制区域
        log_control_frame = ttk.Frame(log_frame)
        log_control_frame.pack(fill="x", pady=5)

        self.debug_log_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            log_control_frame,
            text="显示详细日志",
            variable=self.debug_log_var,
            command=self._toggle_debug_logs
        ).pack(side="left")

        ttk.Button(log_control_frame, text="清空日志", command=self._clear_log).pack(side="right")

    # ==================== 回复设置页 ====================
    def _create_reply_settings_page(self):
        """创建回复设置页"""
        page = ttk.Frame(self.content_frame)
        self.pages["reply_settings"] = page

        # 设置区域
        settings_frame = ttk.LabelFrame(page, text="回复设置", padding=15)
        settings_frame.pack(fill="x", padx=20, pady=15)

        # 检查间隔
        row1 = ttk.Frame(settings_frame)
        row1.pack(fill="x", pady=8)
        ttk.Label(row1, text="检查间隔 (秒):", width=15).pack(side="left")
        self.interval_var = tk.StringVar(value="2")
        interval_spinbox = ttk.Spinbox(row1, from_=1, to=60, textvariable=self.interval_var, width=8)
        interval_spinbox.pack(side="left", padx=5)
        interval_spinbox.bind("<FocusOut>", lambda e: self._auto_save_config())

        # 重复消息过滤
        row2 = ttk.Frame(settings_frame)
        row2.pack(fill="x", pady=8)
        ttk.Label(row2, text="重复消息过滤:", width=15).pack(side="left")
        self.skip_duplicate_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="启用", variable=self.skip_duplicate_var,
                       command=self._on_duplicate_toggle).pack(side="left")
        ttk.Label(row2, text="过期时间:").pack(side="left", padx=(20, 5))
        self.msg_expire_var = tk.StringVar(value="60")
        self.msg_expire_spinbox = ttk.Spinbox(row2, from_=0, to=300, textvariable=self.msg_expire_var, width=6)
        self.msg_expire_spinbox.pack(side="left")
        self.msg_expire_spinbox.bind("<FocusOut>", lambda e: self._auto_save_config())
        ttk.Label(row2, text="秒").pack(side="left", padx=3)

        # 主动发消息
        row3 = ttk.Frame(settings_frame)
        row3.pack(fill="x", pady=8)
        ttk.Label(row3, text="主动发消息:", width=15).pack(side="left")
        self.inactive_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row3, text="启用", variable=self.inactive_enabled_var,
                       command=self._on_inactive_toggle).pack(side="left")
        ttk.Label(row3, text="超时:").pack(side="left", padx=(20, 5))
        self.inactive_timeout_var = tk.StringVar(value="3")
        self.inactive_timeout_spinbox = ttk.Spinbox(row3, from_=1, to=30, textvariable=self.inactive_timeout_var, width=5)
        self.inactive_timeout_spinbox.pack(side="left")
        self.inactive_timeout_spinbox.bind("<FocusOut>", lambda e: self._auto_save_config())
        ttk.Label(row3, text="分钟").pack(side="left", padx=3)

        # 会话切入延迟
        row4 = ttk.Frame(settings_frame)
        row4.pack(fill="x", pady=8)
        ttk.Label(row4, text="会话切入延迟:", width=15).pack(side="left")
        self.enter_delay_var = tk.StringVar(value="1.5")
        enter_delay_spinbox = ttk.Spinbox(row4, from_=0.5, to=5.0, increment=0.5,
                                          textvariable=self.enter_delay_var, width=6)
        enter_delay_spinbox.pack(side="left")
        enter_delay_spinbox.bind("<FocusOut>", lambda e: self._auto_save_config())
        ttk.Label(row4, text="秒 (进入会话后等待页面加载)").pack(side="left", padx=5)

        # 系统提示词
        prompt_frame = ttk.LabelFrame(page, text="系统提示词 (prompt)", padding=15)
        prompt_frame.pack(fill="both", expand=True, padx=20, pady=10)

        ttk.Label(prompt_frame, text="在 Coze 智能体的人设中使用 {{prompt}} 引用此变量:").pack(anchor="w")

        self.prompt_text = tk.Text(prompt_frame, height=8, font=("Microsoft YaHei", 9))
        self.prompt_text.pack(fill="both", expand=True, pady=5)
        self.prompt_text.bind("<FocusOut>", lambda e: self._auto_save_config())

    # ==================== 跨窗口记忆页 ====================
    def _create_memory_page(self):
        """创建跨窗口记忆页"""
        page = ttk.Frame(self.content_frame)
        self.pages["memory"] = page

        # 标题
        ttk.Label(
            page,
            text="跨窗口记忆 - 跨商品上下文传递",
            font=("Microsoft YaHei", 12, "bold")
        ).pack(pady=15)

        # 说明文字
        desc_frame = ttk.LabelFrame(page, text="功能说明", padding=10)
        desc_frame.pack(fill="x", padx=20, pady=5)

        desc_text = """当同一个用户从不同商品页面发起聊天时，系统会自动获取该用户之前与其他商品的对话历史，
并将这些历史记录作为上下文传递给新会话的第一条消息，帮助AI更好地了解用户的需求和偏好。

适用场景：
• 用户咨询过商品A后，又来咨询商品B
• 用户是回头客，之前有过购买/咨询记录
• 需要跨商品保持对话连贯性的场景"""

        ttk.Label(desc_frame, text=desc_text, justify="left", wraplength=800).pack(anchor="w")

        # 设置区域
        settings_frame = ttk.LabelFrame(page, text="设置", padding=15)
        settings_frame.pack(fill="x", padx=20, pady=10)

        # 启用开关
        row1 = ttk.Frame(settings_frame)
        row1.pack(fill="x", pady=8)
        self.memory_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row1, text="启用跨窗口记忆功能", variable=self.memory_enabled_var,
                       command=self._auto_save_config).pack(side="left")

        # 上下文轮数
        row2 = ttk.Frame(settings_frame)
        row2.pack(fill="x", pady=8)
        ttk.Label(row2, text="获取历史对话轮数:").pack(side="left")
        self.memory_rounds_var = tk.StringVar(value="5")
        memory_spinbox = ttk.Spinbox(row2, from_=1, to=20, textvariable=self.memory_rounds_var, width=5)
        memory_spinbox.pack(side="left", padx=5)
        memory_spinbox.bind("<FocusOut>", lambda e: self._auto_save_config())
        ttk.Label(row2, text="轮 (每轮包含用户问+AI答)").pack(side="left")

        # 示例展示
        example_frame = ttk.LabelFrame(page, text="传递给新会话的 input 内容示例", padding=10)
        example_frame.pack(fill="both", expand=True, padx=20, pady=10)

        example_text = scrolledtext.ScrolledText(example_frame, height=12, font=("Consolas", 9), bg="#f5f5f5")
        example_text.pack(fill="both", expand=True)

        example_content = """[历史会话记录]
会话ID: 7593074481959125027
商品ID: 7890123456
商品标题：小米10 PRO 内存12+512

对话内容:
user：你好，这个手机是什么颜色的？
AI：这款是黑色的哦，成色很新。
user：电池健康度怎么样？
AI：电池健康度92%，续航很好的。
user：价格能便宜点吗？
AI：已经是最低价了呢，质量绝对有保障。

当前消息：你好，这个耳机还在吗？"""

        example_text.insert("1.0", example_content)
        example_text.config(state="disabled")

    # ==================== 多消息合并页 ====================
    def _create_merge_page(self):
        """创建多消息合并页"""
        page = ttk.Frame(self.content_frame)
        self.pages["merge"] = page

        # 标题
        ttk.Label(
            page,
            text="多消息合并 - 防止用户分段发送导致AI回复混乱",
            font=("Microsoft YaHei", 12, "bold")
        ).pack(pady=15)

        # 说明文字
        desc_frame = ttk.LabelFrame(page, text="功能说明", padding=10)
        desc_frame.pack(fill="x", padx=20, pady=5)

        desc_text = """当用户快速连续发送多条短消息时（如"pro"、"还有"、"吗"），系统会等待一段时间，
将这些消息合并成一条完整的消息（"pro还有吗"）再发送给AI处理，避免AI对不完整的消息产生错误回复。

工作原理：
• 当收到长度小于阈值的短消息时，消息会进入等待队列
• 在等待时间内收到的新消息会不断追加到队列中
• 等待时间结束后，所有排队消息会合并成一条发送给AI
• 如果收到一条长消息，会立即将之前排队的消息一起合并处理"""

        ttk.Label(desc_frame, text=desc_text, justify="left", wraplength=800).pack(anchor="w")

        # 设置区域
        settings_frame = ttk.LabelFrame(page, text="设置", padding=15)
        settings_frame.pack(fill="x", padx=20, pady=10)

        # 启用开关
        row1 = ttk.Frame(settings_frame)
        row1.pack(fill="x", pady=8)
        self.merge_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row1, text="启用多消息合并功能", variable=self.merge_enabled_var,
                       command=self._auto_save_config).pack(side="left")

        # 等待时间
        row2 = ttk.Frame(settings_frame)
        row2.pack(fill="x", pady=8)
        ttk.Label(row2, text="等待合并时间:").pack(side="left")
        self.merge_wait_var = tk.StringVar(value="3")
        merge_wait_spinbox = ttk.Spinbox(row2, from_=1, to=10, textvariable=self.merge_wait_var, width=5)
        merge_wait_spinbox.pack(side="left", padx=5)
        merge_wait_spinbox.bind("<FocusOut>", lambda e: self._auto_save_config())
        ttk.Label(row2, text="秒 (收到短消息后等待多久再处理)").pack(side="left")

        # 短消息阈值
        row3 = ttk.Frame(settings_frame)
        row3.pack(fill="x", pady=8)
        ttk.Label(row3, text="短消息阈值:").pack(side="left")
        self.merge_min_length_var = tk.StringVar(value="5")
        merge_length_spinbox = ttk.Spinbox(row3, from_=1, to=20, textvariable=self.merge_min_length_var, width=5)
        merge_length_spinbox.pack(side="left", padx=5)
        merge_length_spinbox.bind("<FocusOut>", lambda e: self._auto_save_config())
        ttk.Label(row3, text="字 (低于此长度的消息会触发合并等待)").pack(side="left")

        # 保存按钮
        row4 = ttk.Frame(settings_frame)
        row4.pack(fill="x", pady=(15, 5))
        ttk.Button(row4, text="保存设置", command=self._save_merge_config).pack(side="left")
        self.merge_save_status = tk.StringVar(value="")
        ttk.Label(row4, textvariable=self.merge_save_status, foreground="green").pack(side="left", padx=10)

        # 示例展示
        example_frame = ttk.LabelFrame(page, text="效果示例", padding=10)
        example_frame.pack(fill="both", expand=True, padx=20, pady=10)

        example_text = scrolledtext.ScrolledText(example_frame, height=12, font=("Consolas", 9), bg="#f5f5f5")
        example_text.pack(fill="both", expand=True)

        example_content = """场景：用户想问 "pro还有吗"，但分成3条发送

未开启消息合并时：
  [10:00:01] 用户发送: "pro"
  [10:00:01] AI回复: "您好，请问您是想了解Pro版本吗？"  ❌ 错误回复
  [10:00:02] 用户发送: "还有"
  [10:00:02] AI回复: "还有什么呢？请问有什么需要帮助的？"  ❌ 错误回复
  [10:00:03] 用户发送: "吗"
  [10:00:03] AI回复: "？"  ❌ 错误回复

开启消息合并后（等待3秒）：
  [10:00:01] 用户发送: "pro" → 加入合并队列，等待3秒
  [10:00:02] 用户发送: "还有" → 追加到队列，重置等待
  [10:00:03] 用户发送: "吗" → 追加到队列，重置等待
  [10:00:06] 3秒内无新消息，合并处理: "pro还有吗"
  [10:00:06] AI回复: "Pro版还有货的，需要给您发链接吗？"  ✓ 正确回复"""

        example_text.insert("1.0", example_content)
        example_text.config(state="disabled")

    # ==================== 会话管理页 ====================
    def _create_coze_sessions_page(self):
        """创建会话管理页"""
        page = ttk.Frame(self.content_frame)
        self.pages["coze_sessions"] = page

        # 标题说明
        ttk.Label(
            page,
            text="会话管理 - 查看和管理Coze服务器上的会话",
            font=("Microsoft YaHei", 12, "bold")
        ).pack(pady=15)

        # 列表区域
        list_frame = ttk.Frame(page)
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # 创建表格
        columns = ('conversation_id', 'user_id', 'buyer_name', 'item_id', 'created_at')
        self.coze_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=18)
        self.coze_tree.heading('conversation_id', text='会话ID')
        self.coze_tree.heading('user_id', text='用户ID')
        self.coze_tree.heading('buyer_name', text='用户名')
        self.coze_tree.heading('item_id', text='商品ID')
        self.coze_tree.heading('created_at', text='创建时间')

        self.coze_tree.column('conversation_id', width=180, minwidth=150)
        self.coze_tree.column('user_id', width=180, minwidth=150)
        self.coze_tree.column('buyer_name', width=100, minwidth=80)
        self.coze_tree.column('item_id', width=180, minwidth=150)
        self.coze_tree.column('created_at', width=150, minwidth=120)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.coze_tree.yview)
        self.coze_tree.configure(yscrollcommand=scrollbar.set)
        self.coze_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 状态标签
        self.coze_status_label = ttk.Label(page, text="")
        self.coze_status_label.pack(pady=5)

        # 按钮区域
        btn_frame = ttk.Frame(page)
        btn_frame.pack(pady=15)

        ttk.Button(btn_frame, text="刷新列表", command=self._refresh_coze_sessions, width=12).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="清空Coze会话", command=self._clear_coze_sessions, width=14).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="清除本地记录", command=self._clear_local_sessions, width=14).pack(side="left", padx=5)

        # 存储会话数据
        self.coze_conversations_data = []

    # ==================== 同步商品页 ====================
    def _create_sync_products_page(self):
        """创建同步商品页"""
        page = ttk.Frame(self.content_frame)
        self.pages["sync_products"] = page

        # 标题
        ttk.Label(
            page,
            text="同步商品 - 抓取闲鱼商品信息",
            font=("Microsoft YaHei", 12, "bold")
        ).pack(pady=15)

        # 输入区域
        input_frame = ttk.LabelFrame(page, text="添加商品", padding=10)
        input_frame.pack(fill="x", padx=20, pady=5)

        # 链接输入行
        link_row = ttk.Frame(input_frame)
        link_row.pack(fill="x", pady=5)
        ttk.Label(link_row, text="商品链接:").pack(side="left")
        self.product_link_var = tk.StringVar()
        link_entry = ttk.Entry(link_row, textvariable=self.product_link_var, width=60)
        link_entry.pack(side="left", padx=10, fill="x", expand=True)
        ttk.Button(link_row, text="同步商品", command=self._sync_product, width=12).pack(side="left", padx=5)

        # 同步状态
        self.sync_status_var = tk.StringVar(value="")
        ttk.Label(input_frame, textvariable=self.sync_status_var, foreground="gray").pack(anchor="w", pady=5)

        # 商品列表区域
        list_frame = ttk.LabelFrame(page, text="已同步商品", padding=10)
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # 抓取标题字符数设置
        settings_row = ttk.Frame(list_frame)
        settings_row.pack(fill="x", pady=(0, 8))
        ttk.Label(settings_row, text="抓取标题字符数:").pack(side="left")
        self.title_grab_length_var = tk.StringVar(value=str(self.title_grab_length))
        title_length_entry = ttk.Entry(settings_row, textvariable=self.title_grab_length_var, width=5)
        title_length_entry.pack(side="left", padx=5)
        ttk.Label(settings_row, text="字符（0=不限制）").pack(side="left")
        ttk.Button(settings_row, text="保存", command=self._confirm_title_length, width=6).pack(side="left", padx=10)
        self.title_length_status = tk.StringVar(value="")
        ttk.Label(settings_row, textvariable=self.title_length_status, foreground="green").pack(side="left")

        # 商品表格
        columns = ('item_id', 'title', 'price', 'updated_at', 'operation')
        self.products_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=12)
        self.products_tree.heading('item_id', text='商品ID')
        self.products_tree.heading('title', text='商品标题')
        self.products_tree.heading('price', text='价格')
        self.products_tree.heading('updated_at', text='更新时间')
        self.products_tree.heading('operation', text='操作')
        self.products_tree.column('item_id', width=140, minwidth=120, anchor='center')
        self.products_tree.column('title', width=240, minwidth=160, anchor='center')
        self.products_tree.column('price', width=70, minwidth=50, anchor='center')
        self.products_tree.column('updated_at', width=140, minwidth=110, anchor='center')
        self.products_tree.column('operation', width=100, minwidth=80, anchor='center')

        # 绑定点击事件处理操作列
        self.products_tree.bind('<ButtonRelease-1>', self._on_products_tree_click)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.products_tree.yview)
        self.products_tree.configure(yscrollcommand=scrollbar.set)
        self.products_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 按钮区域
        btn_frame = ttk.Frame(page)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="刷新列表", command=self._refresh_products_list, width=12).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="清空列表", command=self._clear_products_list, width=12).pack(side="left", padx=5)

    def _clear_products_list(self):
        """清空所有商品"""
        from db_manager import db_manager

        # 获取当前商品数量
        products = db_manager.get_all_products()
        if not products:
            messagebox.showinfo("提示", "列表已为空")
            return

        if not messagebox.askyesno("确认", f"确定要删除所有 {len(products)} 个商品吗？"):
            return

        try:
            db_manager._ensure_connection()
            with db_manager.connection.cursor() as cursor:
                cursor.execute("DELETE FROM products")
            db_manager.connection.commit()
            self._refresh_products_list()
            messagebox.showinfo("成功", "已清空所有商品")
        except Exception as e:
            messagebox.showerror("错误", f"清空失败: {e}")

    def _confirm_title_length(self):
        """确认抓取标题字符数设置并保存到配置文件"""
        try:
            val = int(self.title_grab_length_var.get())
            if val < 0:
                self.title_grab_length_var.set("15")
                self.title_length_status.set("无效值，已重置为15")
                val = 15
            else:
                self.title_length_status.set(f"已保存: {val} 字符" if val > 0 else "已保存: 不限制")

            # 保存到配置文件
            self.title_grab_length = val
            self._save_title_grab_length()
        except ValueError:
            self.title_grab_length_var.set("15")
            self.title_length_status.set("无效值，已重置为15")

    def _save_title_grab_length(self):
        """保存抓取标题字符数到配置文件"""
        try:
            # 读取现有配置
            data = {}
            if self.vars_config_path.exists():
                with open(self.vars_config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

            # 更新抓取标题字符数
            data['title_grab_length'] = self.title_grab_length

            # 保存配置
            with open(self.vars_config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存抓取标题字符数失败: {e}")

    def _extract_item_id_from_url(self, url: str) -> str:
        """从URL中提取商品ID"""
        import re
        match = re.search(r'[?&]id=(\d+)', url)
        if match:
            return match.group(1)
        return None

    def _sync_product(self):
        """同步商品信息"""
        url = self.product_link_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请输入商品链接")
            return

        # 提取商品ID
        item_id = self._extract_item_id_from_url(url)
        if not item_id:
            messagebox.showerror("错误", "无法从链接中提取商品ID，请检查链接格式")
            return

        # 在主线程中获取抓取字数设置
        try:
            title_max_len = int(self.title_grab_length_var.get())
        except (ValueError, AttributeError):
            title_max_len = 15  # 默认15字

        self.sync_status_var.set(f"正在同步商品 {item_id}...")

        def do_sync(max_len):
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=False)
                    page = browser.new_page()
                    page.goto(url, timeout=30000)
                    page.wait_for_load_state('networkidle', timeout=15000)

                    # 使用 JavaScript 提取商品信息
                    result = page.evaluate("""
                        () => {
                            let description = '';
                            let price = '';

                            // 直接定位闲鱼商品描述元素（可能有多个）
                            const descEls = document.querySelectorAll('[class*="ItemDesc--"], [class*="itemDesc"], [class*="goods-desc"]');
                            if (descEls.length > 0) {
                                const allTexts = [];
                                for (let i = 0; i < descEls.length; i++) {
                                    const txt = (descEls[i].innerText || descEls[i].textContent || '').trim();
                                    if (txt.length > 0) allTexts.push(txt);
                                }
                                // 合并所有文本，按换行分割再用空格连接
                                const combined = allTexts.join(String.fromCharCode(10));
                                const lines = combined.split(String.fromCharCode(10));
                                const cleaned = [];
                                for (let j = 0; j < lines.length; j++) {
                                    const line = lines[j].replace(/^[ ]+|[ ]+$/g, '');
                                    if (line.length > 0) cleaned.push(line);
                                }
                                description = cleaned.join(' ');
                            }

                            // 备选：从页面标题获取
                            if (!description) {
                                const title = document.title || '';
                                if (title.includes('_闲鱼')) {
                                    description = title.replace(/_闲鱼.*$/, '').trim();
                                }
                            }

                            // 查找价格：闲鱼的 ¥ 和数字是分开的兄弟元素
                            const allElements = document.querySelectorAll('*');
                            for (const el of allElements) {
                                // 找到只包含 ¥ 的叶子节点
                                if (el.children.length === 0 && el.textContent.trim() === '¥') {
                                    // 获取下一个兄弟元素的文本（应该是价格数字）
                                    let next = el.nextElementSibling;
                                    if (next && /^[\\d.]+$/.test(next.textContent.trim())) {
                                        price = next.textContent.trim();
                                        // 检查是否有小数部分在再下一个兄弟
                                        let nextNext = next.nextElementSibling;
                                        if (nextNext && /^\\.[\\d]+$/.test(nextNext.textContent.trim())) {
                                            price += nextNext.textContent.trim();
                                        }
                                        break;
                                    }
                                }
                            }

                            // 备选：用正则从整页文本匹配
                            if (!price) {
                                const bodyText = document.body.innerText;
                                const match = bodyText.match(/¥\\s*([\\d.]+)/);
                                if (match) price = match[1];
                            }

                            return { description, price };
                        }
                    """)

                    browser.close()

                    title = result.get('description', '')
                    price = result.get('price', '')

                    # 根据设置截断标题（按字符数）
                    if max_len > 0 and len(title) > max_len:
                        title = title[:max_len]

                    if title:
                        self.root.after(0, lambda t=title, p=price: self._save_product(item_id, t, p))
                    else:
                        self.root.after(0, lambda: self._on_sync_error("无法抓取商品标题，请手动输入"))

            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda msg=err_msg: self._on_sync_error(msg))

        threading.Thread(target=do_sync, args=(title_max_len,), daemon=True).start()

    def _save_product(self, item_id: str, title: str, price: str = None):
        """保存商品到数据库"""
        from db_manager import db_manager

        if not db_manager.connection:
            db_manager.connect()

        # 确保表结构是最新的（会自动添加缺失的列）
        db_manager.init_tables()

        if db_manager.add_or_update_product(item_id, title, price):
            price_str = f" ¥{price}" if price else ""
            self.sync_status_var.set(f"同步成功: {title}{price_str}")
            self.product_link_var.set("")
            self._refresh_products_list()
            self._log(f"商品同步成功: {item_id} - {title} - ¥{price}")
        else:
            self.sync_status_var.set("保存失败")

    def _on_sync_error(self, error_msg: str):
        """同步失败处理"""
        self.sync_status_var.set(f"同步失败: {error_msg}")
        # 提供手动输入选项
        item_id = self._extract_item_id_from_url(self.product_link_var.get())
        if item_id:
            if messagebox.askyesno("同步失败", f"自动抓取失败: {error_msg}\n\n是否手动输入商品标题？"):
                self._show_manual_input_dialog(item_id)

    def _show_manual_input_dialog(self, item_id: str):
        """显示手动输入对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("手动输入商品信息")
        dialog.geometry("400x180")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text=f"商品ID: {item_id}").pack(pady=10)

        row1 = ttk.Frame(dialog)
        row1.pack(fill="x", padx=20, pady=5)
        ttk.Label(row1, text="商品标题:", width=10).pack(side="left")
        title_var = tk.StringVar()
        title_entry = ttk.Entry(row1, textvariable=title_var, width=30)
        title_entry.pack(side="left", padx=10)
        title_entry.focus()

        row2 = ttk.Frame(dialog)
        row2.pack(fill="x", padx=20, pady=5)
        ttk.Label(row2, text="商品价格:", width=10).pack(side="left")
        price_var = tk.StringVar()
        price_entry = ttk.Entry(row2, textvariable=price_var, width=15)
        price_entry.pack(side="left", padx=10)
        ttk.Label(row2, text="元").pack(side="left")

        def save():
            title = title_var.get().strip()
            price = price_var.get().strip()
            if title:
                self._save_product(item_id, title, price if price else None)
                dialog.destroy()
            else:
                messagebox.showwarning("提示", "请输入商品标题")

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="保存", command=save).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side="left", padx=10)

    def _refresh_products_list(self):
        """刷新商品列表"""
        from db_manager import db_manager

        if not db_manager.connection:
            db_manager.connect()

        # 清空现有数据
        for item in self.products_tree.get_children():
            self.products_tree.delete(item)

        # 加载商品
        products = db_manager.get_all_products()
        for p in products:
            updated_at = str(p.get('updated_at', ''))[:19] if p.get('updated_at') else ''
            price = p.get('price', '')
            price_display = f"¥{price}" if price else ''
            self.products_tree.insert('', 'end', values=(
                p.get('item_id', ''),
                p.get('title', ''),
                price_display,
                updated_at,
                '编辑 | 删除'
            ))

    def _on_products_tree_click(self, event):
        """处理商品列表点击事件"""
        region = self.products_tree.identify_region(event.x, event.y)
        if region != 'cell':
            return

        column = self.products_tree.identify_column(event.x)
        # #5 是操作列（第5列）
        if column != '#5':
            return

        item_id = self.products_tree.identify_row(event.y)
        if not item_id:
            return

        item = self.products_tree.item(item_id)
        product_item_id = item['values'][0]
        product_title = item['values'][1]

        # 获取点击位置，判断是编辑还是删除
        bbox = self.products_tree.bbox(item_id, column)
        if bbox:
            cell_x = event.x - bbox[0]
            cell_width = bbox[2]
            # 左半边是编辑，右半边是删除
            if cell_x < cell_width / 2:
                self._edit_product(product_item_id)
            else:
                self._delete_product_by_id(product_item_id, product_title)

    def _edit_product(self, item_id: str):
        """编辑商品对话框"""
        from db_manager import db_manager

        if not db_manager.connection:
            db_manager.connect()

        # 确保表结构是最新的
        db_manager.init_tables()

        # 获取商品现有信息
        product = db_manager.get_product(item_id)
        if not product:
            messagebox.showerror("错误", "商品不存在")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("编辑商品信息")
        dialog.geometry("550x400")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text=f"商品ID: {item_id}", font=("Microsoft YaHei", 10)).pack(pady=10)

        # 标题输入
        row1 = ttk.Frame(dialog)
        row1.pack(fill="x", padx=20, pady=5)
        ttk.Label(row1, text="商品标题:", width=10).pack(side="left")
        title_var = tk.StringVar(value=product.get('title', ''))
        title_entry = ttk.Entry(row1, textvariable=title_var, width=50)
        title_entry.pack(side="left", padx=10)
        title_entry.focus()

        # 价格输入
        row2 = ttk.Frame(dialog)
        row2.pack(fill="x", padx=20, pady=5)
        ttk.Label(row2, text="商品价格:", width=10).pack(side="left")
        price_var = tk.StringVar(value=product.get('price', '') or '')
        price_entry = ttk.Entry(row2, textvariable=price_var, width=50)
        price_entry.pack(side="left", padx=10)
        ttk.Label(row2, text="元").pack(side="left")

        # 备注输入（多行文本框）
        row4 = ttk.Frame(dialog)
        row4.pack(fill="x", padx=20, pady=5)
        ttk.Label(row4, text="备注:", width=10).pack(side="left", anchor="n")
        notes_text = tk.Text(row4, width=50, height=8, wrap="word", font=("Microsoft YaHei", 9))
        notes_text.pack(side="left", padx=10)
        notes_text.insert("1.0", product.get('notes', '') or '')

        def save():
            title = title_var.get().strip()
            price = price_var.get().strip()
            notes = notes_text.get("1.0", "end-1c").strip()
            if title:
                if db_manager.add_or_update_product(item_id, title, price if price else None, notes if notes else None):
                    self._refresh_products_list()
                    self._log(f"编辑商品: {item_id}")
                    dialog.destroy()
                else:
                    messagebox.showerror("错误", "保存失败")
            else:
                messagebox.showwarning("提示", "请输入商品标题")

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="保存", command=save, width=10).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy, width=10).pack(side="left", padx=10)

    def _delete_product_by_id(self, item_id: str, title: str):
        """根据ID删除商品"""
        if messagebox.askyesno("确认删除", f"确定要删除商品吗？\n\nID: {item_id}\n标题: {title}"):
            from db_manager import db_manager
            if db_manager.delete_product(str(item_id)):
                self._refresh_products_list()
                self._log(f"删除商品: {item_id}")
            else:
                messagebox.showerror("错误", "删除失败")

    def _delete_selected_product(self):
        """删除选中的商品（底部按钮，已移除）"""
        pass

    # ==================== 系统设置页 ====================
    def _create_system_settings_page(self):
        """创建系统设置页"""
        page = ttk.Frame(self.content_frame)
        self.pages["system_settings"] = page

        # Coze API 配置
        api_frame = ttk.LabelFrame(page, text="配置设置", padding=15)
        api_frame.pack(fill="x", padx=20, pady=15)

        # API Token
        row1 = ttk.Frame(api_frame)
        row1.pack(fill="x", pady=5)
        ttk.Label(row1, text="Coze API Token:", width=15).pack(side="left")
        self.api_token_var = tk.StringVar()
        self.api_token_entry = ttk.Entry(row1, textvariable=self.api_token_var, width=50, show="*")
        self.api_token_entry.pack(side="left", padx=5)
        self.api_token_entry.bind("<FocusOut>", lambda e: self._auto_save_config())
        self.show_token = tk.BooleanVar(value=False)
        ttk.Checkbutton(row1, text="显示", variable=self.show_token,
                       command=self._toggle_token_visibility).pack(side="left", padx=5)

        # Bot ID
        row2 = ttk.Frame(api_frame)
        row2.pack(fill="x", pady=5)
        ttk.Label(row2, text="Coze Bot ID:", width=15).pack(side="left")
        self.bot_id_var = tk.StringVar()
        bot_id_entry = ttk.Entry(row2, textvariable=self.bot_id_var, width=50)
        bot_id_entry.pack(side="left", padx=5)
        bot_id_entry.bind("<FocusOut>", lambda e: self._auto_save_config())
        ttk.Button(row2, text="测试连接", command=self._test_coze_connection).pack(side="left", padx=20)

        # 数据库配置
        db_frame = ttk.LabelFrame(page, text="数据库配置 (对话记忆)", padding=15)
        db_frame.pack(fill="x", padx=20, pady=10)

        # 数据库地址和端口
        row3 = ttk.Frame(db_frame)
        row3.pack(fill="x", pady=5)
        ttk.Label(row3, text="数据库地址:", width=12).pack(side="left")
        self.db_host_var = tk.StringVar(value="localhost")
        db_host_entry = ttk.Entry(row3, textvariable=self.db_host_var, width=20)
        db_host_entry.pack(side="left", padx=5)
        db_host_entry.bind("<FocusOut>", lambda e: self._auto_save_config())
        ttk.Label(row3, text="端口:").pack(side="left", padx=(20, 5))
        self.db_port_var = tk.StringVar(value="3306")
        db_port_entry = ttk.Entry(row3, textvariable=self.db_port_var, width=8)
        db_port_entry.pack(side="left")
        db_port_entry.bind("<FocusOut>", lambda e: self._auto_save_config())

        # 用户名和密码
        row4 = ttk.Frame(db_frame)
        row4.pack(fill="x", pady=5)
        ttk.Label(row4, text="用户名:", width=12).pack(side="left")
        self.db_user_var = tk.StringVar(value="root")
        db_user_entry = ttk.Entry(row4, textvariable=self.db_user_var, width=15)
        db_user_entry.pack(side="left", padx=5)
        db_user_entry.bind("<FocusOut>", lambda e: self._auto_save_config())
        ttk.Label(row4, text="密码:").pack(side="left", padx=(20, 5))
        self.db_password_var = tk.StringVar(value="root")
        db_password_entry = ttk.Entry(row4, textvariable=self.db_password_var, width=15, show="*")
        db_password_entry.pack(side="left")
        db_password_entry.bind("<FocusOut>", lambda e: self._auto_save_config())

        # 数据库名和测试按钮
        row5 = ttk.Frame(db_frame)
        row5.pack(fill="x", pady=5)
        ttk.Label(row5, text="数据库名:", width=12).pack(side="left")
        self.db_name_var = tk.StringVar(value="xianyu")
        db_name_entry = ttk.Entry(row5, textvariable=self.db_name_var, width=15)
        db_name_entry.pack(side="left", padx=5)
        db_name_entry.bind("<FocusOut>", lambda e: self._auto_save_config())
        ttk.Button(row5, text="测试连接", command=self._test_db_connection).pack(side="left", padx=20)

        # 保存配置按钮
        save_frame = ttk.Frame(page)
        save_frame.pack(fill="x", padx=20, pady=15)
        ttk.Button(save_frame, text="💾 保存所有配置", command=self._save_config, width=20).pack(side="left")
        self.save_status_var = tk.StringVar(value="")
        ttk.Label(save_frame, textvariable=self.save_status_var, foreground="green").pack(side="left", padx=15)

        # Coze 工作流变量配置
        coze_vars_frame = ttk.LabelFrame(page, text="Coze 工作流变量配置", padding=15)
        coze_vars_frame.pack(fill="x", padx=20, pady=10)

        # 变量配置表头
        vars_header_frame = ttk.Frame(coze_vars_frame)
        vars_header_frame.pack(fill="x")
        ttk.Label(vars_header_frame, text="启用", width=6).pack(side="left")
        ttk.Label(vars_header_frame, text="变量名", width=15).pack(side="left", padx=5)
        ttk.Label(vars_header_frame, text="说明", width=15).pack(side="left", padx=5)

        # 变量行容器
        self.var_entries = {}
        vars_list_frame = ttk.Frame(coze_vars_frame)
        vars_list_frame.pack(fill="x", pady=5)

        var_configs = [
            ('buyer_name', '买家用户名'),
            ('order_status', '订单状态'),
            ('product_info', '商品信息'),
        ]

        for var_key, desc in var_configs:
            row_frame = ttk.Frame(vars_list_frame)
            row_frame.pack(fill="x", pady=2)

            enabled_var = tk.BooleanVar(value=self.coze_vars_config.get(var_key, {}).get('enabled', True))
            cb = ttk.Checkbutton(row_frame, variable=enabled_var, width=3)
            cb.pack(side="left")
            cb.bind("<ButtonRelease-1>", lambda e: self.root.after(100, self._auto_save_config))

            name_var = tk.StringVar(value=self.coze_vars_config.get(var_key, {}).get('name', var_key))
            name_entry = ttk.Entry(row_frame, textvariable=name_var, width=15)
            name_entry.pack(side="left", padx=5)
            name_entry.bind("<FocusOut>", lambda e: self._auto_save_config())

            ttk.Label(row_frame, text=desc, width=15).pack(side="left", padx=5)

            if var_key == 'order_status':
                ttk.Button(row_frame, text="查看映射详情", command=self._show_status_mapping_popup, width=12).pack(side="left", padx=10)

            if var_key == 'product_info':
                ttk.Button(row_frame, text="查看输出样式", command=self._show_product_info_format_popup, width=12).pack(side="left", padx=10)

            self.var_entries[var_key] = {
                'enabled': enabled_var,
                'name': name_var,
                'desc': desc
            }

    # ==================== 配置相关方法 ====================
    def _load_config(self):
        """加载配置"""
        self.api_token_var.set(os.getenv("COZE_API_TOKEN", ""))
        self.bot_id_var.set(os.getenv("COZE_BOT_ID", ""))
        self.interval_var.set(os.getenv("XIANYU_CHECK_INTERVAL", "2"))
        self.skip_duplicate_var.set(os.getenv("SKIP_DUPLICATE_MSG", "true").lower() == "true")
        self.msg_expire_var.set(os.getenv("MSG_EXPIRE_SECONDS", "60"))
        self.inactive_enabled_var.set(os.getenv("INACTIVE_ENABLED", "true").lower() == "true")
        self.inactive_timeout_var.set(os.getenv("INACTIVE_TIMEOUT_MINUTES", "3"))
        self.enter_delay_var.set(os.getenv("CONVERSATION_ENTER_DELAY", "1.5"))
        self.db_host_var.set(os.getenv("DB_HOST", "localhost"))
        self.db_port_var.set(os.getenv("DB_PORT", "3306"))
        self.db_user_var.set(os.getenv("DB_USER", "root"))
        self.db_password_var.set(os.getenv("DB_PASSWORD", "root"))
        self.db_name_var.set(os.getenv("DB_NAME", "xianyu"))
        self.memory_enabled_var.set(os.getenv("MEMORY_ENABLED", "true").lower() == "true")
        self.memory_rounds_var.set(os.getenv("MEMORY_CONTEXT_ROUNDS", "5"))
        self.merge_enabled_var.set(Config.MESSAGE_MERGE_ENABLED)
        self.merge_wait_var.set(str(Config.MESSAGE_MERGE_WAIT_SECONDS))
        self.merge_min_length_var.set(str(Config.MESSAGE_MERGE_MIN_LENGTH))

        # 加载 prompt
        if hasattr(self, 'prompt_content') and self.prompt_content:
            self.prompt_text.insert("1.0", self.prompt_content)

        # 更新 spinbox 状态
        self._on_duplicate_toggle()
        self._on_inactive_toggle()

    def _auto_save_config(self):
        """自动保存配置（无提示）"""
        try:
            if not self.env_path.exists():
                self.env_path.touch()

            set_key(str(self.env_path), "COZE_API_TOKEN", self.api_token_var.get())
            set_key(str(self.env_path), "COZE_BOT_ID", self.bot_id_var.get())
            set_key(str(self.env_path), "XIANYU_CHECK_INTERVAL", self.interval_var.get())
            set_key(str(self.env_path), "HEADLESS", "false")
            set_key(str(self.env_path), "SKIP_DUPLICATE_MSG", str(self.skip_duplicate_var.get()).lower())
            set_key(str(self.env_path), "MSG_EXPIRE_SECONDS", self.msg_expire_var.get())
            set_key(str(self.env_path), "INACTIVE_ENABLED", str(self.inactive_enabled_var.get()).lower())
            set_key(str(self.env_path), "INACTIVE_TIMEOUT_MINUTES", self.inactive_timeout_var.get())
            set_key(str(self.env_path), "CONVERSATION_ENTER_DELAY", self.enter_delay_var.get())
            set_key(str(self.env_path), "DB_HOST", self.db_host_var.get())
            set_key(str(self.env_path), "DB_PORT", self.db_port_var.get())
            set_key(str(self.env_path), "DB_USER", self.db_user_var.get())
            set_key(str(self.env_path), "DB_PASSWORD", self.db_password_var.get())
            set_key(str(self.env_path), "DB_NAME", self.db_name_var.get())
            set_key(str(self.env_path), "MEMORY_ENABLED", str(self.memory_enabled_var.get()).lower())
            set_key(str(self.env_path), "MEMORY_CONTEXT_ROUNDS", self.memory_rounds_var.get())
            set_key(str(self.env_path), "MESSAGE_MERGE_ENABLED", str(self.merge_enabled_var.get()).lower())
            set_key(str(self.env_path), "MESSAGE_MERGE_WAIT_SECONDS", self.merge_wait_var.get())
            set_key(str(self.env_path), "MESSAGE_MERGE_MIN_LENGTH", self.merge_min_length_var.get())

            self._save_coze_vars_config()
            load_dotenv(self.env_path, override=True)

            # 同步更新 Config 类属性（确保运行时生效）
            Config.MESSAGE_MERGE_ENABLED = self.merge_enabled_var.get()
            Config.MESSAGE_MERGE_WAIT_SECONDS = float(self.merge_wait_var.get())
            Config.MESSAGE_MERGE_MIN_LENGTH = int(self.merge_min_length_var.get())
        except Exception as e:
            logger.error(f"自动保存配置失败: {e}")

    def _save_config(self):
        """保存配置（带提示）"""
        try:
            self._auto_save_config()
            self.save_status_var.set("✓ 配置已保存，重启后生效")
            self._log("配置已保存")
            messagebox.showinfo("保存成功", "配置已保存！\n\n部分配置需要重启客户端后生效。")
        except Exception as e:
            self.save_status_var.set("✗ 保存失败")
            messagebox.showerror("错误", f"保存配置失败: {e}")

    def _save_merge_config(self):
        """保存多消息合并配置"""
        self._auto_save_config()
        self.merge_save_status.set("已保存")
        # 3秒后清除提示
        self.root.after(3000, lambda: self.merge_save_status.set(""))

    def _toggle_token_visibility(self):
        """切换密钥显示/隐藏"""
        if self.show_token.get():
            self.api_token_entry.config(show="")
        else:
            self.api_token_entry.config(show="*")

    def _on_duplicate_toggle(self):
        """重复消息过滤开关切换"""
        if self.skip_duplicate_var.get():
            self.msg_expire_spinbox.config(state="normal")
        else:
            self.msg_expire_spinbox.config(state="disabled")
        self._auto_save_config()

    def _on_inactive_toggle(self):
        """主动发消息开关切换"""
        if self.inactive_enabled_var.get():
            self.inactive_timeout_spinbox.config(state="normal")
        else:
            self.inactive_timeout_spinbox.config(state="disabled")
        self._auto_save_config()

    def _test_db_connection(self):
        """测试数据库连接"""
        try:
            import pymysql
            conn = pymysql.connect(
                host=self.db_host_var.get(),
                port=int(self.db_port_var.get()),
                user=self.db_user_var.get(),
                password=self.db_password_var.get(),
                database=self.db_name_var.get(),
                charset='utf8mb4'
            )
            conn.close()
            messagebox.showinfo("成功", "数据库连接成功！")
            self._log("数据库连接测试成功")
        except Exception as e:
            messagebox.showerror("错误", f"数据库连接失败: {e}")
            self._log(f"数据库连接失败: {e}")

    def _test_coze_connection(self):
        """测试Coze API连接"""
        api_token = self.api_token_var.get().strip()
        bot_id = self.bot_id_var.get().strip()

        if not api_token:
            messagebox.showerror("错误", "请先填写 Coze API Token")
            return
        if not bot_id:
            messagebox.showerror("错误", "请先填写 Coze Bot ID")
            return

        # 检查 token 格式
        if api_token.startswith('/') or ':/' in api_token or api_token.endswith('.bat'):
            messagebox.showerror("错误", "API Token 格式错误！\n\n看起来你填的是文件路径，请填写正确的 Coze API Token。\n\n正确格式示例：pat_xxxxxxxxxxxxxxxx")
            return

        try:
            import httpx
            headers = {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json"
            }
            # 使用 Coze API 获取 bot 信息来测试连接
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    f"https://api.coze.cn/v1/bot/get_online_info?bot_id={bot_id}",
                    headers=headers
                )
                result = response.json()

                if result.get("code") == 0:
                    bot_name = result.get("data", {}).get("name", "未知")
                    messagebox.showinfo("成功", f"Coze API 连接成功！\n\nBot 名称: {bot_name}")
                    self._log(f"Coze API 连接测试成功，Bot: {bot_name}")
                else:
                    error_msg = result.get("msg", "未知错误")
                    messagebox.showerror("错误", f"Coze API 连接失败:\n{error_msg}")
                    self._log(f"Coze API 连接失败: {error_msg}")
        except Exception as e:
            messagebox.showerror("错误", f"Coze API 连接失败:\n{e}")
            self._log(f"Coze API 连接失败: {e}")

    def _load_coze_vars_config(self):
        """加载Coze变量配置"""
        try:
            if self.vars_config_path.exists():
                with open(self.vars_config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.coze_vars_config = data.get('vars', DEFAULT_COZE_VARS.copy())
                    self.status_mapping = data.get('status_mapping', DEFAULT_STATUS_MAPPING.copy())
                    self.prompt_content = data.get('prompt', '')
                    self.title_grab_length = data.get('title_grab_length', 15)
            else:
                self.coze_vars_config = DEFAULT_COZE_VARS.copy()
                self.status_mapping = DEFAULT_STATUS_MAPPING.copy()
                self.prompt_content = ''
                self.title_grab_length = 15
        except Exception as e:
            logger.error(f"加载Coze变量配置失败: {e}")
            self.coze_vars_config = DEFAULT_COZE_VARS.copy()
            self.status_mapping = DEFAULT_STATUS_MAPPING.copy()
            self.prompt_content = ''
            self.title_grab_length = 15

    def _save_coze_vars_config(self):
        """保存Coze变量配置"""
        try:
            for var_key, entry_data in self.var_entries.items():
                self.coze_vars_config[var_key] = {
                    'name': entry_data['name'].get(),
                    'desc': entry_data['desc'],
                    'enabled': entry_data['enabled'].get()
                }

            prompt_content = self.prompt_text.get("1.0", "end-1c").strip()

            data = {
                'vars': self.coze_vars_config,
                'status_mapping': self.status_mapping,
                'prompt': prompt_content,
                'title_grab_length': self.title_grab_length
            }
            with open(self.vars_config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            logger.error(f"保存Coze变量配置失败: {e}")
            return False

    # ==================== Coze会话操作 ====================
    def _refresh_coze_sessions(self):
        """刷新Coze会话列表"""
        from db_manager import db_manager
        from coze_client import CozeClient
        from datetime import datetime

        self.coze_status_label.config(text="正在从Coze获取会话列表...")

        def do_refresh():
            try:
                coze_client = CozeClient()
                result = coze_client.list_conversations_sync(page_num=1, page_size=50)
                self.root.after(0, lambda: on_refresh_complete(result))
            except Exception as e:
                self.root.after(0, lambda: on_refresh_error(e))

        def on_refresh_complete(result):
            for item in self.coze_tree.get_children():
                self.coze_tree.delete(item)

            session_map = {}
            try:
                sessions = db_manager.get_all_sessions_with_status()
                for s in sessions:
                    conv_id = s.get('conversation_id')
                    if conv_id:
                        session_map[conv_id] = s
            except:
                pass

            self.coze_conversations_data = result.get('conversations', [])
            for conv in self.coze_conversations_data:
                conv_id = conv.get('id', '')
                created_at = conv.get('created_at', 0)

                session = session_map.get(conv_id, {})
                user_id = session.get('user_id', '')
                buyer_name = session.get('buyer_name', '')
                item_id = session.get('item_id', '')

                created_at_str = ''
                if created_at:
                    try:
                        created_at_str = datetime.fromtimestamp(int(created_at)).strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        created_at_str = str(created_at)

                self.coze_tree.insert('', 'end', values=(conv_id, user_id, buyer_name, item_id, created_at_str))

            has_more = result.get('has_more', False)
            status_text = f"共 {len(self.coze_conversations_data)} 个会话"
            if has_more:
                status_text += " (还有更多)"
            self.coze_status_label.config(text=status_text)

        def on_refresh_error(e):
            self.coze_status_label.config(text=f"获取失败: {e}")

        threading.Thread(target=do_refresh, daemon=True).start()

    def _clear_coze_sessions(self):
        """清空Coze会话"""
        from db_manager import db_manager
        from coze_client import CozeClient

        if not self.coze_conversations_data:
            messagebox.showinfo("提示", "没有需要清空的会话")
            return

        if not messagebox.askyesno("确认", f"确定要删除Coze服务器上的所有 {len(self.coze_conversations_data)} 个会话吗？"):
            return

        self.coze_status_label.config(text="正在删除会话...")

        def do_clear():
            coze_client = CozeClient()
            success_count = 0
            fail_count = 0

            for conv in self.coze_conversations_data:
                conv_id = conv.get('id')
                if conv_id:
                    try:
                        if coze_client.delete_conversation_sync(conv_id):
                            success_count += 1
                        else:
                            fail_count += 1
                    except:
                        fail_count += 1

            db_manager.clear_all_conversation_ids()

            def update_ui():
                self.coze_status_label.config(text=f"清空完成: 成功{success_count}个, 失败{fail_count}个")
                self._refresh_coze_sessions()
                messagebox.showinfo("完成", f"Coze会话清空完成\n\n成功: {success_count}\n失败: {fail_count}")
                self._log(f"已清空 {success_count} 个Coze会话")

            self.root.after(0, update_ui)

        threading.Thread(target=do_clear, daemon=True).start()

    def _clear_local_sessions(self):
        """清除本地会话记录"""
        from db_manager import db_manager

        if not messagebox.askyesno("确认", "确定要清除所有本地会话记录吗？\n\n这将清空 user_sessions 表"):
            return
        if db_manager.clear_user_sessions():
            messagebox.showinfo("成功", "本地会话记录已清除")
            self._log("已清除本地会话记录")
        else:
            messagebox.showerror("错误", "清除失败")

    def _clear_all_sessions(self):
        """清空所有会话（Coze + 本地）"""
        from db_manager import db_manager
        from coze_client import CozeClient

        if not messagebox.askyesno("确认", "确定要清空所有会话吗？\n\n这将同时清空：\n- Coze服务器上的会话\n- 本地数据库记录"):
            return

        self._log("正在清空所有会话...")

        def do_clear():
            coze_success = 0
            coze_fail = 0

            # 1. 清空Coze会话
            try:
                coze_client = CozeClient()
                result = coze_client.list_conversations_sync(page_num=1, page_size=50)
                conversations = result.get('conversations', [])

                for conv in conversations:
                    conv_id = conv.get('id')
                    if conv_id:
                        try:
                            if coze_client.delete_conversation_sync(conv_id):
                                coze_success += 1
                            else:
                                coze_fail += 1
                        except:
                            coze_fail += 1
            except Exception as e:
                self.root.after(0, lambda: self._log(f"获取Coze会话列表失败: {e}"))

            # 2. 清空本地数据库
            if not db_manager.connection:
                db_manager.connect()
            db_result = db_manager.clear_all_tables()

            # 更新UI
            def update_ui():
                if db_result:
                    msg = f"清空完成！\n\nCoze会话：成功{coze_success}个"
                    if coze_fail > 0:
                        msg += f"，失败{coze_fail}个"
                    msg += "\n本地数据库：已清空"
                    messagebox.showinfo("成功", msg)
                    self._log(f"已清空所有会话 - Coze: {coze_success}个, 本地数据库: 已清空")
                else:
                    messagebox.showerror("错误", "清空本地数据库失败")

            self.root.after(0, update_ui)

        threading.Thread(target=do_clear, daemon=True).start()

    # ==================== 订单状态映射弹窗 ====================
    def _show_status_mapping_popup(self):
        """显示订单状态映射浮层"""
        popup = tk.Toplevel(self.root)
        popup.title("订单状态映射详情")
        popup.geometry("650x450")
        popup.transient(self.root)
        popup.grab_set()

        ttk.Label(
            popup,
            text="闲鱼原始状态 → 传给Coze的值 | 系统消息",
            font=("Microsoft YaHei", 10, "bold")
        ).pack(pady=10)

        table_frame = ttk.Frame(popup)
        table_frame.pack(fill="both", expand=True, padx=15, pady=5)

        columns = ('original', 'mapped', 'system_msg')
        tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=12)
        tree.heading('original', text='闲鱼原始状态')
        tree.heading('mapped', text='传给Coze的值')
        tree.heading('system_msg', text='系统消息内容')
        tree.column('original', width=150)
        tree.column('mapped', width=100)
        tree.column('system_msg', width=200)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for orig, value in self.status_mapping.items():
            mapped, system_msg = _extract_status_mapping_values(value)
            tree.insert('', 'end', values=(orig, mapped, system_msg))

        btn_frame = ttk.Frame(popup)
        btn_frame.pack(fill="x", padx=15, pady=15)

        ttk.Button(
            btn_frame,
            text="编辑映射",
            command=lambda: [popup.destroy(), self._open_status_mapping_dialog()]
        ).pack(side="left", padx=5)

        ttk.Button(
            btn_frame,
            text="重置默认",
            command=lambda: self._reset_status_mapping_in_popup(tree)
        ).pack(side="left", padx=5)

        ttk.Button(btn_frame, text="关闭", command=popup.destroy).pack(side="right", padx=5)

    # ==================== 商品信息输出样式弹窗 ====================
    def _show_product_info_format_popup(self):
        """显示商品信息输出样式弹窗"""
        popup = tk.Toplevel(self.root)
        popup.title("商品信息输出样式")
        popup.geometry("550x380")
        popup.transient(self.root)
        popup.grab_set()

        ttk.Label(
            popup,
            text="传递给 Coze 工作流的商品信息格式",
            font=("Microsoft YaHei", 11, "bold")
        ).pack(pady=10)

        # 说明文字
        desc_text = "当用户咨询某个商品时，系统会自动从数据库获取该商品的备注信息，\n并以下列格式传递给 Coze 工作流的 product_info 变量："
        ttk.Label(popup, text=desc_text, justify="left", wraplength=500).pack(padx=20, pady=5, anchor="w")

        # 示例展示
        example_frame = ttk.LabelFrame(popup, text="输出样式示例", padding=10)
        example_frame.pack(fill="both", expand=True, padx=20, pady=10)

        example_text = scrolledtext.ScrolledText(example_frame, height=10, font=("Consolas", 10), bg="#f5f5f5")
        example_text.pack(fill="both", expand=True)

        example_content = """[当前会话-商品信息]
标题：小米10 PRO 内存12+512
价格：2999
备注：成色99新，国行正品，支持验机
电池健康度92%，屏幕无划痕
原装配件齐全，送钢化膜+保护壳
可当面交易，支持同城闪送"""

        example_text.insert("1.0", example_content)
        example_text.config(state="disabled")

        # 提示
        tip_text = "提示：在 Coze 工作流中使用 {{product_info}} 引用此变量"
        ttk.Label(popup, text=tip_text, foreground="gray").pack(pady=5)

        ttk.Button(popup, text="关闭", command=popup.destroy, width=10).pack(pady=10)

    def _reset_status_mapping_in_popup(self, tree):
        """重置映射"""
        if messagebox.askyesno("确认", "确定要重置为默认映射吗？"):
            self.status_mapping = DEFAULT_STATUS_MAPPING.copy()
            self._populate_status_mapping_tree(tree, self.status_mapping)
            self._log("订单状态映射已重置为默认值")

    def _populate_status_mapping_tree(self, tree, mapping):
        """填充状态映射表格"""
        for item in tree.get_children():
            tree.delete(item)
        for orig, value in mapping.items():
            mapped, system_msg = _extract_status_mapping_values(value)
            tree.insert('', 'end', values=(orig, mapped, system_msg))

    def _open_status_mapping_dialog(self):
        """打开订单状态映射编辑对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("订单状态映射配置")
        dialog.geometry("700x550")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(
            dialog,
            text="配置闲鱼原始状态、传给Coze的简化状态、以及系统消息内容的映射关系",
            font=("Microsoft YaHei", 9)
        ).pack(pady=10)

        table_frame = ttk.Frame(dialog)
        table_frame.pack(fill="both", expand=True, padx=10, pady=5)

        columns = ('original', 'mapped', 'system_msg')
        tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=12)
        tree.heading('original', text='闲鱼原始状态')
        tree.heading('mapped', text='传给Coze的值')
        tree.heading('system_msg', text='系统消息内容')
        tree.column('original', width=150)
        tree.column('mapped', width=100)
        tree.column('system_msg', width=200)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)

        self._populate_status_mapping_tree(tree, self.status_mapping)

        edit_frame = ttk.LabelFrame(dialog, text="编辑映射", padding=10)
        edit_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(edit_frame, text="原始状态:").grid(row=0, column=0, sticky="w", pady=3)
        orig_var = tk.StringVar()
        orig_entry = ttk.Entry(edit_frame, textvariable=orig_var, width=20)
        orig_entry.grid(row=0, column=1, pady=3, padx=5)

        ttk.Label(edit_frame, text="映射值:").grid(row=0, column=2, sticky="w", pady=3)
        mapped_var = tk.StringVar()
        mapped_entry = ttk.Entry(edit_frame, textvariable=mapped_var, width=15)
        mapped_entry.grid(row=0, column=3, pady=3, padx=5)

        ttk.Label(edit_frame, text="系统消息:").grid(row=1, column=0, sticky="w", pady=3)
        system_msg_var = tk.StringVar()
        system_msg_entry = ttk.Entry(edit_frame, textvariable=system_msg_var, width=45)
        system_msg_entry.grid(row=1, column=1, columnspan=3, pady=3, padx=5, sticky="w")

        def on_tree_select(event):
            selection = tree.selection()
            if selection:
                item = tree.item(selection[0])
                values = item['values']
                orig_var.set(values[0] if len(values) > 0 else '')
                mapped_var.set(values[1] if len(values) > 1 else '')
                system_msg_var.set(values[2] if len(values) > 2 else '')

        tree.bind('<<TreeviewSelect>>', on_tree_select)

        def add_mapping():
            orig = orig_var.get().strip()
            mapped = mapped_var.get().strip()
            system_msg = system_msg_var.get().strip()
            if orig and mapped:
                for item in tree.get_children():
                    if tree.item(item)['values'][0] == orig:
                        tree.item(item, values=(orig, mapped, system_msg))
                        return
                tree.insert('', 'end', values=(orig, mapped, system_msg))
                orig_var.set('')
                mapped_var.set('')
                system_msg_var.set('')

        def delete_mapping():
            selection = tree.selection()
            if selection:
                tree.delete(selection[0])

        def reset_default():
            if messagebox.askyesno("确认", "确定要重置为默认映射吗？"):
                self._populate_status_mapping_tree(tree, DEFAULT_STATUS_MAPPING)

        btn_frame = ttk.Frame(edit_frame)
        btn_frame.grid(row=2, column=0, columnspan=4, pady=10)

        ttk.Button(btn_frame, text="添加/更新", command=add_mapping).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="删除选中", command=delete_mapping).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="重置默认", command=reset_default).pack(side="left", padx=5)

        def save_and_close():
            self.status_mapping = {}
            for item in tree.get_children():
                values = tree.item(item)['values']
                orig = values[0]
                mapped = values[1] if len(values) > 1 else ''
                system_msg = values[2] if len(values) > 2 else ''
                self.status_mapping[orig] = {
                    'mapped': mapped,
                    'system_msg': system_msg
                }
            self._auto_save_config()
            dialog.destroy()
            self._log(f"订单状态映射已更新，共 {len(self.status_mapping)} 个映射")

        bottom_frame = ttk.Frame(dialog)
        bottom_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(bottom_frame, text="保存", command=save_and_close).pack(side="right", padx=5)
        ttk.Button(bottom_frame, text="取消", command=dialog.destroy).pack(side="right", padx=5)

    # ==================== 日志相关 ====================
    def _setup_logging(self):
        """设置日志重定向"""
        class GUILogHandler:
            def __init__(self, text_widget, gui):
                self.text_widget = text_widget
                self.gui = gui

            def write(self, message):
                if message.strip():
                    self.gui.root.after(0, self._append_log, message)

            def _append_log(self, message):
                self.text_widget.config(state="normal")
                parts = message.split(" | ", 2)
                if len(parts) >= 2:
                    time_str = parts[0]
                    level = parts[1].strip()
                    content = parts[2] if len(parts) > 2 else ""
                    start_idx = self.text_widget.index("end-1c")
                    self.text_widget.insert("end", f"{time_str} | ")
                    self.text_widget.tag_add("TIME", start_idx, "end-1c")
                    start_idx = self.text_widget.index("end-1c")
                    self.text_widget.insert("end", f"{level} | ")
                    self.text_widget.tag_add(level, start_idx, "end-1c")
                    start_idx = self.text_widget.index("end-1c")
                    self.text_widget.insert("end", f"{content}\n")
                    self.text_widget.tag_add(level, start_idx, "end-1c")
                else:
                    self.text_widget.insert("end", message + "\n")
                self.text_widget.see("end")
                self.text_widget.config(state="disabled")

            def flush(self):
                pass

        self.gui_handler = GUILogHandler(self.log_text, self)
        self.log_handler_id = logger.add(
            self.gui_handler.write,
            format="{time:HH:mm:ss} | {level} | {message}",
            level="INFO"
        )

    def _toggle_debug_logs(self):
        """切换详细日志"""
        self.show_debug_logs = self.debug_log_var.get()

        if self.log_handler_id is not None:
            try:
                logger.remove(self.log_handler_id)
            except ValueError:
                pass

        level = "DEBUG" if self.show_debug_logs else "INFO"
        self.log_handler_id = logger.add(
            self.gui_handler.write,
            format="{time:HH:mm:ss} | {level} | {message}",
            level=level
        )

        if self.show_debug_logs:
            self._log("已开启详细日志模式")
        else:
            self._log("已关闭详细日志模式")

    def _register_conversation_callback(self):
        """注册对话记录回调"""
        def on_conversation(msg_type, username, content, conv_id, order_status, level, timestamp=None):
            self.root.after(0, lambda: self.add_conversation_record(
                msg_type, username, content, conv_id, order_status, level, timestamp
            ))

        set_gui_conversation_callback(on_conversation)

    def _log(self, message, level="INFO"):
        """添加系统日志"""
        self.log_text.config(state="normal")
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_line = f"{timestamp} | {message}\n"
        self.log_text.insert("1.0", log_line)
        time_end = f"1.{len(timestamp) + 3}"
        self.log_text.tag_add("TIME", "1.0", time_end)
        msg_end = f"1.{len(log_line) - 1}"
        self.log_text.tag_add(level, time_end, msg_end)
        self.log_text.see("1.0")
        self.log_text.config(state="disabled")

    def add_conversation_record(self, msg_type: str, username: str, content: str,
                                  conv_id: str = "", order_status: str = "", level: str = "INFO",
                                  timestamp: str = None):
        """添加对话记录"""
        import datetime
        if timestamp is None:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        display_content = content.replace("\n", " ")
        if not ("http" in content and "alicdn" in content):
            if len(display_content) > 100:
                display_content = display_content[:100] + "..."

        display_conv_id = conv_id if conv_id else ""
        if len(display_conv_id) > 20:
            display_conv_id = display_conv_id[:8] + "..." + display_conv_id[-8:]

        tag = self._get_conversation_tag(msg_type, level)

        self.conv_tree.insert('', 0,
                              values=(timestamp, level, msg_type, username, display_content, display_conv_id, order_status),
                              tags=(tag,))
        children = self.conv_tree.get_children()
        if children:
            self.conv_tree.see(children[0])

    def _get_conversation_tag(self, msg_type: str, level: str) -> str:
        """根据消息类型和级别获取对应的显示标签"""
        msg_type_lower = msg_type.lower()
        if msg_type_lower == "user":
            return 'user'
        if msg_type_lower == "ai":
            return 'ai'

        level_upper = level.upper()
        if level_upper == "ERROR":
            return 'error'
        if level_upper == "WARNING":
            return 'warning'
        return 'info'

    def _clear_log(self):
        """清空日志"""
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, "end")
        self.log_text.config(state="disabled")

        for item in self.conv_tree.get_children():
            self.conv_tree.delete(item)

    # ==================== 控制台窗口控制 ====================
    def _init_console_control(self):
        """初始化控制台窗口控制（Windows平台）"""
        self.console_hwnd = None
        self.console_allocated = False  # 标记是否是动态创建的控制台

        if sys.platform == 'win32':
            try:
                self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
                self.user32 = ctypes.WinDLL('user32', use_last_error=True)
                self.console_hwnd = self.kernel32.GetConsoleWindow()
                if self.console_hwnd:
                    # 有现有控制台，默认隐藏
                    self.user32.ShowWindow(self.console_hwnd, 0)  # SW_HIDE = 0
                    self.console_visible = False
                else:
                    # 没有控制台（pythonw启动），标记为未显示
                    self.console_visible = False
            except Exception:
                pass

    def _set_console_font(self, font_name: str, font_size: int = 16):
        """设置控制台字体"""
        try:
            # 定义 CONSOLE_FONT_INFOEX 结构体
            class COORD(ctypes.Structure):
                _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

            class CONSOLE_FONT_INFOEX(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_ulong),
                    ("nFont", ctypes.c_ulong),
                    ("dwFontSize", COORD),
                    ("FontFamily", ctypes.c_uint),
                    ("FontWeight", ctypes.c_uint),
                    ("FaceName", ctypes.c_wchar * 32)
                ]

            # 获取标准输出句柄
            STD_OUTPUT_HANDLE = -11
            handle = self.kernel32.GetStdHandle(STD_OUTPUT_HANDLE)

            # 设置字体信息
            font_info = CONSOLE_FONT_INFOEX()
            font_info.cbSize = ctypes.sizeof(CONSOLE_FONT_INFOEX)
            font_info.nFont = 0
            font_info.dwFontSize.X = 0
            font_info.dwFontSize.Y = font_size
            font_info.FontFamily = 54  # FF_MODERN | FIXED_PITCH
            font_info.FontWeight = 400  # FW_NORMAL
            font_info.FaceName = font_name

            # 调用 SetCurrentConsoleFontEx
            self.kernel32.SetCurrentConsoleFontEx(handle, False, ctypes.byref(font_info))
        except Exception as e:
            logger.debug(f"设置控制台字体失败: {e}")

    def _toggle_console(self):
        """切换控制台窗口显示/隐藏"""
        if sys.platform != 'win32':
            messagebox.showinfo("提示", "控制台窗口控制仅支持 Windows 平台")
            return

        try:
            # 如果没有控制台窗口，动态创建一个
            if not self.console_hwnd:
                # 创建新控制台
                self.kernel32.AllocConsole()
                self.console_hwnd = self.kernel32.GetConsoleWindow()
                self.console_allocated = True

                # 重定向标准输出到新控制台
                sys.stdout = open('CONOUT$', 'w', encoding='utf-8')
                sys.stderr = open('CONOUT$', 'w', encoding='utf-8')

                # 重新绑定 loguru 的控制台输出
                rebind_console_output()

                # 设置控制台标题
                self.kernel32.SetConsoleTitleW("闲鱼RPA - 控制台日志")

                # 设置控制台字体（使用等宽字体避免错位）
                self._set_console_font("Consolas", 22)

                self.console_visible = True
                self.console_btn.config(text="隐藏控制台")
                return

            if self.console_visible:
                # 隐藏控制台
                self.user32.ShowWindow(self.console_hwnd, 0)  # SW_HIDE = 0
                self.console_visible = False
                self.console_btn.config(text="显示控制台")
            else:
                # 显示控制台
                self.user32.ShowWindow(self.console_hwnd, 5)  # SW_SHOW = 5
                self.console_visible = True
                self.console_btn.config(text="隐藏控制台")
        except Exception as e:
            messagebox.showerror("错误", f"控制台窗口操作失败: {e}")

    # ==================== 启动/停止 ====================
    def _toggle_running(self):
        """切换运行状态"""
        if self.is_running:
            self._stop()
        else:
            self._start()

    def _validate_required_config(self) -> bool:
        """验证必要配置是否已填写"""
        validations = [
            (self.api_token_var.get(), "请先填写 API Token"),
            (self.bot_id_var.get(), "请先填写 Bot ID"),
        ]
        for value, message in validations:
            if not value:
                messagebox.showwarning("警告", message)
                self._show_page("system_settings")
                return False
        return True

    def _start(self):
        """启动程序"""
        if not self._validate_required_config():
            return

        self._auto_save_config()

        self.is_running = True
        self.start_btn.config(text="停止")
        self.status_var.set("运行中...")
        self.status_label.config(fg="green")

        self._log("正在启动...")

        self.thread = threading.Thread(target=self._run_handler, daemon=True)
        self.thread.start()

    def _run_handler(self):
        """运行消息处理器"""
        try:
            load_dotenv(self.env_path, override=True)

            from message_handler import MessageHandler

            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            self.handler = MessageHandler()
            self.loop.run_until_complete(self.handler.start())

        except Exception as e:
            self._log(f"运行出错: {e}")
            self.root.after(0, self._on_stopped)

    def _stop(self):
        """停止程序"""
        self._log("正在停止...")

        if self.handler:
            self.handler.running = False

        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

        self._on_stopped()

    def _on_stopped(self):
        """停止后处理"""
        self.is_running = False
        self.start_btn.config(text="启动")
        self.status_var.set("已停止")
        self.status_label.config(fg="gray")
        self._log("已停止")

    def run(self):
        """运行GUI"""
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.root.mainloop()

    def _on_closing(self):
        """关闭窗口"""
        if self.is_running:
            if messagebox.askokcancel("确认", "程序正在运行，确定要退出吗？"):
                self._stop()
                self.root.destroy()
        else:
            self.root.destroy()


if __name__ == "__main__":
    app = XianyuGUI()
    app.run()
