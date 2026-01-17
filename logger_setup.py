"""日志配置模块"""
import sys
from loguru import logger
from pathlib import Path
from typing import Callable, Optional

# 全局GUI回调函数（用于将对话记录发送到GUI表格）
_gui_conversation_callback: Optional[Callable] = None


def set_gui_conversation_callback(callback: Optional[Callable]):
    """
    设置GUI对话记录回调函数

    Args:
        callback: 回调函数，签名为 (msg_type, username, content, conv_id, order_status, level, timestamp)
    """
    global _gui_conversation_callback
    _gui_conversation_callback = callback


_console_handler_id = None  # 保存控制台handler的ID


def setup_logger():
    """配置日志系统"""
    global _console_handler_id

    # 创建日志目录
    log_dir = Path("./logs")
    log_dir.mkdir(exist_ok=True)

    # 移除默认处理器
    logger.remove()

    # 添加控制台输出
    _console_handler_id = logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True,
    )

    # 添加文件输出 - 所有日志
    logger.add(
        log_dir / "app_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="00:00",  # 每天轮转
        retention="30 days",  # 保留30天
        encoding="utf-8",
    )

    # 添加对话记录文件
    logger.add(
        log_dir / "conversations_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {message}",
        level="INFO",
        rotation="00:00",
        retention="90 days",
        encoding="utf-8",
        filter=lambda record: record["extra"].get("conversation", False),
    )

    return logger


def rebind_console_output():
    """重新绑定控制台输出（用于动态创建控制台后）"""
    global _console_handler_id

    # 移除旧的控制台handler
    if _console_handler_id is not None:
        try:
            logger.remove(_console_handler_id)
        except Exception:
            pass

    # 添加新的控制台handler（绑定到新的sys.stdout，禁用颜色避免乱码）
    _console_handler_id = logger.add(
        sys.stdout,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="INFO",
        colorize=False,
    )
    logger.info("控制台日志输出已重新绑定")


def log_conversation(buyer_id: str, buyer_msg: str, bot_reply: str,
                     product_info: str = "", order_status: str = "",
                     conversation_id: str = "", user_msg_time: str = None):
    """记录对话日志（用户-AI对话）

    Args:
        user_msg_time: 用户消息的时间戳（格式 HH:MM:SS），如不传则使用当前时间
    """
    import datetime
    conversation_logger = logger.bind(conversation=True)
    conversation_logger.info(
        f"买家ID: {buyer_id} | 商品: {product_info} | 买家: {buyer_msg} | 回复: {bot_reply}"
    )

    # 调用GUI回调（如果已注册）
    if _gui_conversation_callback:
        try:
            # 用户消息时间：使用传入的时间或当前时间
            user_time = user_msg_time or datetime.datetime.now().strftime("%H:%M:%S")
            # AI回复时间：总是使用当前时间
            ai_time = datetime.datetime.now().strftime("%H:%M:%S")

            # 记录用户消息
            _gui_conversation_callback("user", buyer_id, buyer_msg, conversation_id, order_status, "INFO", user_time)
            # 记录AI回复
            _gui_conversation_callback("AI", buyer_id, bot_reply, conversation_id, order_status, "INFO", ai_time)
        except Exception as e:
            logger.debug(f"GUI回调失败: {e}")


def log_system_message(buyer_id: str, message: str, order_status: str = "",
                       conversation_id: str = ""):
    """记录系统主动发送的消息（如 Inactive 主动问候，没有用户消息）"""
    import datetime
    conversation_logger = logger.bind(conversation=True)
    conversation_logger.info(
        f"买家ID: {buyer_id} | [系统主动发送] | 回复: {message}"
    )

    # 调用GUI回调（如果已注册）- 只记录AI发送的消息
    if _gui_conversation_callback:
        try:
            ai_time = datetime.datetime.now().strftime("%H:%M:%S")
            _gui_conversation_callback("AI", buyer_id, message, conversation_id, order_status, "INFO", ai_time)
        except Exception as e:
            logger.debug(f"GUI回调失败: {e}")
