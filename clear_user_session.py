"""清除指定用户的会话历史（用于解决AI回复被历史污染的问题）"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from db_manager import db_manager


def clear_user_session(buyer_name: str):
    """清除指定用户的会话ID和对话历史"""
    print(f"正在清除用户 [{buyer_name}] 的会话...")

    if not db_manager.connect():
        print("❌ 数据库连接失败")
        return False

    try:
        # 先查看当前状态
        with db_manager.connection.cursor() as cursor:
            cursor.execute(
                "SELECT coze_conversation_id FROM users WHERE buyer_name = %s",
                (buyer_name,)
            )
            result = cursor.fetchone()
            if result:
                print(f"当前会话ID: {result.get('coze_conversation_id', '无')}")
            else:
                print(f"用户 [{buyer_name}] 不存在")
                return False

            # 查看对话历史数量
            cursor.execute(
                "SELECT COUNT(*) as count FROM conversation_history WHERE buyer_name = %s",
                (buyer_name,)
            )
            count_result = cursor.fetchone()
            print(f"对话历史条数: {count_result.get('count', 0)}")

        # 清除会话ID和对话历史
        success = db_manager.clear_conversation_id(buyer_name)

        if success:
            print(f"✅ 已清除用户 [{buyer_name}] 的会话ID和对话历史")
            print("下次该用户发消息时，将创建全新的会话")
        else:
            print("❌ 清除失败")

        return success

    finally:
        db_manager.close()


def clear_all_sessions():
    """清除所有用户的会话（谨慎使用）"""
    print("正在清除所有用户的会话...")

    if not db_manager.connect():
        print("❌ 数据库连接失败")
        return False

    try:
        with db_manager.connection.cursor() as cursor:
            # 清除所有 conversation_id
            cursor.execute("UPDATE users SET coze_conversation_id = NULL")
            # 清除所有对话历史
            cursor.execute("DELETE FROM conversation_history")

        db_manager.connection.commit()
        print("✅ 已清除所有用户的会话ID和对话历史")
        return True

    except Exception as e:
        print(f"❌ 清除失败: {e}")
        return False
    finally:
        db_manager.close()


def list_users():
    """列出所有用户及其会话状态"""
    if not db_manager.connect():
        print("❌ 数据库连接失败")
        return

    try:
        with db_manager.connection.cursor() as cursor:
            cursor.execute("""
                SELECT u.buyer_name, u.coze_conversation_id,
                       (SELECT COUNT(*) FROM conversation_history ch WHERE ch.buyer_name = u.buyer_name) as msg_count
                FROM users u
                ORDER BY u.updated_at DESC
            """)
            users = cursor.fetchall()

            if not users:
                print("没有用户记录")
                return

            print(f"\n{'用户名':<20} {'会话ID':<40} {'消息数':<10}")
            print("-" * 70)
            for user in users:
                name = user['buyer_name'][:18] if user['buyer_name'] else '未知'
                conv_id = (user['coze_conversation_id'] or '无')[:38]
                msg_count = user['msg_count'] or 0
                print(f"{name:<20} {conv_id:<40} {msg_count:<10}")
    finally:
        db_manager.close()


if __name__ == "__main__":
    print("=" * 60)
    print("用户会话管理工具")
    print("=" * 60)

    if len(sys.argv) < 2:
        print("\n用法:")
        print("  python clear_user_session.py list              - 列出所有用户")
        print("  python clear_user_session.py clear <用户名>    - 清除指定用户的会话")
        print("  python clear_user_session.py clear_all         - 清除所有用户的会话")
        print("\n示例:")
        print("  python clear_user_session.py clear 敌法师爱码")
        sys.exit(0)

    command = sys.argv[1]

    if command == "list":
        list_users()
    elif command == "clear" and len(sys.argv) >= 3:
        buyer_name = sys.argv[2]
        clear_user_session(buyer_name)
    elif command == "clear_all":
        confirm = input("确定要清除所有用户的会话吗？(y/n): ")
        if confirm.lower() == 'y':
            clear_all_sessions()
        else:
            print("已取消")
    else:
        print("未知命令，请使用 list / clear / clear_all")
