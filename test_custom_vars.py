"""测试 custom_variables 传递"""
import asyncio
import sys
import io
from pathlib import Path

# Fix encoding for Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from coze_client import CozeClient


async def test_custom_vars():
    client = CozeClient()

    print("=" * 50)
    print("测试 custom_variables 传递")
    print("=" * 50)

    # 创建会话
    print("\n[Step 1] 创建会话...")
    conv_id = await client.create_conversation("test_user")

    if not conv_id:
        print("[FAIL] 创建会话失败!")
        return

    print(f"[OK] 会话已创建: {conv_id}")

    # 测试传递 custom_variables
    print("\n[Step 2] 发送消息并传递 custom_variables...")

    custom_vars = {
        "buyer_name": "测试买家张三",
        "product_title": "iPhone 15 Pro Max",
        "product_price": "8999"
    }

    print(f"传递的变量: {custom_vars}")

    # 发送一条测试消息，让 bot 回复时使用这些变量
    reply, returned_id = await client.chat(
        user_message="你好，请告诉我你知道我的名字吗？商品是什么？",
        user_id="test_user",
        conversation_id=conv_id,
        custom_variables=custom_vars
    )

    print(f"\nAI 回复: {reply}")

    # 检查回复中是否包含我们传递的变量值
    print("\n" + "=" * 50)
    print("检查结果:")

    if "张三" in reply or "测试买家" in reply:
        print("[OK] 买家名称传递成功!")
    else:
        print("[WARN] 回复中未发现买家名称")

    if "iPhone" in reply or "15" in reply or "Pro" in reply:
        print("[OK] 商品名称传递成功!")
    else:
        print("[WARN] 回复中未发现商品名称")

    if "8999" in reply:
        print("[OK] 商品价格传递成功!")
    else:
        print("[WARN] 回复中未发现商品价格")

    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(test_custom_vars())
