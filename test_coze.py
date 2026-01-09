"""测试 Coze API 调用 - 清除会话后测试"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from coze_client import CozeClient
from db_manager import db_manager
from loguru import logger

# 配置日志输出到控制台
logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")


async def test_new_conversation():
    """测试新会话（无历史记录）"""
    buyer_name = "敌法师爱码"

    # 1. 连接数据库并清除该用户的 conversation_id
    print("=" * 50)
    print(f"Step 1: Clear conversation ID for {buyer_name}")
    print("=" * 50)

    if db_manager.connect():
        # 清除 conversation_id
        try:
            with db_manager.connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET coze_conversation_id = NULL WHERE buyer_name = %s",
                    (buyer_name,)
                )
            db_manager.connection.commit()
            print(f"[OK] Cleared conversation ID for {buyer_name}")
        except Exception as e:
            print(f"[FAIL] Clear failed: {e}")
    else:
        print("[FAIL] Database connection failed")

    # 2. 创建 Coze 客户端并发送测试消息
    print("\n" + "=" * 50)
    print("Step 2: Send test message (new conversation)")
    print("=" * 50)

    client = CozeClient()

    # 测试消息1
    test_message = "你好"
    custom_vars = {
        "buyer_name": buyer_name,
        "order_status": "已完成"
    }

    print(f"Message 1: {test_message}")
    print(f"Variables: {custom_vars}")
    print("-" * 50)

    reply1, conv_id = await client.chat(
        user_message=test_message,
        user_id=buyer_name,
        conversation_id=None,
        custom_variables=custom_vars
    )

    print(f"\n>>> AI Reply 1: {reply1}")
    print(f">>> Conversation ID: {conv_id}")

    # 测试消息2 - 使用刚获得的 conv_id 继续对话
    print("\n" + "=" * 50)
    print("Step 3: Send second message (continue conversation)")
    print("=" * 50)

    test_message2 = "这个商品还在吗"
    print(f"Message 2: {test_message2}")
    print(f"Using conversation ID: {conv_id}")
    print("-" * 50)

    reply2, conv_id2 = await client.chat(
        user_message=test_message2,
        user_id=buyer_name,
        conversation_id=conv_id,
        custom_variables=custom_vars
    )

    print(f"\n>>> AI Reply 2: {reply2}")

    # 测试消息3 - 直接问订单状态
    print("\n" + "=" * 50)
    print("Step 4: Ask about order status")
    print("=" * 50)

    test_message3 = "我的订单发货了吗"
    print(f"Message 3: {test_message3}")
    print("-" * 50)

    reply3, conv_id3 = await client.chat(
        user_message=test_message3,
        user_id=buyer_name,
        conversation_id=conv_id,
        custom_variables=custom_vars
    )

    print(f"\n>>> AI Reply 3: {reply3}")

    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    print(f"Q1: 'ni hao' -> {reply1[:50]}...")
    print(f"Q2: 'shang pin hai zai ma' -> {reply2[:50]}...")
    print(f"Q3: 'ding dan fa huo le ma' -> {reply3[:50]}...")

    # 关闭数据库连接
    db_manager.close()

    return reply1


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Coze 对话流测试 - 验证新会话行为")
    print("=" * 60 + "\n")

    asyncio.run(test_new_conversation())
