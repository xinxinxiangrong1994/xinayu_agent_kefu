"""闲鱼智能客服 - 可视化界面"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import asyncio
import sys
import os
import json
from pathlib import Path

# 确保能找到其他模块
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv, set_key
from loguru import logger
from logger_setup import set_gui_conversation_callback


# 默认订单状态映射（包含系统消息）
DEFAULT_STATUS_MAPPING = {
    '交易成功': {'mapped': '已完成', 'system_msg': '交易成功'},
    '去评价': {'mapped': '已完成', 'system_msg': ''},  # 交易完成后显示"去评价"
    '交易关闭': {'mapped': '已关闭', 'system_msg': '交易关闭'},
    '交易取消': {'mapped': '已取消', 'system_msg': '订单已取消'},
    '等待买家收货': {'mapped': '已发货', 'system_msg': '已发货，等待买家确认'},
    '等待卖家发货': {'mapped': '已付款', 'system_msg': '我已付款，等待你发货'},
    '等待买家付款': {'mapped': '待付款', 'system_msg': '我已拍下，待付款'},
    '待付款': {'mapped': '待付款', 'system_msg': ''},
    '已付款': {'mapped': '已付款', 'system_msg': ''},
    '已发货': {'mapped': '已发货', 'system_msg': '你已发货'},
    '已收货': {'mapped': '已收货', 'system_msg': '买家已确认收货'},
    '等待见面交易': {'mapped': '已付款', 'system_msg': ''},
    '退款中': {'mapped': '退款中', 'system_msg': '申请退款'},
    '已退款': {'mapped': '已退款', 'system_msg': '退款成功'},
}

# 默认Coze变量配置
DEFAULT_COZE_VARS = {
    'buyer_name': {'name': 'buyer_name', 'desc': '买家用户名', 'enabled': True},
    'product_title': {'name': 'product_title', 'desc': '商品标题', 'enabled': True},
    'product_price': {'name': 'product_price', 'desc': '商品价格', 'enabled': True},
    'order_status': {'name': 'order_status', 'desc': '订单状态', 'enabled': True},
}


class XianyuGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("闲鱼智能客服 RPA")
        self.root.geometry("1200x1300")
        self.root.minsize(900, 800)  # 设置最小尺寸
        self.root.resizable(True, True)  # 允许拉伸窗口

        # 状态变量
        self.is_running = False
        self.handler = None
        self.loop = None
        self.thread = None
        self.show_debug_logs = False  # 是否显示详细日志
        self.log_handler_id = None  # loguru handler ID

        # Coze变量配置
        self.coze_vars_config = {}
        self.status_mapping = {}
        self.prompt_content = ''
        self.vars_config_path = Path(__file__).parent / "coze_vars_config.json"

        # 加载当前配置
        self.env_path = Path(__file__).parent / ".env"
        load_dotenv(self.env_path)

        self._load_coze_vars_config()
        self._create_widgets()
        self._load_config()

        # 重定向日志到界面
        self._setup_logging()

        # 注册对话记录回调
        self._register_conversation_callback()

    def _create_widgets(self):
        """创建界面组件"""
        # 标题
        title_label = tk.Label(
            self.root,
            text="闲鱼智能客服 RPA",
            font=("Microsoft YaHei", 18, "bold")
        )
        title_label.pack(pady=15)

        # 配置区域
        config_frame = ttk.LabelFrame(self.root, text="配置设置", padding=10)
        config_frame.pack(fill="x", padx=20, pady=10)

        # API Token
        ttk.Label(config_frame, text="Coze API Token:").grid(row=0, column=0, sticky="w", pady=5)
        self.api_token_var = tk.StringVar()
        self.api_token_entry = ttk.Entry(config_frame, textvariable=self.api_token_var, width=45, show="*")
        self.api_token_entry.grid(row=0, column=1, pady=5, padx=5)

        # 显示/隐藏密钥按钮
        self.show_token = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            config_frame,
            text="显示",
            variable=self.show_token,
            command=self._toggle_token_visibility
        ).grid(row=0, column=2)

        # Bot ID
        ttk.Label(config_frame, text="Coze Bot ID:").grid(row=1, column=0, sticky="w", pady=5)
        self.bot_id_var = tk.StringVar()
        ttk.Entry(config_frame, textvariable=self.bot_id_var, width=45).grid(row=1, column=1, pady=5, padx=5)

        # 检查间隔
        ttk.Label(config_frame, text="检查间隔 (秒):").grid(row=2, column=0, sticky="w", pady=5)
        self.interval_var = tk.StringVar(value="2")
        interval_spinbox = ttk.Spinbox(
            config_frame,
            from_=1,
            to=60,
            textvariable=self.interval_var,
            width=10
        )
        interval_spinbox.grid(row=2, column=1, sticky="w", pady=5, padx=5)

        # 重复消息过滤设置
        ttk.Label(config_frame, text="重复消息过滤:").grid(row=3, column=0, sticky="w", pady=5)
        dup_frame = ttk.Frame(config_frame)
        dup_frame.grid(row=3, column=1, sticky="w", pady=5, padx=5)

        self.skip_duplicate_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            dup_frame,
            text="启用",
            variable=self.skip_duplicate_var,
            command=self._toggle_duplicate_filter
        ).pack(side="left")

        ttk.Label(dup_frame, text="  过期时间:").pack(side="left")
        self.msg_expire_var = tk.StringVar(value="60")
        self.msg_expire_spinbox = ttk.Spinbox(
            dup_frame,
            from_=0,
            to=300,
            textvariable=self.msg_expire_var,
            width=5
        )
        self.msg_expire_spinbox.pack(side="left", padx=2)
        ttk.Label(dup_frame, text="秒").pack(side="left")

        # Inactive 主动发消息设置
        ttk.Label(config_frame, text="主动发消息:").grid(row=4, column=0, sticky="w", pady=5)
        inactive_frame = ttk.Frame(config_frame)
        inactive_frame.grid(row=4, column=1, sticky="w", pady=5, padx=5)

        self.inactive_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            inactive_frame,
            text="启用",
            variable=self.inactive_enabled_var,
            command=self._toggle_inactive_settings
        ).pack(side="left")

        ttk.Label(inactive_frame, text="  超时:").pack(side="left")
        self.inactive_timeout_var = tk.StringVar(value="3")
        self.inactive_timeout_spinbox = ttk.Spinbox(
            inactive_frame,
            from_=1,
            to=30,
            textvariable=self.inactive_timeout_var,
            width=4
        )
        self.inactive_timeout_spinbox.pack(side="left", padx=2)
        ttk.Label(inactive_frame, text="分钟").pack(side="left")

        # 会话切换延迟设置
        ttk.Label(config_frame, text="会话切入延迟:").grid(row=5, column=0, sticky="w", pady=5)
        switch_delay_frame = ttk.Frame(config_frame)
        switch_delay_frame.grid(row=5, column=1, sticky="w", pady=5, padx=5)

        self.enter_delay_var = tk.StringVar(value="1.5")
        ttk.Spinbox(
            switch_delay_frame,
            from_=0.5,
            to=5.0,
            increment=0.5,
            textvariable=self.enter_delay_var,
            width=4
        ).pack(side="left", padx=2)
        ttk.Label(switch_delay_frame, text="秒 (进入会话后等待页面加载)").pack(side="left")

        # 数据库配置区域
        db_frame = ttk.LabelFrame(self.root, text="数据库配置 (对话记忆)", padding=10)
        db_frame.pack(fill="x", padx=20, pady=10)

        # 数据库地址
        ttk.Label(db_frame, text="数据库地址:").grid(row=0, column=0, sticky="w", pady=3)
        self.db_host_var = tk.StringVar(value="localhost")
        ttk.Entry(db_frame, textvariable=self.db_host_var, width=20).grid(row=0, column=1, pady=3, padx=5, sticky="w")

        # 端口
        ttk.Label(db_frame, text="端口:").grid(row=0, column=2, sticky="w", pady=3)
        self.db_port_var = tk.StringVar(value="3306")
        ttk.Entry(db_frame, textvariable=self.db_port_var, width=8).grid(row=0, column=3, pady=3, padx=5, sticky="w")

        # 用户名
        ttk.Label(db_frame, text="用户名:").grid(row=1, column=0, sticky="w", pady=3)
        self.db_user_var = tk.StringVar(value="root")
        ttk.Entry(db_frame, textvariable=self.db_user_var, width=20).grid(row=1, column=1, pady=3, padx=5, sticky="w")

        # 密码
        ttk.Label(db_frame, text="密码:").grid(row=1, column=2, sticky="w", pady=3)
        self.db_password_var = tk.StringVar(value="root")
        ttk.Entry(db_frame, textvariable=self.db_password_var, width=12, show="*").grid(row=1, column=3, pady=3, padx=5, sticky="w")

        # 数据库名
        ttk.Label(db_frame, text="数据库名:").grid(row=2, column=0, sticky="w", pady=3)
        self.db_name_var = tk.StringVar(value="xianyu")
        ttk.Entry(db_frame, textvariable=self.db_name_var, width=20).grid(row=2, column=1, pady=3, padx=5, sticky="w")

        # 测试连接按钮
        test_db_btn = ttk.Button(db_frame, text="测试连接", command=self._test_db_connection)
        test_db_btn.grid(row=2, column=2, columnspan=2, pady=3, padx=5)

        # Coze 工作流变量配置区域
        coze_vars_frame = ttk.LabelFrame(self.root, text="Coze 工作流变量配置", padding=10)
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

        # 创建变量配置行
        var_configs = [
            ('buyer_name', '买家用户名'),
            ('product_title', '商品标题'),
            ('product_price', '商品价格'),
            ('order_status', '订单状态'),
        ]

        for var_key, desc in var_configs:
            row_frame = ttk.Frame(vars_list_frame)
            row_frame.pack(fill="x", pady=2)

            # 启用复选框
            enabled_var = tk.BooleanVar(value=self.coze_vars_config.get(var_key, {}).get('enabled', True))
            ttk.Checkbutton(row_frame, variable=enabled_var, width=3).pack(side="left")

            # 变量名输入框
            name_var = tk.StringVar(value=self.coze_vars_config.get(var_key, {}).get('name', var_key))
            ttk.Entry(row_frame, textvariable=name_var, width=15).pack(side="left", padx=5)

            # 说明标签
            ttk.Label(row_frame, text=desc, width=12).pack(side="left", padx=5)

            # 订单状态行添加"查看详情"按钮
            if var_key == 'order_status':
                ttk.Button(row_frame, text="查看映射详情", command=self._show_status_mapping_popup, width=12).pack(side="left", padx=10)

            self.var_entries[var_key] = {
                'enabled': enabled_var,
                'name': name_var,
                'desc': desc
            }

        # 系统提示词配置区域
        prompt_frame = ttk.LabelFrame(self.root, text="系统提示词 (prompt)", padding=10)
        prompt_frame.pack(fill="x", padx=20, pady=10)

        ttk.Label(prompt_frame, text="在 Coze 智能体的人设中使用 {{prompt}} 引用此变量:").pack(anchor="w")

        self.prompt_text = tk.Text(prompt_frame, height=4, font=("Microsoft YaHei", 9))
        self.prompt_text.pack(fill="x", pady=5)
        if hasattr(self, 'prompt_content') and self.prompt_content:
            self.prompt_text.insert("1.0", self.prompt_content)

        # 保存配置按钮
        save_frame = ttk.Frame(self.root)
        save_frame.pack(fill="x", padx=20, pady=5)
        save_btn = ttk.Button(save_frame, text="保存所有配置", command=self._save_config)
        save_btn.pack(side="right")

        # 控制区域
        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill="x", padx=20, pady=10)

        # 启动/停止按钮
        self.start_btn = ttk.Button(
            control_frame,
            text="启动",
            command=self._toggle_running,
            width=15
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

        # 测试白名单按钮
        user_mgmt_btn = ttk.Button(
            control_frame,
            text="上下文管理",
            command=self._open_user_management_popup,
            width=12
        )
        user_mgmt_btn.pack(side="right", padx=5)

        # 新会话回忆按钮
        memory_btn = ttk.Button(
            control_frame,
            text="新会话回忆",
            command=self._open_memory_settings_popup,
            width=12
        )
        memory_btn.pack(side="right", padx=5)

        # 消息合并按钮
        merge_btn = ttk.Button(
            control_frame,
            text="消息合并",
            command=self._open_merge_settings_popup,
            width=12
        )
        merge_btn.pack(side="right", padx=5)

        # Coze会话管理按钮
        coze_session_btn = ttk.Button(
            control_frame,
            text="Coze会话",
            command=self._open_coze_sessions_popup,
            width=12
        )
        coze_session_btn.pack(side="right", padx=5)

        # 清空数据库按钮
        clear_db_btn = ttk.Button(
            control_frame,
            text="清空数据库",
            command=self._clear_database,
            width=12
        )
        clear_db_btn.pack(side="right", padx=5)

        # 日志区域 - 使用 Notebook 双标签页
        log_frame = ttk.LabelFrame(self.root, text="运行日志", padding=10)
        log_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # 创建 Notebook
        self.log_notebook = ttk.Notebook(log_frame)
        self.log_notebook.pack(fill="both", expand=True)

        # Tab 1: 对话记录表格
        conv_tab = ttk.Frame(self.log_notebook)
        self.log_notebook.add(conv_tab, text="对话记录")

        # 对话记录表格
        conv_columns = ('time', 'level', 'type', 'username', 'content', 'conv_id', 'order_status')
        self.conv_tree = ttk.Treeview(conv_tab, columns=conv_columns, show='headings', height=10)
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
        self.conv_tree.column('content', width=450, minwidth=250, anchor='w')
        self.conv_tree.column('conv_id', width=180, minwidth=120, anchor='center')
        self.conv_tree.column('order_status', width=80, minwidth=60, anchor='center')

        # 对话表格滚动条
        conv_scrollbar = ttk.Scrollbar(conv_tab, orient="vertical", command=self.conv_tree.yview)
        self.conv_tree.configure(yscrollcommand=conv_scrollbar.set)
        self.conv_tree.pack(side="left", fill="both", expand=True)
        conv_scrollbar.pack(side="right", fill="y")

        # 设置行颜色标签
        self.conv_tree.tag_configure('user', background='#e3f2fd')  # 浅蓝色 - 用户消息
        self.conv_tree.tag_configure('ai', background='#f3e5f5')    # 浅紫色 - AI回复
        self.conv_tree.tag_configure('info', background='#ffffff')  # 白色 - 普通信息
        self.conv_tree.tag_configure('warning', background='#fff8e1')  # 浅黄色 - 警告
        self.conv_tree.tag_configure('error', background='#ffebee')  # 浅红色 - 错误

        # Tab 2: 系统日志
        sys_tab = ttk.Frame(self.log_notebook)
        self.log_notebook.add(sys_tab, text="系统日志")

        self.log_text = scrolledtext.ScrolledText(
            sys_tab,
            height=10,
            font=("Microsoft YaHei", 9),
            bg="#1e1e1e",  # 深色背景
            fg="#d4d4d4",  # 默认浅灰色文字
            insertbackground="white",
            state="disabled",
            spacing1=1,  # 段落前间距
            spacing3=1,  # 段落后间距
        )
        self.log_text.pack(fill="both", expand=True)

        # 配置不同日志级别的颜色标签
        self.log_text.tag_configure("INFO", foreground="#4ec9b0")      # 青绿色
        self.log_text.tag_configure("DEBUG", foreground="#808080")     # 灰色
        self.log_text.tag_configure("WARNING", foreground="#dcdcaa")   # 黄色
        self.log_text.tag_configure("ERROR", foreground="#f14c4c")     # 红色
        self.log_text.tag_configure("SUCCESS", foreground="#6a9955")   # 绿色
        self.log_text.tag_configure("TIME", foreground="#569cd6")      # 蓝色 - 时间戳

        # 控制区域
        log_control_frame = ttk.Frame(log_frame)
        log_control_frame.pack(fill="x", pady=5)

        # 详细日志开关
        self.debug_log_var = tk.BooleanVar(value=False)
        debug_check = ttk.Checkbutton(
            log_control_frame,
            text="显示详细日志",
            variable=self.debug_log_var,
            command=self._toggle_debug_logs
        )
        debug_check.pack(side="left")

        clear_btn = ttk.Button(log_control_frame, text="清空日志", command=self._clear_log)
        clear_btn.pack(side="right")

        # 底部信息
        footer = tk.Label(
            self.root,
            text="基于 Coze AI + Playwright 构建",
            font=("Microsoft YaHei", 8),
            fg="gray"
        )
        footer.pack(pady=5)

    def _toggle_token_visibility(self):
        """切换密钥显示/隐藏"""
        if self.show_token.get():
            self.api_token_entry.config(show="")
        else:
            self.api_token_entry.config(show="*")

    def _toggle_duplicate_filter(self):
        """切换重复消息过滤开关"""
        if self.skip_duplicate_var.get():
            self.msg_expire_spinbox.config(state="normal")
        else:
            self.msg_expire_spinbox.config(state="disabled")

    def _toggle_inactive_settings(self):
        """切换主动发消息设置开关"""
        if self.inactive_enabled_var.get():
            self.inactive_timeout_spinbox.config(state="normal")
        else:
            self.inactive_timeout_spinbox.config(state="disabled")

    def _load_config(self):
        """加载配置"""
        self.api_token_var.set(os.getenv("COZE_API_TOKEN", ""))
        self.bot_id_var.set(os.getenv("COZE_BOT_ID", ""))
        self.interval_var.set(os.getenv("XIANYU_CHECK_INTERVAL", "2"))
        # 重复消息过滤配置
        self.skip_duplicate_var.set(os.getenv("SKIP_DUPLICATE_MSG", "true").lower() == "true")
        self.msg_expire_var.set(os.getenv("MSG_EXPIRE_SECONDS", "60"))
        self._toggle_duplicate_filter()  # 更新spinbox状态
        # Inactive 主动发消息配置
        self.inactive_enabled_var.set(os.getenv("INACTIVE_ENABLED", "true").lower() == "true")
        self.inactive_timeout_var.set(os.getenv("INACTIVE_TIMEOUT_MINUTES", "3"))
        self._toggle_inactive_settings()  # 更新spinbox状态
        # 会话切换延迟配置
        self.enter_delay_var.set(os.getenv("CONVERSATION_ENTER_DELAY", "1.5"))
        # 数据库配置
        self.db_host_var.set(os.getenv("DB_HOST", "localhost"))
        self.db_port_var.set(os.getenv("DB_PORT", "3306"))
        self.db_user_var.set(os.getenv("DB_USER", "root"))
        self.db_password_var.set(os.getenv("DB_PASSWORD", "root"))
        self.db_name_var.set(os.getenv("DB_NAME", "xianyu"))

    def _save_config(self):
        """保存配置到 .env 文件"""
        try:
            # 确保 .env 文件存在
            if not self.env_path.exists():
                self.env_path.touch()

            set_key(str(self.env_path), "COZE_API_TOKEN", self.api_token_var.get())
            set_key(str(self.env_path), "COZE_BOT_ID", self.bot_id_var.get())
            set_key(str(self.env_path), "XIANYU_CHECK_INTERVAL", self.interval_var.get())
            set_key(str(self.env_path), "HEADLESS", "false")
            # 重复消息过滤配置
            set_key(str(self.env_path), "SKIP_DUPLICATE_MSG", str(self.skip_duplicate_var.get()).lower())
            set_key(str(self.env_path), "MSG_EXPIRE_SECONDS", self.msg_expire_var.get())
            # Inactive 主动发消息配置
            set_key(str(self.env_path), "INACTIVE_ENABLED", str(self.inactive_enabled_var.get()).lower())
            set_key(str(self.env_path), "INACTIVE_TIMEOUT_MINUTES", self.inactive_timeout_var.get())
            # 会话切换延迟配置
            set_key(str(self.env_path), "CONVERSATION_ENTER_DELAY", self.enter_delay_var.get())
            # 数据库配置
            set_key(str(self.env_path), "DB_HOST", self.db_host_var.get())
            set_key(str(self.env_path), "DB_PORT", self.db_port_var.get())
            set_key(str(self.env_path), "DB_USER", self.db_user_var.get())
            set_key(str(self.env_path), "DB_PASSWORD", self.db_password_var.get())
            set_key(str(self.env_path), "DB_NAME", self.db_name_var.get())

            # 保存Coze变量配置
            self._save_coze_vars_config()

            # 重新加载环境变量
            load_dotenv(self.env_path, override=True)

            messagebox.showinfo("成功", "配置已保存！")
            self._log("配置已保存（包含Coze变量配置）")
        except Exception as e:
            messagebox.showerror("错误", f"保存配置失败: {e}")

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

    def _load_coze_vars_config(self):
        """加载Coze变量配置"""
        try:
            if self.vars_config_path.exists():
                with open(self.vars_config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.coze_vars_config = data.get('vars', DEFAULT_COZE_VARS.copy())
                    self.status_mapping = data.get('status_mapping', DEFAULT_STATUS_MAPPING.copy())
                    self.prompt_content = data.get('prompt', '')
            else:
                self.coze_vars_config = DEFAULT_COZE_VARS.copy()
                self.status_mapping = DEFAULT_STATUS_MAPPING.copy()
                self.prompt_content = ''
        except Exception as e:
            logger.error(f"加载Coze变量配置失败: {e}")
            self.coze_vars_config = DEFAULT_COZE_VARS.copy()
            self.status_mapping = DEFAULT_STATUS_MAPPING.copy()
            self.prompt_content = ''

    def _save_coze_vars_config(self):
        """保存Coze变量配置"""
        try:
            # 从UI收集变量配置
            for var_key, entry_data in self.var_entries.items():
                self.coze_vars_config[var_key] = {
                    'name': entry_data['name'].get(),
                    'desc': entry_data['desc'],
                    'enabled': entry_data['enabled'].get()
                }

            # 获取 prompt 内容
            prompt_content = self.prompt_text.get("1.0", "end-1c").strip()

            # 保存到文件
            data = {
                'vars': self.coze_vars_config,
                'status_mapping': self.status_mapping,
                'prompt': prompt_content
            }
            with open(self.vars_config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            logger.error(f"保存Coze变量配置失败: {e}")
            return False

    def _show_status_mapping_popup(self):
        """显示订单状态映射浮层"""
        popup = tk.Toplevel(self.root)
        popup.title("订单状态映射详情")
        popup.geometry("650x450")
        popup.transient(self.root)
        popup.grab_set()

        # 标题
        ttk.Label(
            popup,
            text="闲鱼原始状态 → 传给Coze的值 | 系统消息",
            font=("Microsoft YaHei", 10, "bold")
        ).pack(pady=10)

        # 创建表格框架
        table_frame = ttk.Frame(popup)
        table_frame.pack(fill="both", expand=True, padx=15, pady=5)

        # 创建Treeview显示所有映射（3列）
        columns = ('original', 'mapped', 'system_msg')
        tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=12)
        tree.heading('original', text='闲鱼原始状态')
        tree.heading('mapped', text='传给Coze的值')
        tree.heading('system_msg', text='系统消息内容')
        tree.column('original', width=150)
        tree.column('mapped', width=100)
        tree.column('system_msg', width=200)

        # 滚动条
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 填充数据
        for orig, value in self.status_mapping.items():
            if isinstance(value, dict):
                mapped = value.get('mapped', '')
                system_msg = value.get('system_msg', '')
            else:
                # 兼容旧格式
                mapped = value
                system_msg = ''
            tree.insert('', 'end', values=(orig, mapped, system_msg))

        # 底部按钮
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

    def _reset_status_mapping_in_popup(self, tree):
        """在浮层中重置映射"""
        if messagebox.askyesno("确认", "确定要重置为默认映射吗？"):
            self.status_mapping = DEFAULT_STATUS_MAPPING.copy()
            # 刷新浮层中的表格
            for item in tree.get_children():
                tree.delete(item)
            for orig, value in self.status_mapping.items():
                if isinstance(value, dict):
                    mapped = value.get('mapped', '')
                    system_msg = value.get('system_msg', '')
                else:
                    mapped = value
                    system_msg = ''
                tree.insert('', 'end', values=(orig, mapped, system_msg))
            self._log("订单状态映射已重置为默认值")

    def _open_status_mapping_dialog(self):
        """打开订单状态映射编辑对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("订单状态映射配置")
        dialog.geometry("700x550")
        dialog.transient(self.root)
        dialog.grab_set()

        # 说明
        ttk.Label(
            dialog,
            text="配置闲鱼原始状态、传给Coze的简化状态、以及系统消息内容的映射关系",
            font=("Microsoft YaHei", 9)
        ).pack(pady=10)

        # 表格框架
        table_frame = ttk.Frame(dialog)
        table_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # 创建Treeview（3列）
        columns = ('original', 'mapped', 'system_msg')
        tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=12)
        tree.heading('original', text='闲鱼原始状态')
        tree.heading('mapped', text='传给Coze的值')
        tree.heading('system_msg', text='系统消息内容')
        tree.column('original', width=150)
        tree.column('mapped', width=100)
        tree.column('system_msg', width=200)

        # 滚动条
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)

        # 填充数据
        for orig, value in self.status_mapping.items():
            if isinstance(value, dict):
                mapped = value.get('mapped', '')
                system_msg = value.get('system_msg', '')
            else:
                mapped = value
                system_msg = ''
            tree.insert('', 'end', values=(orig, mapped, system_msg))

        # 编辑区域
        edit_frame = ttk.LabelFrame(dialog, text="编辑映射", padding=10)
        edit_frame.pack(fill="x", padx=10, pady=10)

        # 第一行：原始状态和映射值
        ttk.Label(edit_frame, text="原始状态:").grid(row=0, column=0, sticky="w", pady=3)
        orig_var = tk.StringVar()
        orig_entry = ttk.Entry(edit_frame, textvariable=orig_var, width=20)
        orig_entry.grid(row=0, column=1, pady=3, padx=5)

        ttk.Label(edit_frame, text="映射值:").grid(row=0, column=2, sticky="w", pady=3)
        mapped_var = tk.StringVar()
        mapped_entry = ttk.Entry(edit_frame, textvariable=mapped_var, width=15)
        mapped_entry.grid(row=0, column=3, pady=3, padx=5)

        # 第二行：系统消息
        ttk.Label(edit_frame, text="系统消息:").grid(row=1, column=0, sticky="w", pady=3)
        system_msg_var = tk.StringVar()
        system_msg_entry = ttk.Entry(edit_frame, textvariable=system_msg_var, width=45)
        system_msg_entry.grid(row=1, column=1, columnspan=3, pady=3, padx=5, sticky="w")

        def on_tree_select(event):
            """选中行时填充编辑框"""
            selection = tree.selection()
            if selection:
                item = tree.item(selection[0])
                values = item['values']
                orig_var.set(values[0] if len(values) > 0 else '')
                mapped_var.set(values[1] if len(values) > 1 else '')
                system_msg_var.set(values[2] if len(values) > 2 else '')

        tree.bind('<<TreeviewSelect>>', on_tree_select)

        def add_mapping():
            """添加映射"""
            orig = orig_var.get().strip()
            mapped = mapped_var.get().strip()
            system_msg = system_msg_var.get().strip()
            if orig and mapped:
                # 检查是否已存在
                for item in tree.get_children():
                    if tree.item(item)['values'][0] == orig:
                        tree.item(item, values=(orig, mapped, system_msg))
                        return
                tree.insert('', 'end', values=(orig, mapped, system_msg))
                orig_var.set('')
                mapped_var.set('')
                system_msg_var.set('')

        def delete_mapping():
            """删除选中的映射"""
            selection = tree.selection()
            if selection:
                tree.delete(selection[0])

        def reset_default():
            """重置为默认映射"""
            if messagebox.askyesno("确认", "确定要重置为默认映射吗？"):
                for item in tree.get_children():
                    tree.delete(item)
                for orig, value in DEFAULT_STATUS_MAPPING.items():
                    if isinstance(value, dict):
                        mapped = value.get('mapped', '')
                        system_msg = value.get('system_msg', '')
                    else:
                        mapped = value
                        system_msg = ''
                    tree.insert('', 'end', values=(orig, mapped, system_msg))

        # 按钮
        btn_frame = ttk.Frame(edit_frame)
        btn_frame.grid(row=2, column=0, columnspan=4, pady=10)

        ttk.Button(btn_frame, text="添加/更新", command=add_mapping).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="删除选中", command=delete_mapping).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="重置默认", command=reset_default).pack(side="left", padx=5)

        def save_and_close():
            """保存并关闭"""
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
            dialog.destroy()
            self._log(f"订单状态映射已更新，共 {len(self.status_mapping)} 个映射")

        # 底部按钮
        bottom_frame = ttk.Frame(dialog)
        bottom_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(bottom_frame, text="保存", command=save_and_close).pack(side="right", padx=5)
        ttk.Button(bottom_frame, text="取消", command=dialog.destroy).pack(side="right", padx=5)

    def _open_user_management_popup(self):
        """打开用户上下文管理弹窗"""
        popup = tk.Toplevel(self.root)
        popup.title("用户上下文管理")
        popup.geometry("1100x500")
        popup.transient(self.root)
        popup.grab_set()

        # 标题
        ttk.Label(
            popup,
            text="用户上下文管理",
            font=("Microsoft YaHei", 12, "bold")
        ).pack(pady=10)

        # 用户列表框架
        list_frame = ttk.LabelFrame(popup, text="所有咨询会话（一个用户可能有多个商品会话）", padding=10)
        list_frame.pack(fill="both", expand=True, padx=15, pady=5)

        # 创建一个内部框架来放置 tree 和滚动条
        tree_container = ttk.Frame(list_frame)
        tree_container.pack(fill="both", expand=True)

        # 创建Treeview显示会话
        columns = ('user_id', 'buyer_name', 'item_id', 'product_title', 'conversation_id', 'last_msg_time')
        tree = ttk.Treeview(tree_container, columns=columns, show='headings', height=12)
        tree.heading('user_id', text='用户ID')
        tree.heading('buyer_name', text='用户名')
        tree.heading('item_id', text='商品ID')
        tree.heading('product_title', text='商品标题')
        tree.heading('conversation_id', text='会话ID')
        tree.heading('last_msg_time', text='最后消息时间')
        tree.column('user_id', width=180)
        tree.column('buyer_name', width=100)
        tree.column('item_id', width=120)
        tree.column('product_title', width=150)
        tree.column('conversation_id', width=220)
        tree.column('last_msg_time', width=130)

        # 垂直滚动条
        v_scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=tree.yview)
        v_scrollbar.pack(side="right", fill="y")

        # 水平滚动条
        h_scrollbar = ttk.Scrollbar(tree_container, orient="horizontal", command=tree.xview)
        h_scrollbar.pack(side="bottom", fill="x")

        # 配置 tree
        tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)

        def refresh_user_list():
            """刷新会话列表"""
            # 清空列表
            for item in tree.get_children():
                tree.delete(item)

            # 从数据库获取所有会话
            try:
                from db_manager import db_manager
                if not db_manager.connection or not db_manager.connection.open:
                    db_manager.connect()

                sessions = db_manager.get_all_sessions_with_status()
                for session in sessions:
                    user_id = session.get('user_id', '')
                    buyer_name = session.get('buyer_name', '') or ''
                    item_id = session.get('item_id', '')
                    product_title = session.get('product_title', '') or ''
                    conv_id = session.get('conversation_id', '') or ''
                    last_msg = session.get('last_message_at')
                    last_msg_str = last_msg.strftime('%m-%d %H:%M') if last_msg else ''

                    # 存储完整值，让列宽自动截断显示
                    tree.insert('', 'end', values=(user_id, buyer_name, item_id, product_title, conv_id, last_msg_str))

            except Exception as e:
                messagebox.showerror("错误", f"获取会话列表失败: {e}")

        # 初始加载
        refresh_user_list()

        # 操作区域
        action_frame = ttk.LabelFrame(popup, text="操作（选中一行后点击按钮）", padding=10)
        action_frame.pack(fill="x", padx=15, pady=10)

        # 操作按钮行
        btn_row = ttk.Frame(action_frame)
        btn_row.pack(fill="x", pady=5)

        # 说明文字
        ttk.Label(btn_row, text="选中会话后:").pack(side="left", padx=(0, 10))

        def clear_context():
            """清除选中会话的上下文"""
            selection = tree.selection()
            if not selection:
                messagebox.showwarning("警告", "请先选择一个会话")
                return

            values = tree.item(selection[0])['values']
            # 索引: 0=user_id, 1=buyer_name, 2=item_id, 3=product_title, 4=conv_id, 5=last_msg_time
            user_id = str(values[0])
            buyer_name = str(values[1])
            item_id = str(values[2])
            product_title = str(values[3]) if values[3] else ''

            # 获取完整的会话ID（从 user_sessions 表）
            try:
                from db_manager import db_manager
                if not db_manager.connection or not db_manager.connection.open:
                    db_manager.connect()

                # 使用 user_id 和 item_id 获取完整的 session 信息
                session = db_manager.get_session(user_id, item_id)
                conv_id = session.get('conversation_id') if session else None

                if not conv_id:
                    messagebox.showwarning("警告", f"该会话没有会话ID，无需清除")
                    return

                # 构建详细信息显示
                detail_info = f"用户: {buyer_name}\n商品ID: {item_id}"
                if product_title:
                    detail_info += f"\n商品标题: {product_title}"
                detail_info += f"\n会话ID: {conv_id}"

                # 确认操作
                if not messagebox.askyesno("确认", f"确定要清除以下会话的对话上下文吗？\n\n{detail_info}\n\n注意：这将清除AI的对话记忆，但不会删除消息记录。"):
                    return

                # 使用同步方法调用Coze API清除上下文
                from coze_client import CozeClient
                client = CozeClient()

                # 在后台线程执行，避免阻塞GUI
                display_info = f"{buyer_name} - {product_title or item_id}"
                def do_clear():
                    try:
                        result = client.clear_conversation_context_sync(conv_id)
                        # 使用 after 在主线程更新GUI
                        self.root.after(0, lambda: on_clear_complete(result, display_info))
                    except Exception as e:
                        self.root.after(0, lambda: on_clear_error(e))

                def on_clear_complete(success, info):
                    if success:
                        messagebox.showinfo("成功", f"已清除会话上下文\n\n{info}\n\n下次对话时，AI将不再参考之前的历史记录。")
                        self._log(f"已清除会话上下文: {info}")
                    else:
                        messagebox.showerror("错误", "清除上下文失败，请查看日志")

                def on_clear_error(e):
                    messagebox.showerror("错误", f"清除上下文失败: {e}")

                # 启动后台线程
                import threading
                thread = threading.Thread(target=do_clear, daemon=True)
                thread.start()

                # 提示用户正在处理
                self._log(f"正在清除会话上下文: {display_info}...")

            except Exception as e:
                messagebox.showerror("错误", f"清除上下文失败: {e}")

        ttk.Button(btn_row, text="清除AI上下文", command=clear_context).pack(side="left", padx=5)

        def clear_local_history():
            """清除选中会话的本地对话历史"""
            selection = tree.selection()
            if not selection:
                messagebox.showwarning("警告", "请先选择一个会话")
                return

            values = tree.item(selection[0])['values']
            # 索引: 0=user_id, 1=buyer_name, 2=item_id, 3=product_title, 4=conv_id, 5=last_msg_time
            user_id = str(values[0])
            buyer_name = str(values[1])
            item_id = str(values[2])
            product_title = str(values[3]) if values[3] else ''

            # 构建详细信息显示
            detail_info = f"用户: {buyer_name}\n商品ID: {item_id}"
            if product_title:
                detail_info += f"\n商品标题: {product_title}"

            if not messagebox.askyesno("确认", f"确定要清除以下会话的本地记录吗？\n\n{detail_info}\n\n这将删除该会话在数据库中的记录。"):
                return

            try:
                from db_manager import db_manager
                if not db_manager.connection or not db_manager.connection.open:
                    db_manager.connect()

                if db_manager.delete_session(user_id, item_id):
                    display_info = f"{buyer_name} - {product_title or item_id}"
                    messagebox.showinfo("成功", f"已清除会话记录: {display_info}")
                    refresh_user_list()
                    self._log(f"已清除会话记录: {display_info}")
                else:
                    messagebox.showerror("错误", "清除失败")
            except Exception as e:
                messagebox.showerror("错误", f"清除失败: {e}")

        ttk.Button(btn_row, text="删除本地会话记录", command=clear_local_history).pack(side="left", padx=5)

        # 底部按钮
        bottom_frame = ttk.Frame(popup)
        bottom_frame.pack(fill="x", padx=15, pady=10)

        ttk.Button(bottom_frame, text="刷新", command=refresh_user_list).pack(side="left", padx=5)
        ttk.Button(bottom_frame, text="关闭", command=popup.destroy).pack(side="right", padx=5)

    def _open_memory_settings_popup(self):
        """打开新会话回忆设置弹窗"""
        popup = tk.Toplevel(self.root)
        popup.title("新会话回忆设置")
        popup.geometry("650x500")
        popup.transient(self.root)
        popup.grab_set()

        # 标题
        ttk.Label(
            popup,
            text="新会话回忆 - 跨商品上下文传递",
            font=("Microsoft YaHei", 12, "bold")
        ).pack(pady=10)

        # 说明文字
        desc_frame = ttk.LabelFrame(popup, text="功能说明", padding=10)
        desc_frame.pack(fill="x", padx=15, pady=5)

        desc_text = """当同一个用户从不同商品页面发起聊天时，系统会自动获取该用户之前与其他商品的对话历史，
并将这些历史记录作为上下文传递给新会话的第一条消息，帮助AI更好地了解用户的需求和偏好。

适用场景：
• 用户咨询过商品A后，又来咨询商品B
• 用户是回头客，之前有过购买/咨询记录
• 需要跨商品保持对话连贯性的场景"""

        ttk.Label(desc_frame, text=desc_text, justify="left", wraplength=580).pack(anchor="w")

        # 设置区域
        settings_frame = ttk.LabelFrame(popup, text="设置", padding=10)
        settings_frame.pack(fill="x", padx=15, pady=10)

        # 启用开关
        row1 = ttk.Frame(settings_frame)
        row1.pack(fill="x", pady=5)

        self.memory_enabled_var = tk.BooleanVar(value=os.getenv("MEMORY_ENABLED", "true").lower() == "true")
        ttk.Checkbutton(
            row1,
            text="启用新会话回忆功能",
            variable=self.memory_enabled_var
        ).pack(side="left")

        # 上下文轮数设置
        row2 = ttk.Frame(settings_frame)
        row2.pack(fill="x", pady=5)

        ttk.Label(row2, text="获取历史对话轮数:").pack(side="left")
        self.memory_rounds_var = tk.StringVar(value=os.getenv("MEMORY_CONTEXT_ROUNDS", "5"))
        memory_rounds_spinbox = ttk.Spinbox(
            row2,
            from_=1,
            to=20,
            textvariable=self.memory_rounds_var,
            width=5
        )
        memory_rounds_spinbox.pack(side="left", padx=5)
        ttk.Label(row2, text="轮 (每轮包含用户问+AI答)").pack(side="left")

        # 示例展示区域
        example_frame = ttk.LabelFrame(popup, text="传递给新会话的 input 内容示例", padding=10)
        example_frame.pack(fill="both", expand=True, padx=15, pady=10)

        example_text = scrolledtext.ScrolledText(
            example_frame,
            height=12,
            font=("Consolas", 9),
            bg="#f5f5f5",
            state="normal"
        )
        example_text.pack(fill="both", expand=True)

        # 示例内容
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

        # 底部按钮
        btn_frame = ttk.Frame(popup)
        btn_frame.pack(fill="x", padx=15, pady=10)

        def save_memory_settings():
            """保存新会话回忆设置"""
            try:
                set_key(str(self.env_path), "MEMORY_ENABLED", str(self.memory_enabled_var.get()).lower())
                set_key(str(self.env_path), "MEMORY_CONTEXT_ROUNDS", self.memory_rounds_var.get())
                load_dotenv(self.env_path, override=True)
                messagebox.showinfo("成功", "新会话回忆设置已保存！")
                self._log(f"新会话回忆设置已保存 - 启用: {self.memory_enabled_var.get()}, 轮数: {self.memory_rounds_var.get()}")
                popup.destroy()
            except Exception as e:
                messagebox.showerror("错误", f"保存设置失败: {e}")

        ttk.Button(btn_frame, text="保存", command=save_memory_settings).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="取消", command=popup.destroy).pack(side="right", padx=5)

    def _open_coze_sessions_popup(self):
        """打开Coze会话管理弹窗"""
        from db_manager import db_manager
        from coze_client import CozeClient
        import threading
        from datetime import datetime

        popup = tk.Toplevel(self.root)
        popup.title("Coze会话管理")
        popup.geometry("900x550")
        popup.transient(self.root)
        popup.grab_set()

        # 说明
        ttk.Label(popup, text="查看和管理Coze服务器上的会话（从Coze API获取）", font=('', 10)).pack(pady=10)

        # 列表区域
        list_frame = ttk.Frame(popup)
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # 创建表格 - 根据 Coze API 返回的字段调整
        columns = ('conversation_id', 'created_at', 'last_section_id')
        tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)
        tree.heading('conversation_id', text='会话ID')
        tree.heading('created_at', text='创建时间')
        tree.heading('last_section_id', text='最后章节ID')

        tree.column('conversation_id', width=250, minwidth=200)
        tree.column('created_at', width=180, minwidth=150)
        tree.column('last_section_id', width=250, minwidth=200)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 状态标签
        status_label = ttk.Label(popup, text="")
        status_label.pack(pady=5)

        # 存储会话数据用于删除操作
        conversations_data = []

        def refresh_list():
            """从Coze API刷新会话列表"""
            nonlocal conversations_data

            status_label.config(text="正在从Coze获取会话列表...")
            popup.update()

            def do_refresh():
                try:
                    coze_client = CozeClient()
                    result = coze_client.list_conversations_sync(page_num=1, page_size=50)
                    # 在主线程更新UI
                    popup.after(0, lambda: on_refresh_complete(result))
                except Exception as e:
                    popup.after(0, lambda: on_refresh_error(e))

            def on_refresh_complete(result):
                nonlocal conversations_data
                # 清空列表
                for item in tree.get_children():
                    tree.delete(item)

                conversations_data = result.get('conversations', [])
                for conv in conversations_data:
                    conv_id = conv.get('id', '')
                    created_at = conv.get('created_at', 0)
                    last_section_id = conv.get('last_section_id', '')

                    # 转换时间戳
                    created_at_str = ''
                    if created_at:
                        try:
                            created_at_str = datetime.fromtimestamp(int(created_at)).strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            created_at_str = str(created_at)

                    tree.insert('', 'end', values=(conv_id, created_at_str, last_section_id))

                has_more = result.get('has_more', False)
                status_text = f"共 {len(conversations_data)} 个会话"
                if has_more:
                    status_text += " (还有更多)"
                status_label.config(text=status_text)

            def on_refresh_error(e):
                status_label.config(text=f"获取失败: {e}")
                messagebox.showerror("错误", f"获取Coze会话列表失败: {e}")

            # 在后台线程执行
            threading.Thread(target=do_refresh, daemon=True).start()

        def clear_all_sessions():
            """清空所有Coze会话"""
            if not conversations_data:
                messagebox.showinfo("提示", "没有需要清空的会话")
                return

            if not messagebox.askyesno("确认", f"确定要删除Coze服务器上的所有 {len(conversations_data)} 个会话吗？\n\n注意：这将永久删除这些会话！"):
                return

            status_label.config(text="正在删除会话...")
            popup.update()

            def do_clear():
                coze_client = CozeClient()
                success_count = 0
                fail_count = 0

                for conv in conversations_data:
                    conv_id = conv.get('id')
                    if conv_id:
                        try:
                            if coze_client.delete_conversation_sync(conv_id):
                                success_count += 1
                            else:
                                fail_count += 1
                        except Exception as e:
                            fail_count += 1

                # 同时清空数据库中的conversation_id
                db_manager.clear_all_conversation_ids()

                # 更新UI（在主线程中）
                def update_ui():
                    status_label.config(text=f"清空完成: 成功{success_count}个, 失败{fail_count}个")
                    refresh_list()
                    messagebox.showinfo("完成", f"Coze会话清空完成\n\n成功: {success_count}\n失败: {fail_count}")
                    self._log(f"已清空 {success_count} 个Coze会话")

                popup.after(0, update_ui)

            # 在后台线程执行清空操作
            threading.Thread(target=do_clear, daemon=True).start()

        # 按钮区域
        btn_frame = ttk.Frame(popup)
        btn_frame.pack(pady=15)

        ttk.Button(btn_frame, text="刷新列表", command=refresh_list, width=15).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="一键清空所有会话", command=clear_all_sessions, width=20).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="关闭", command=popup.destroy, width=10).pack(side="left", padx=10)

        # 初始加载
        refresh_list()

    def _clear_database(self):
        """清空数据库所有表的数据"""
        from db_manager import db_manager

        # 简单确认
        if not messagebox.askyesno("确认", "确定要清空所有数据库表吗？\n\n将清空：用户表、会话表、对话历史表"):
            return

        # 确保数据库已连接
        if not db_manager.connection:
            db_manager.connect()

        if db_manager.clear_all_tables():
            messagebox.showinfo("成功", "数据库已清空！")
            self._log("已清空所有数据库表")
        else:
            messagebox.showerror("错误", "清空数据库失败，请查看日志")

    def _open_merge_settings_popup(self):
        """打开消息合并设置弹窗"""
        popup = tk.Toplevel(self.root)
        popup.title("消息合并设置")
        popup.geometry("650x550")
        popup.transient(self.root)
        popup.grab_set()

        # 标题
        ttk.Label(
            popup,
            text="消息合并 - 防止用户分段发送导致AI回复混乱",
            font=("Microsoft YaHei", 12, "bold")
        ).pack(pady=10)

        # 说明文字
        desc_frame = ttk.LabelFrame(popup, text="功能说明", padding=10)
        desc_frame.pack(fill="x", padx=15, pady=5)

        desc_text = """当用户快速连续发送多条短消息时（如"pro"、"还有"、"吗"），系统会等待一段时间，
将这些消息合并成一条完整的消息（"pro还有吗"）再发送给AI处理，避免AI对不完整的消息产生错误回复。

工作原理：
• 当收到长度小于阈值的短消息时，消息会进入等待队列
• 在等待时间内收到的新消息会不断追加到队列中
• 等待时间结束后，所有排队消息会合并成一条发送给AI
• 如果收到一条长消息，会立即将之前排队的消息一起合并处理"""

        ttk.Label(desc_frame, text=desc_text, justify="left", wraplength=580).pack(anchor="w")

        # 设置区域
        settings_frame = ttk.LabelFrame(popup, text="设置", padding=10)
        settings_frame.pack(fill="x", padx=15, pady=10)

        # 启用开关
        row1 = ttk.Frame(settings_frame)
        row1.pack(fill="x", pady=5)

        self.merge_enabled_var = tk.BooleanVar(value=os.getenv("MESSAGE_MERGE_ENABLED", "true").lower() == "true")
        ttk.Checkbutton(
            row1,
            text="启用消息合并功能",
            variable=self.merge_enabled_var
        ).pack(side="left")

        # 等待时间设置
        row2 = ttk.Frame(settings_frame)
        row2.pack(fill="x", pady=5)

        ttk.Label(row2, text="等待合并时间:").pack(side="left")
        self.merge_wait_var = tk.StringVar(value=os.getenv("MESSAGE_MERGE_WAIT_SECONDS", "3"))
        merge_wait_spinbox = ttk.Spinbox(
            row2,
            from_=1,
            to=10,
            textvariable=self.merge_wait_var,
            width=5
        )
        merge_wait_spinbox.pack(side="left", padx=5)
        ttk.Label(row2, text="秒 (收到短消息后等待多久再处理)").pack(side="left")

        # 短消息阈值设置
        row3 = ttk.Frame(settings_frame)
        row3.pack(fill="x", pady=5)

        ttk.Label(row3, text="短消息阈值:").pack(side="left")
        self.merge_min_length_var = tk.StringVar(value=os.getenv("MESSAGE_MERGE_MIN_LENGTH", "5"))
        merge_length_spinbox = ttk.Spinbox(
            row3,
            from_=1,
            to=20,
            textvariable=self.merge_min_length_var,
            width=5
        )
        merge_length_spinbox.pack(side="left", padx=5)
        ttk.Label(row3, text="字 (低于此长度的消息会触发合并等待)").pack(side="left")

        # 示例展示区域
        example_frame = ttk.LabelFrame(popup, text="效果示例", padding=10)
        example_frame.pack(fill="both", expand=True, padx=15, pady=10)

        example_text = scrolledtext.ScrolledText(
            example_frame,
            height=10,
            font=("Consolas", 9),
            bg="#f5f5f5",
            state="normal"
        )
        example_text.pack(fill="both", expand=True)

        # 示例内容
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

        # 底部按钮
        btn_frame = ttk.Frame(popup)
        btn_frame.pack(fill="x", padx=15, pady=10)

        def save_merge_settings():
            """保存消息合并设置"""
            try:
                set_key(str(self.env_path), "MESSAGE_MERGE_ENABLED", str(self.merge_enabled_var.get()).lower())
                set_key(str(self.env_path), "MESSAGE_MERGE_WAIT_SECONDS", self.merge_wait_var.get())
                set_key(str(self.env_path), "MESSAGE_MERGE_MIN_LENGTH", self.merge_min_length_var.get())
                load_dotenv(self.env_path, override=True)
                messagebox.showinfo("成功", "消息合并设置已保存！\n\n注意：设置将在下次启动时生效。")
                self._log(f"消息合并设置已保存 - 启用: {self.merge_enabled_var.get()}, 等待: {self.merge_wait_var.get()}秒, 阈值: {self.merge_min_length_var.get()}字")
                popup.destroy()
            except Exception as e:
                messagebox.showerror("错误", f"保存设置失败: {e}")

        ttk.Button(btn_frame, text="保存", command=save_merge_settings).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="取消", command=popup.destroy).pack(side="right", padx=5)

    def _setup_logging(self):
        """设置日志重定向到界面"""
        class GUILogHandler:
            def __init__(self, text_widget, gui):
                self.text_widget = text_widget
                self.gui = gui

            def write(self, message):
                if message.strip():
                    self.gui.root.after(0, self._append_log, message)

            def _append_log(self, message):
                self.text_widget.config(state="normal")
                # 解析日志格式: "HH:mm:ss | LEVEL | message"
                parts = message.split(" | ", 2)
                if len(parts) >= 2:
                    time_str = parts[0]
                    level = parts[1].strip()
                    content = parts[2] if len(parts) > 2 else ""
                    # 插入时间戳（蓝色）
                    start_idx = self.text_widget.index("end-1c")
                    self.text_widget.insert("end", f"{time_str} | ")
                    self.text_widget.tag_add("TIME", start_idx, "end-1c")
                    # 插入级别（对应颜色）
                    start_idx = self.text_widget.index("end-1c")
                    self.text_widget.insert("end", f"{level} | ")
                    self.text_widget.tag_add(level, start_idx, "end-1c")
                    # 插入消息内容（对应颜色）
                    start_idx = self.text_widget.index("end-1c")
                    self.text_widget.insert("end", f"{content}\n")
                    self.text_widget.tag_add(level, start_idx, "end-1c")
                else:
                    self.text_widget.insert("end", message + "\n")
                self.text_widget.see("end")
                self.text_widget.config(state="disabled")

            def flush(self):
                pass

        # 添加自定义日志处理器（默认 INFO 级别）
        self.gui_handler = GUILogHandler(self.log_text, self)
        self.log_handler_id = logger.add(
            self.gui_handler.write,
            format="{time:HH:mm:ss} | {level} | {message}",
            level="INFO"
        )

    def _toggle_debug_logs(self):
        """切换详细日志显示"""
        self.show_debug_logs = self.debug_log_var.get()

        # 移除旧的 handler
        if self.log_handler_id is not None:
            try:
                logger.remove(self.log_handler_id)
            except ValueError:
                pass

        # 添加新的 handler，根据开关设置日志级别
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
        """注册对话记录回调函数"""
        def on_conversation(msg_type, username, content, conv_id, order_status, level):
            # 使用 after 确保在主线程执行
            self.root.after(0, lambda: self.add_conversation_record(
                msg_type, username, content, conv_id, order_status, level
            ))

        set_gui_conversation_callback(on_conversation)
        logger.debug("GUI对话记录回调已注册")

    def _log(self, message, level="INFO"):
        """添加系统日志（倒序显示，最新在最上面）"""
        self.log_text.config(state="normal")
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        # 构建完整的日志行
        log_line = f"{timestamp} | {message}\n"
        # 插入到开头
        self.log_text.insert("1.0", log_line)
        # 添加标签颜色
        time_end = f"1.{len(timestamp) + 3}"  # "HH:MM:SS | " 的长度
        self.log_text.tag_add("TIME", "1.0", time_end)
        msg_end = f"1.{len(log_line) - 1}"  # 不包括换行符
        self.log_text.tag_add(level, time_end, msg_end)
        self.log_text.see("1.0")
        self.log_text.config(state="disabled")

    def add_conversation_record(self, msg_type: str, username: str, content: str,
                                  conv_id: str = "", order_status: str = "", level: str = "INFO"):
        """
        添加对话记录到表格

        Args:
            msg_type: 消息类型 - "user" 或 "AI"
            username: 用户名
            content: 消息内容
            conv_id: 会话ID
            order_status: 订单状态
            level: 级别 - "INFO", "WARNING", "ERROR" 等
        """
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        # 处理内容显示：图片URL不截断，普通文本截断
        display_content = content
        # 替换换行符为空格
        display_content = display_content.replace("\n", " ")
        # 如果不是图片URL，则截断过长内容
        if not ("http" in content and "alicdn" in content):
            if len(display_content) > 100:
                display_content = display_content[:100] + "..."

        # 处理会话ID显示：截断过长的ID
        display_conv_id = conv_id if conv_id else ""
        if len(display_conv_id) > 20:
            display_conv_id = display_conv_id[:8] + "..." + display_conv_id[-8:]

        # 根据类型和级别确定行标签
        if msg_type.lower() == "user":
            tag = 'user'
        elif msg_type.lower() == "ai":
            tag = 'ai'
        elif level.upper() == "ERROR":
            tag = 'error'
        elif level.upper() == "WARNING":
            tag = 'warning'
        else:
            tag = 'info'

        # 插入记录
        self.conv_tree.insert('', 'end',
                              values=(timestamp, level, msg_type, username, display_content, display_conv_id, order_status),
                              tags=(tag,))
        # 滚动到最新记录
        children = self.conv_tree.get_children()
        if children:
            self.conv_tree.see(children[-1])

    def _clear_log(self):
        """清空日志（两个标签页）"""
        # 清空系统日志
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, "end")
        self.log_text.config(state="disabled")

        # 清空对话记录表格
        for item in self.conv_tree.get_children():
            self.conv_tree.delete(item)

    def _toggle_running(self):
        """切换运行状态"""
        if self.is_running:
            self._stop()
        else:
            self._start()

    def _start(self):
        """启动程序"""
        # 验证配置
        if not self.api_token_var.get():
            messagebox.showwarning("警告", "请先填写 API Token")
            return
        if not self.bot_id_var.get():
            messagebox.showwarning("警告", "请先填写 Bot ID")
            return

        # 保存当前配置
        self._save_config()

        self.is_running = True
        self.start_btn.config(text="停止")
        self.status_var.set("运行中...")
        self.status_label.config(fg="green")

        self._log("正在启动...")

        # 在新线程中运行
        self.thread = threading.Thread(target=self._run_handler, daemon=True)
        self.thread.start()

    def _run_handler(self):
        """在线程中运行消息处理器"""
        try:
            # 重新加载配置
            load_dotenv(self.env_path, override=True)

            # 导入并运行
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
        """停止后的处理"""
        self.is_running = False
        self.start_btn.config(text="启动")
        self.status_var.set("已停止")
        self.status_label.config(fg="gray")
        self._log("已停止")

    def run(self):
        """运行GUI"""
        # 关闭窗口时的处理
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
