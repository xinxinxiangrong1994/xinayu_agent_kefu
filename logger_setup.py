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
        callback: 回调函数，签名为 (msg_type, username, content, order_status, level)
    """
    global _gui_conversation_callback
    _gui_conversation_callback = callback


def setup_logger():
    """配置日志系统"""
    # 创建日志目录
    log_dir = Path("./logs")
    log_dir.mkdir(exist_ok=True)

    # 移除默认处理器
    logger.remove()

    # 添加控制台输出
    logger.add(
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


def log_conversation(buyer_id: str, buyer_msg: str, bot_reply: str,
                     product_info: str = "", order_status: str = ""):
    """记录对话日志"""
    conversation_logger = logger.bind(conversation=True)
    conversation_logger.info(
        f"买家ID: {buyer_id} | 商品: {product_info} | 买家: {buyer_msg} | 回复: {bot_reply}"
    )

    # 调用GUI回调（如果已注册）
    if _gui_conversation_callback:
        try:
            # 记录用户消息
            _gui_conversation_callback("user", buyer_id, buyer_msg, order_status, "INFO")
            # 记录AI回复
            _gui_conversation_callback("AI", buyer_id, bot_reply, order_status, "INFO")
        except Exception as e:
            logger.debug(f"GUI回调失败: {e}")
