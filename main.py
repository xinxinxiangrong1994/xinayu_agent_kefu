"""
闲鱼智能客服 RPA 工具
基于 Playwright 浏览器自动化 + Coze AI 智能体
"""
import asyncio
import argparse
import signal
import sys
from loguru import logger
from logger_setup import setup_logger
from config import Config
from message_handler import MessageHandler, ManualMessageHandler


# 全局处理器引用，用于优雅退出
handler = None


def signal_handler(sig, frame):
    """处理退出信号"""
    logger.info("收到退出信号，正在停止...")
    if handler:
        asyncio.create_task(handler.stop())
    sys.exit(0)


async def main(mode: str = "auto"):
    """主函数"""
    global handler

    # 设置日志
    setup_logger()

    logger.info("=" * 50)
    logger.info("闲鱼智能客服 RPA 工具")
    logger.info("=" * 50)

    # 验证配置
    if not Config.validate():
        logger.error("配置验证失败，请检查 .env 文件")
        return

    logger.info(f"运行模式: {'自动回复' if mode == 'auto' else '手动确认'}")
    logger.info(f"检查间隔: {Config.XIANYU_CHECK_INTERVAL} 秒")

    # 创建消息处理器
    if mode == "manual":
        handler = ManualMessageHandler()
    else:
        handler = MessageHandler()

    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await handler.start()
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error(f"程序出错: {e}")
    finally:
        await handler.stop()


def run():
    """运行入口"""
    parser = argparse.ArgumentParser(description="闲鱼智能客服 RPA 工具")
    parser.add_argument(
        "--mode",
        choices=["auto", "manual"],
        default="auto",
        help="运行模式: auto(自动回复) 或 manual(手动确认)",
    )
    args = parser.parse_args()

    asyncio.run(main(args.mode))


if __name__ == "__main__":
    run()
