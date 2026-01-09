import pymysql
import json
from datetime import datetime, timedelta
from config import Config
from logger_setup import logger

class DBManager:
    def __init__(self):
        self.config = Config()
        self.connection = None

    def connect(self):
        """连接数据库"""
        try:
            self.connection = pymysql.connect(
                host=self.config.db_host,
                port=int(self.config.db_port),
                user=self.config.db_user,
                password=self.config.db_password,
                database=self.config.db_name,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            logger.info("数据库连接成功")
            return True
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            return False

    def close(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            logger.info("数据库连接已关闭")

    def _ensure_connection(self):
        """确保数据库连接有效，断开则重连"""
        try:
            self.connection.ping(reconnect=True)
        except Exception as e:
            logger.warning(f"数据库连接断开，尝试重连: {e}")
            self.connect()

    def init_tables(self):
        """初始化数据表"""
        try:
            with self.connection.cursor() as cursor:
                # 创建用户表（包含白名单标记）
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        buyer_name VARCHAR(255) NOT NULL UNIQUE,
                        coze_conversation_id VARCHAR(255),
                        is_whitelist TINYINT(1) DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

                # 检查并添加 is_whitelist 列（兼容旧表）
                cursor.execute("""
                    SELECT COUNT(*) as cnt FROM information_schema.columns
                    WHERE table_schema = DATABASE()
                    AND table_name = 'users' AND column_name = 'is_whitelist'
                """)
                if cursor.fetchone()['cnt'] == 0:
                    cursor.execute("ALTER TABLE users ADD COLUMN is_whitelist TINYINT(1) DEFAULT 0")
                    logger.info("已添加 is_whitelist 列到 users 表")

                # 创建对话历史表（包含buyer_name方便直接查看）
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_history (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        buyer_name VARCHAR(255) NOT NULL,
                        role VARCHAR(50) NOT NULL,
                        content TEXT NOT NULL,
                        coze_conversation_id VARCHAR(255),
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

                # 创建用户会话表（新表：基于用户ID和商品ID）
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_sessions (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id VARCHAR(50) NOT NULL COMMENT '闲鱼用户唯一ID',
                        item_id VARCHAR(50) NOT NULL COMMENT '商品ID',
                        buyer_name VARCHAR(255) COMMENT '买家昵称',
                        conversation_id VARCHAR(255) COMMENT 'Coze会话ID',
                        summary TEXT COMMENT '会话摘要',
                        inactive_sent TINYINT(1) DEFAULT 0 COMMENT '是否已发送过inactive',
                        customer_type VARCHAR(20) DEFAULT 'new' COMMENT '客户类型: new/returning',
                        order_status VARCHAR(50) COMMENT '订单状态',
                        last_message_at DATETIME COMMENT '最后消息时间',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        UNIQUE KEY unique_user_item (user_id, item_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)

            self.connection.commit()
            logger.info("数据表初始化成功")
            return True
        except Exception as e:
            logger.error(f"数据表初始化失败: {e}")
            return False

    def get_or_create_user(self, buyer_name):
        """获取或创建用户"""
        try:
            with self.connection.cursor() as cursor:
                # 先查找用户
                cursor.execute(
                    "SELECT * FROM users WHERE buyer_name = %s",
                    (buyer_name,)
                )
                user = cursor.fetchone()

                if user:
                    return user

                # 创建新用户
                cursor.execute(
                    "INSERT INTO users (buyer_name) VALUES (%s)",
                    (buyer_name,)
                )
                self.connection.commit()

                # 获取新创建的用户
                cursor.execute(
                    "SELECT * FROM users WHERE buyer_name = %s",
                    (buyer_name,)
                )
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"获取/创建用户失败: {e}")
            return None

    def update_conversation_id(self, buyer_name, conversation_id):
        """更新用户的Coze conversation_id（如果用户不存在则创建）"""
        try:
            # 先确保用户存在
            self.get_or_create_user(buyer_name)

            with self.connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET coze_conversation_id = %s WHERE buyer_name = %s",
                    (conversation_id, buyer_name)
                )
            self.connection.commit()
            logger.info(f"更新用户 {buyer_name} 的conversation_id: {conversation_id}")
            return True
        except Exception as e:
            logger.error(f"更新conversation_id失败: {e}")
            return False

    def clear_conversation_id(self, buyer_name):
        """清除用户的conversation_id并清空对话历史（用于会话轮换）"""
        try:
            with self.connection.cursor() as cursor:
                # 清除 conversation_id
                cursor.execute(
                    "UPDATE users SET coze_conversation_id = NULL WHERE buyer_name = %s",
                    (buyer_name,)
                )
                # 清空该用户的对话历史
                cursor.execute(
                    "DELETE FROM conversation_history WHERE buyer_name = %s",
                    (buyer_name,)
                )
            self.connection.commit()
            logger.info(f"已清除用户 {buyer_name} 的会话ID和对话历史")
            return True
        except Exception as e:
            logger.error(f"清除conversation_id失败: {e}")
            return False

    def get_conversation_id(self, buyer_name):
        """获取用户的Coze conversation_id"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT coze_conversation_id FROM users WHERE buyer_name = %s",
                    (buyer_name,)
                )
                result = cursor.fetchone()
                if result and result['coze_conversation_id']:
                    return result['coze_conversation_id']
                return None
        except Exception as e:
            logger.error(f"获取conversation_id失败: {e}")
            return None

    def add_message(self, buyer_name, role, content, conversation_id=None):
        """添加对话消息"""
        try:
            # 确保用户存在
            self.get_or_create_user(buyer_name)

            # 如果没传conversation_id，从用户表获取
            if not conversation_id:
                conversation_id = self.get_conversation_id(buyer_name)

            with self.connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO conversation_history (buyer_name, role, content, coze_conversation_id) VALUES (%s, %s, %s, %s)",
                    (buyer_name, role, content, conversation_id)
                )
            self.connection.commit()
            logger.debug(f"保存消息 - 用户:{buyer_name}, 角色:{role}, 会话ID:{conversation_id}")
            return True
        except Exception as e:
            logger.error(f"添加消息失败: {e}")
            return False

    def get_conversation_history(self, buyer_name, limit=10):
        """获取用户的对话历史"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT role, content, coze_conversation_id, created_at
                    FROM conversation_history
                    WHERE buyer_name = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (buyer_name, limit)
                )
                messages = cursor.fetchall()
                # 反转顺序，让最早的消息在前面
                return list(reversed(messages))
        except Exception as e:
            logger.error(f"获取对话历史失败: {e}")
            return []

    def get_conversation_count(self, buyer_name):
        """获取用户的对话轮数"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) as count FROM conversation_history WHERE buyer_name = %s",
                    (buyer_name,)
                )
                result = cursor.fetchone()
                return result['count'] if result else 0
        except Exception as e:
            logger.error(f"获取对话轮数失败: {e}")
            return 0

    def is_user_in_whitelist(self, buyer_name: str) -> bool:
        """检查用户是否在白名单中"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT is_whitelist FROM users WHERE buyer_name = %s",
                    (buyer_name,)
                )
                result = cursor.fetchone()
                if result:
                    return bool(result.get('is_whitelist', 0))
                return False
        except Exception as e:
            logger.error(f"检查白名单状态失败: {e}")
            return False

    def set_user_whitelist(self, buyer_name: str, is_whitelist: bool) -> bool:
        """设置用户的白名单状态"""
        try:
            # 确保用户存在
            self.get_or_create_user(buyer_name)

            with self.connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET is_whitelist = %s WHERE buyer_name = %s",
                    (1 if is_whitelist else 0, buyer_name)
                )
            self.connection.commit()
            status = "加入" if is_whitelist else "移出"
            logger.info(f"用户 {buyer_name} 已{status}白名单")
            return True
        except Exception as e:
            logger.error(f"设置白名单状态失败: {e}")
            return False

    def get_whitelist_users(self) -> list:
        """获取所有白名单用户"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT buyer_name FROM users WHERE is_whitelist = 1 ORDER BY updated_at DESC"
                )
                results = cursor.fetchall()
                return [r['buyer_name'] for r in results]
        except Exception as e:
            logger.error(f"获取白名单用户列表失败: {e}")
            return []

    def get_all_users_with_status(self) -> list:
        """获取所有用户及其状态（用于GUI显示）"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT u.buyer_name, u.coze_conversation_id, u.is_whitelist,
                           (SELECT COUNT(*) FROM conversation_history ch WHERE ch.buyer_name = u.buyer_name) as msg_count,
                           u.updated_at
                    FROM users u
                    ORDER BY u.updated_at DESC
                """)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取用户列表失败: {e}")
            return []

    # ========== user_sessions 表操作方法 ==========

    def get_or_create_session(self, user_id: str, item_id: str, buyer_name: str = None, order_status: str = None) -> dict:
        """获取或创建用户会话"""
        try:
            with self.connection.cursor() as cursor:
                # 先查找会话
                cursor.execute(
                    "SELECT * FROM user_sessions WHERE user_id = %s AND item_id = %s",
                    (user_id, item_id)
                )
                session = cursor.fetchone()

                if session:
                    # 更新最后消息时间
                    cursor.execute(
                        "UPDATE user_sessions SET last_message_at = NOW() WHERE user_id = %s AND item_id = %s",
                        (user_id, item_id)
                    )
                    self.connection.commit()
                    return session

                # 检查该用户是否有其他会话（判断新老客户 + 继承inactive状态）
                cursor.execute(
                    "SELECT COUNT(*) as cnt, MAX(inactive_sent) as inactive_sent FROM user_sessions WHERE user_id = %s",
                    (user_id,)
                )
                result = cursor.fetchone()
                has_other_sessions = result['cnt'] > 0
                customer_type = 'returning' if has_other_sessions else 'new'
                # 继承用户已有的inactive_sent状态
                inherit_inactive_sent = 1 if result['inactive_sent'] else 0

                # 创建新会话
                cursor.execute(
                    """INSERT INTO user_sessions
                       (user_id, item_id, buyer_name, customer_type, order_status, last_message_at, inactive_sent)
                       VALUES (%s, %s, %s, %s, %s, NOW(), %s)""",
                    (user_id, item_id, buyer_name, customer_type, order_status, inherit_inactive_sent)
                )
                self.connection.commit()

                # 获取新创建的会话
                cursor.execute(
                    "SELECT * FROM user_sessions WHERE user_id = %s AND item_id = %s",
                    (user_id, item_id)
                )
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"获取/创建会话失败: {e}")
            return None

    def update_session_conversation_id(self, user_id: str, item_id: str, conversation_id: str) -> bool:
        """更新会话的Coze conversation_id"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE user_sessions SET conversation_id = %s WHERE user_id = %s AND item_id = %s",
                    (conversation_id, user_id, item_id)
                )
            self.connection.commit()
            logger.info(f"更新会话 conversation_id: user={user_id}, item={item_id}, conv={conversation_id}")
            return True
        except Exception as e:
            logger.error(f"更新会话conversation_id失败: {e}")
            return False

    def update_session_message_time(self, user_id: str, item_id: str) -> bool:
        """更新会话的最后消息时间"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE user_sessions SET last_message_at = NOW() WHERE user_id = %s AND item_id = %s",
                    (user_id, item_id)
                )
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"更新最后消息时间失败: {e}")
            return False

    def update_session_order_status(self, user_id: str, item_id: str, order_status: str) -> bool:
        """更新会话的订单状态"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE user_sessions SET order_status = %s WHERE user_id = %s AND item_id = %s",
                    (order_status, user_id, item_id)
                )
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"更新订单状态失败: {e}")
            return False

    def set_inactive_sent(self, user_id: str, sent: bool = True) -> bool:
        """设置用户的inactive发送状态（针对用户的所有会话）"""
        try:
            self._ensure_connection()
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE user_sessions SET inactive_sent = %s WHERE user_id = %s",
                    (1 if sent else 0, user_id)
                )
            self.connection.commit()
            logger.info(f"用户 {user_id} inactive_sent 设置为 {sent}")
            return True
        except Exception as e:
            logger.error(f"设置inactive状态失败: {e}")
            return False

    def is_inactive_sent(self, user_id: str) -> bool:
        """检查用户是否已发送过inactive"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT inactive_sent FROM user_sessions WHERE user_id = %s LIMIT 1",
                    (user_id,)
                )
                result = cursor.fetchone()
                if result:
                    return bool(result.get('inactive_sent', 0))
                return False
        except Exception as e:
            logger.error(f"检查inactive状态失败: {e}")
            return False

    def get_user_last_message_time(self, user_id: str) -> datetime:
        """获取用户所有会话中的最后消息时间"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT MAX(last_message_at) as last_time FROM user_sessions WHERE user_id = %s",
                    (user_id,)
                )
                result = cursor.fetchone()
                if result and result['last_time']:
                    return result['last_time']
                return None
        except Exception as e:
            logger.error(f"获取最后消息时间失败: {e}")
            return None

    def get_inactive_candidates(self, timeout_minutes: int = 3) -> list:
        """获取需要发送inactive的用户列表

        条件：
        1. 最后消息时间超过指定分钟数
        2. 未发送过inactive
        3. 订单状态不是已付款相关状态
        """
        try:
            paid_statuses = ['paid', '已付款', '待发货', '已发货', '交易成功']
            paid_status_str = ','.join([f"'{s}'" for s in paid_statuses])

            with self.connection.cursor() as cursor:
                cursor.execute(f"""
                    SELECT user_id, MAX(last_message_at) as last_time,
                           MAX(buyer_name) as buyer_name,
                           GROUP_CONCAT(DISTINCT item_id) as item_ids,
                           GROUP_CONCAT(DISTINCT conversation_id) as conversation_ids
                    FROM user_sessions
                    WHERE inactive_sent = 0
                      AND (order_status IS NULL OR order_status NOT IN ({paid_status_str}))
                      AND last_message_at IS NOT NULL
                      AND last_message_at < DATE_SUB(NOW(), INTERVAL %s MINUTE)
                    GROUP BY user_id
                """, (timeout_minutes,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取inactive候选用户失败: {e}")
            return []

    def get_user_sessions(self, user_id: str) -> list:
        """获取用户的所有会话"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM user_sessions WHERE user_id = %s ORDER BY updated_at DESC",
                    (user_id,)
                )
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取用户会话列表失败: {e}")
            return []

    def get_user_other_sessions(self, user_id: str, exclude_item_id: str) -> list:
        """获取用户的其他会话（排除指定商品）"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM user_sessions WHERE user_id = %s AND item_id != %s ORDER BY updated_at DESC",
                    (user_id, exclude_item_id)
                )
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取用户其他会话失败: {e}")
            return []

    def update_session_summary(self, user_id: str, item_id: str, summary: str) -> bool:
        """更新会话摘要"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE user_sessions SET summary = %s WHERE user_id = %s AND item_id = %s",
                    (summary, user_id, item_id)
                )
            self.connection.commit()
            logger.info(f"更新会话摘要: user={user_id}, item={item_id}")
            return True
        except Exception as e:
            logger.error(f"更新会话摘要失败: {e}")
            return False

    def get_all_sessions_with_status(self) -> list:
        """获取所有会话及其状态（用于GUI显示）"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT user_id, item_id, buyer_name, conversation_id,
                           customer_type, order_status, inactive_sent,
                           last_message_at, updated_at
                    FROM user_sessions
                    ORDER BY updated_at DESC
                """)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取会话列表失败: {e}")
            return []

    def reset_user_inactive_status(self, user_id: str) -> bool:
        """重置用户的inactive状态（当用户有新消息时调用）"""
        try:
            self._ensure_connection()
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE user_sessions SET inactive_sent = 0 WHERE user_id = %s",
                    (user_id,)
                )
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"重置inactive状态失败: {e}")
            return False

    def update_session_buyer_name(self, user_id: str, buyer_name: str) -> bool:
        """更新用户所有会话的buyer_name（用于修正错误的名字）"""
        try:
            self._ensure_connection()
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE user_sessions SET buyer_name = %s WHERE user_id = %s",
                    (buyer_name, user_id)
                )
            self.connection.commit()
            logger.info(f"更新用户 {user_id} 的 buyer_name: {buyer_name}")
            return True
        except Exception as e:
            logger.error(f"更新buyer_name失败: {e}")
            return False


# 全局数据库管理器实例
db_manager = DBManager()
