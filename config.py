"""配置管理模块"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


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
    'order_status': {'name': 'order_status', 'desc': '订单状态', 'enabled': True},
    'product_info': {'name': 'product_info', 'desc': '商品信息', 'enabled': True},
}


def _load_vars_config():
    """加载变量配置文件"""
    config_path = Path(__file__).parent / "coze_vars_config.json"
    try:
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {'vars': DEFAULT_COZE_VARS, 'status_mapping': DEFAULT_STATUS_MAPPING}


# ============================================================
# Coze 工作流变量配置
# 这些常量对应 Coze 工作流开始节点中定义的输入参数名称
# 现在支持从 GUI 配置文件动态读取
# ============================================================
class CozeVars:
    """Coze 工作流变量名称常量（与工作流开始节点参数名对应）"""

    # 默认变量名（可被配置文件覆盖）
    BUYER_NAME = "buyer_name"           # 买家用户名
    ORDER_STATUS = "order_status"       # 订单状态
    PRODUCT_INFO = "product_info"       # 商品信息

    @classmethod
    def _get_config(cls):
        """获取配置"""
        return _load_vars_config()

    @classmethod
    def get_var_name(cls, var_key: str) -> str:
        """获取变量名（从配置文件读取）"""
        config = cls._get_config()
        vars_config = config.get('vars', {})
        if var_key in vars_config:
            return vars_config[var_key].get('name', var_key)
        return var_key

    @classmethod
    def is_var_enabled(cls, var_key: str) -> bool:
        """检查变量是否启用"""
        config = cls._get_config()
        vars_config = config.get('vars', {})
        if var_key in vars_config:
            return vars_config[var_key].get('enabled', True)
        return True

    @classmethod
    def get_status_mapping(cls) -> dict:
        """获取订单状态映射表（完整结构）"""
        config = cls._get_config()
        return config.get('status_mapping', DEFAULT_STATUS_MAPPING)

    @classmethod
    def get_status_mapping_simple(cls) -> dict:
        """获取简化的订单状态映射表（仅原始状态 -> 映射值）"""
        full_mapping = cls.get_status_mapping()
        simple_mapping = {}
        for orig, value in full_mapping.items():
            if isinstance(value, dict):
                simple_mapping[orig] = value.get('mapped', '')
            else:
                # 兼容旧格式
                simple_mapping[orig] = value
        return simple_mapping

    @classmethod
    def get_prompt(cls) -> str:
        """获取系统提示词"""
        config = cls._get_config()
        return config.get('prompt', '')

    @classmethod
    def build(cls, buyer_name: str = "", product_info: dict = None, order_status: str = "") -> dict:
        """
        构建传递给 Coze 工作流的变量字典

        Args:
            buyer_name: 买家用户名
            product_info: 商品信息字典，包含 title, price, order_status 等字段
            order_status: 订单状态（如未在product_info中提供，可单独传入）

        Returns:
            dict: 可直接传递给 Coze API 的变量字典

        Example:
            custom_vars = CozeVars.build(
                buyer_name="张三",
                product_info={"title": "iPhone 15", "price": "5999", "order_status": "交易成功"}
            )
        """
        variables = {}

        # 买家信息
        if buyer_name and cls.is_var_enabled('buyer_name'):
            var_name = cls.get_var_name('buyer_name')
            variables[var_name] = buyer_name

        # 商品信息
        if product_info:
            # 优先从 product_info 获取订单状态
            if product_info.get("order_status") and cls.is_var_enabled('order_status'):
                var_name = cls.get_var_name('order_status')
                variables[var_name] = product_info.get("order_status", "")
            # 商品备注信息（包含标题、价格等完整信息）
            if product_info.get("notes") and cls.is_var_enabled('product_info'):
                var_name = cls.get_var_name('product_info')
                variables[var_name] = product_info.get("notes", "")

        # 如果单独传入了 order_status，覆盖 product_info 中的值
        if order_status and cls.is_var_enabled('order_status'):
            var_name = cls.get_var_name('order_status')
            variables[var_name] = order_status

        # 添加系统提示词
        prompt = cls.get_prompt()
        if prompt:
            variables['prompt'] = prompt

        return variables


class Config:
    """系统配置"""

    # Coze API 配置
    COZE_API_TOKEN: str = os.getenv("COZE_API_TOKEN", "")
    COZE_BOT_ID: str = os.getenv("COZE_BOT_ID", "")
    COZE_API_BASE: str = "https://api.coze.cn"  # 国内版使用 coze.cn，海外版使用 coze.com

    # 闲鱼配置
    XIANYU_CHECK_INTERVAL: int = int(os.getenv("XIANYU_CHECK_INTERVAL", "10"))

    # 重复消息过滤配置
    SKIP_DUPLICATE_MSG: bool = os.getenv("SKIP_DUPLICATE_MSG", "true").lower() == "true"
    MSG_EXPIRE_SECONDS: int = int(os.getenv("MSG_EXPIRE_SECONDS", "60"))

    XIANYU_URL: str = "https://www.goofish.com/im"  # 闲鱼网页版消息页面

    # Inactive 主动发消息配置
    INACTIVE_ENABLED: bool = os.getenv("INACTIVE_ENABLED", "true").lower() == "true"  # 是否启用主动发消息
    INACTIVE_TIMEOUT_MINUTES: int = int(os.getenv("INACTIVE_TIMEOUT_MINUTES", "3"))  # 超时时间（分钟）
    INACTIVE_MESSAGE: str = os.getenv("INACTIVE_MESSAGE", "[inactive]")  # 发送给Coze的触发消息
    INACTIVE_SKIP_RESPONSE: str = os.getenv("INACTIVE_SKIP_RESPONSE", "[inact_skip]")  # Coze跳过发送的回复

    # 新会话回忆配置（跨商品上下文传递）
    MEMORY_ENABLED: bool = os.getenv("MEMORY_ENABLED", "true").lower() == "true"  # 是否启用新会话回忆
    MEMORY_CONTEXT_ROUNDS: int = int(os.getenv("MEMORY_CONTEXT_ROUNDS", "5"))  # 获取历史对话轮数

    # 消息合并配置（防止用户分段发送导致AI回复混乱）
    MESSAGE_MERGE_ENABLED: bool = os.getenv("MESSAGE_MERGE_ENABLED", "true").lower() == "true"  # 是否启用消息合并
    MESSAGE_MERGE_WAIT_SECONDS: float = float(os.getenv("MESSAGE_MERGE_WAIT_SECONDS", "3"))  # 等待合并的时间窗口（秒）
    MESSAGE_MERGE_MIN_LENGTH: int = int(os.getenv("MESSAGE_MERGE_MIN_LENGTH", "5"))  # 低于此长度的消息触发等待

    # 会话切换延迟配置（防止页面切换过快导致元素找不到）
    CONVERSATION_ENTER_DELAY: float = float(os.getenv("CONVERSATION_ENTER_DELAY", "1.5"))  # 进入会话后等待时间（秒）

    # 浏览器配置
    HEADLESS: bool = os.getenv("HEADLESS", "false").lower() == "true"
    USER_DATA_DIR: str = str(Path(__file__).parent / "browser_data")  # 浏览器数据目录，用于保持登录状态

    # MySQL数据库配置
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: str = os.getenv("DB_PORT", "3306")
    db_user: str = os.getenv("DB_USER", "root")
    db_password: str = os.getenv("DB_PASSWORD", "root")
    db_name: str = os.getenv("DB_NAME", "xianyu")

    @classmethod
    def validate(cls) -> bool:
        """验证必要配置是否完整"""
        if not cls.COZE_API_TOKEN:
            print("错误: 请设置 COZE_API_TOKEN")
            return False
        if not cls.COZE_BOT_ID:
            print("错误: 请设置 COZE_BOT_ID")
            return False
        return True
