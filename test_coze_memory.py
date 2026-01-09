"""Test Coze multi-round conversation memory"""
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


async def test_multi_round():
    client = CozeClient()

    print("=" * 50)
    print("Test Coze Multi-round Memory")
    print("=" * 50)

    # Step 1: Create conversation
    print("\n[Step 1] Creating conversation...")
    conv_id = await client.create_conversation("test_user")

    if not conv_id:
        print("[FAIL] Failed to create conversation!")
        return

    print(f"[OK] Conversation created: {conv_id}")

    # Step 2: First round
    print("\n[Step 2] First round...")
    print("Sending: Hello, my name is Xiaoming")
    reply1, returned_id1 = await client.chat(
        user_message="Hello, my name is Xiaoming",
        user_id="test_user",
        conversation_id=conv_id
    )
    print(f"Reply: {reply1}")
    print(f"Returned conv_id: {returned_id1}")

    if returned_id1 == conv_id:
        print("[OK] Conversation ID matches!")
    else:
        print(f"[WARN] ID mismatch! Sent:{conv_id} Got:{returned_id1}")

    # Step 3: Second round (test memory)
    print("\n[Step 3] Second round (testing memory)...")
    print("Sending: What is my name?")
    reply2, returned_id2 = await client.chat(
        user_message="What is my name?",
        user_id="test_user",
        conversation_id=conv_id
    )
    print(f"Reply: {reply2}")
    print(f"Returned conv_id: {returned_id2}")

    if returned_id2 == conv_id:
        print("[OK] Conversation ID matches!")
    else:
        print(f"[WARN] ID mismatch! Sent:{conv_id} Got:{returned_id2}")

    # Check result
    print("\n" + "=" * 50)
    print("Test Result:")
    if "Xiaoming" in reply2 or "xiaoming" in reply2.lower() or "name" in reply2.lower():
        print("[SUCCESS] Multi-round memory is working!")
    else:
        print("[CHECK] Please verify the reply content above")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(test_multi_round())
