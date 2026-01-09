"""消息处理模块 - 监控和自动回复逻辑"""
import asyncio
from typing import Dict, Optional
from loguru import logger
import time
from xianyu_browser import XianyuBrowser
from coze_client import CozeClient
from logger_setup import log_conversation
from config import Config, CozeVars
from db_manager import db_manager


class MessageHandler:
    """消息处理器"""

    def __init__(self):
        self.browser = XianyuBrowser()
        self.coze_client = CozeClient()
        # 已处理的消息标识 -> 处理时间戳 (用于过期检测)
        self.processed_messages: Dict[str, float] = {}
        # 从配置读取重复消息过滤设置
        self.skip_duplicate_msg = Config.SKIP_DUPLICATE_MSG
        self.message_expire_seconds = Config.MSG_EXPIRE_SECONDS
        # Inactive 配置
        self.inactive_enabled = Config.INACTIVE_ENABLED
        self.inactive_timeout_minutes = Config.INACTIVE_TIMEOUT_MINUTES
        self.inactive_message = Config.INACTIVE_MESSAGE
        self.inactive_skip_response = Config.INACTIVE_SKIP_RESPONSE
        self.running = False
        # inactive 处理锁，避免与消息处理冲突
        self._inactive_lock = asyncio.Lock()
        # 每个用户的 inactive 定时器
        self._inactive_timers: Dict[str, asyncio.Task] = {}

    async def start(self):
        """启动消息处理器"""
        logger.info("启动消息处理器...")

        # 显示重复消息过滤配置
        if self.skip_duplicate_msg:
            logger.info(f"重复消息过滤: 已启用 (过期时间: {self.message_expire_seconds}秒)")
        else:
            logger.info("重复消息过滤: 已关闭")

        # 显示 Inactive 配置
        if self.inactive_enabled:
            logger.info(f"主动发消息: 已启用 (超时: {self.inactive_timeout_minutes}分钟)")
        else:
            logger.info("主动发消息: 已关闭")

        # 连接数据库
        if db_manager.connect():
            db_manager.init_tables()
            logger.info("数据库连接成功，对话记忆功能已启用")
        else:
            logger.warning("数据库连接失败，将不保存对话历史")

        # 启动浏览器
        await self.browser.start()

        # 导航到消息页面
        await self.browser.navigate_to_messages()

        # 检查登录状态
        if not await self.browser.check_login_status():
            logger.warning("未登录，请在浏览器中完成登录")
            if not await self.browser.wait_for_login():
                logger.error("登录超时，程序退出")
                await self.stop()
                return

        self.running = True
        logger.info("消息处理器已启动，开始监控新消息...")

        # 启动消息监控循环
        await self._message_loop()

    async def stop(self):
        """停止消息处理器"""
        self.running = False
        await self.browser.close()
        db_manager.close()
        logger.info("消息处理器已停止")

    async def _message_loop(self):
        """消息监控主循环"""
        while self.running:
            try:
                # 获取未读会话
                unread_conversations = await self.browser.get_unread_conversations()

                for conv in unread_conversations:
                    if not self.running:
                        break

                    # 直接处理每个未读会话
                    await self._handle_conversation(conv)

                # 清理过期的已处理标记（仅在开启重复消息过滤时执行）
                if self.skip_duplicate_msg:
                    current_time = time.time()
                    expired_keys = [
                        key for key, timestamp in self.processed_messages.items()
                        if current_time - timestamp > self.message_expire_seconds
                    ]
                    for key in expired_keys:
                        del self.processed_messages[key]

                    if expired_keys:
                        logger.debug(f"清理了 {len(expired_keys)} 条过期消息标记")

                # 等待下一次检查
                await asyncio.sleep(Config.XIANYU_CHECK_INTERVAL)

            except Exception as e:
                logger.error(f"消息循环出错: {e}")
                await asyncio.sleep(5)

    def _cancel_inactive_timer(self, user_id: str):
        """取消用户的 inactive 定时器"""
        if user_id in self._inactive_timers:
            self._inactive_timers[user_id].cancel()
            del self._inactive_timers[user_id]
            logger.debug(f"[Inactive] 取消定时器: user_id={user_id}")

    def _schedule_inactive_check(self, user_id: str, buyer_name: str, conversation_id: str):
        """为用户设置 inactive 定时检查（3分钟后触发）"""
        if not self.inactive_enabled:
            return

        # 取消旧的定时器（如果有）
        self._cancel_inactive_timer(user_id)

        # 创建新的定时任务
        async def delayed_check():
            await asyncio.sleep(self.inactive_timeout_minutes * 60)
            await self._on_inactive_timeout(user_id, buyer_name, conversation_id)

        task = asyncio.create_task(delayed_check())
        self._inactive_timers[user_id] = task
        logger.debug(f"[Inactive] 设置定时器: user_id={user_id}, {self.inactive_timeout_minutes}分钟后检查")

    async def _on_inactive_timeout(self, user_id: str, buyer_name: str, conversation_id: str):
        """定时器触发：检查并发送 inactive 消息"""
        try:
            # 从定时器列表中移除
            if user_id in self._inactive_timers:
                del self._inactive_timers[user_id]

            # 检查是否已发送过 inactive
            if db_manager.is_inactive_sent(user_id):
                logger.debug(f"[Inactive] 用户 {user_id} 已发送过 inactive，跳过")
                return

            # 检查订单状态（排除已付款用户）
            sessions = db_manager.get_user_sessions(user_id)
            for session in sessions:
                order_status = session.get('order_status', '')
                if order_status in ['paid', '已付款', '待发货', '已发货', '交易成功']:
                    logger.debug(f"[Inactive] 用户 {user_id} 订单已付款，跳过")
                    return

            logger.info(f"[Inactive] 用户 {buyer_name} (user_id={user_id}) 超时，发送主动消息")
            logger.info(f"[Inactive] 发送给Coze的消息: '{self.inactive_message}', conversation_id={conversation_id}")

            # 发送 inactive 消息给 Coze
            reply, new_conv_id = await self.coze_client.chat(
                user_message=self.inactive_message,
                user_id=buyer_name,
                conversation_id=conversation_id,
                custom_variables={
                    'buyer_name': buyer_name,
                    'user_id': user_id,
                },
            )

            logger.info(f"[Inactive] Coze 回复: {reply}")

            # 检查是否是错误消息（超时、失败等）
            error_messages = ["抱歉，", "系统", "超时", "失败", "错误"]
            is_error = any(err in reply for err in error_messages)
            if is_error:
                logger.warning(f"[Inactive] Coze 返回错误消息，跳过发送: {reply}")
                return

            # 检查是否跳过发送
            if self.inactive_skip_response in reply:
                logger.info(f"[Inactive] Coze 返回跳过标记，不发送消息给用户: {buyer_name}")
            else:
                # 发送消息给用户
                await self._send_inactive_message_to_user(user_id, buyer_name, reply)

            # 标记该用户已发送过 inactive
            db_manager.set_inactive_sent(user_id, True)

        except asyncio.CancelledError:
            # 定时器被取消（用户有新消息了）
            logger.debug(f"[Inactive] 定时器已取消: user_id={user_id}")
        except Exception as e:
            logger.error(f"[Inactive] 处理超时出错: {e}")

    async def _send_inactive_message_to_user(self, user_id: str, buyer_name: str, message: str):
        """发送 inactive 消息给用户（需要进入对应会话）"""
        async with self._inactive_lock:
            try:
                # 获取会话列表
                conversations = await self.browser.get_conversation_list()

                # 优先通过 buyer_name 快速定位（效率更高）
                target_conv = None
                for conv in conversations:
                    if conv.get('buyer_name') == buyer_name:
                        target_conv = conv
                        break

                found = False

                # 1. 先尝试通过 buyer_name 匹配的会话
                if target_conv:
                    if await self.browser.enter_conversation(target_conv):
                        conv_user_id = await self.browser.get_user_id()
                        if conv_user_id == user_id:
                            # buyer_name 和 user_id 都匹配，直接发送
                            found = True
                            await self._do_send_inactive_message(user_id, buyer_name, message)
                        await self.browser.go_back_to_list()

                # 2. 如果 buyer_name 没找到或 user_id 不匹配，再遍历查找
                if not found:
                    for conv in conversations:
                        # 跳过已经尝试过的
                        if conv == target_conv:
                            continue

                        if not await self.browser.enter_conversation(conv):
                            continue

                        conv_user_id = await self.browser.get_user_id()
                        if conv_user_id == user_id:
                            found = True
                            actual_buyer_name = conv.get('buyer_name', buyer_name)
                            await self._do_send_inactive_message(user_id, actual_buyer_name, message)
                            await self.browser.go_back_to_list()
                            break

                        await self.browser.go_back_to_list()
                        await asyncio.sleep(0.3)

                if not found:
                    logger.warning(f"[Inactive] 未找到 user_id={user_id} 的会话")

            except Exception as e:
                logger.error(f"[Inactive] 发送消息异常: {e}")
                await self.browser.go_back_to_list()

    async def _do_send_inactive_message(self, user_id: str, buyer_name: str, message: str):
        """实际发送 inactive 消息的逻辑"""
        logger.info(f"[Inactive] 找到目标用户会话: user_id={user_id}, buyer={buyer_name}")

        if await self.browser.send_message(message):
            logger.info(f"[Inactive] 已发送消息给 {buyer_name}: {message[:50]}...")
            log_conversation(
                buyer_id=buyer_name,
                buyer_msg=self.inactive_message,
                bot_reply=message,
                product_info="",
                order_status="",
            )
            db_manager.update_session_buyer_name(user_id, buyer_name)
        else:
            logger.error(f"[Inactive] 发送消息失败: {buyer_name}")

    async def _prepare_conversation(self, conversation: dict) -> Optional[dict]:
        """
        准备会话数据（公共逻辑）

        Returns:
            dict: 包含所有准备好的数据，或 None 如果应该跳过这个会话
        """
        buyer_name = conversation.get("buyer_name", "未知买家")
        conv_order_status = conversation.get("order_status", "")
        logger.info(f"处理会话: {buyer_name} (订单状态: {conv_order_status or '未知'})")

        # 进入会话
        if not await self.browser.enter_conversation(conversation):
            logger.error(f"无法进入会话: {buyer_name}")
            return None

        # 获取商品信息
        product_info = await self.browser.get_product_info()
        order_status = product_info.get("order_status") or conv_order_status

        # 获取用户唯一ID和商品ID
        user_id = await self.browser.get_user_id()
        item_id = await self.browser.get_item_id()
        logger.debug(f"获取到 user_id={user_id}, item_id={item_id}")

        # 如果无法获取 user_id，使用 buyer_name 作为替代
        if not user_id:
            logger.warning(f"无法获取用户ID，使用买家昵称: {buyer_name}")
            user_id = f"name_{buyer_name}"

        # 如果无法获取 item_id，使用 'unknown' 作为替代
        if not item_id:
            logger.debug("无法获取商品ID（可能是已完成交易），使用 unknown")
            item_id = "unknown"

        # 构建自定义变量
        custom_vars = CozeVars.build(
            buyer_name=buyer_name,
            product_info=product_info,
            order_status=order_status
        )

        # 获取消息历史
        messages = await self.browser.get_current_conversation_messages()
        if not messages:
            logger.warning(f"未获取到消息: {buyer_name}")
            await self.browser.go_back_to_list()
            return None

        # 提取买家消息
        last_buyer_message = None
        last_buyer_images = []
        for msg in reversed(messages):
            if msg.sender == "buyer" and not msg.is_system:
                last_buyer_message = msg.content
                last_buyer_images = msg.image_urls or []
                break

        if not last_buyer_message and not last_buyer_images:
            logger.info(f"没有新的买家消息（可能只有系统通知）: {buyer_name}")
            await self.browser.go_back_to_list()
            return None

        # 构建完整消息（包含图片URL）
        full_message = last_buyer_message or ""
        if last_buyer_images:
            for img_url in last_buyer_images:
                full_message = f"{full_message}\n{img_url}" if full_message else img_url
            logger.info(f"检测到 {len(last_buyer_images)} 张图片")

        logger.info(f"买家消息: {last_buyer_message}")
        if last_buyer_images:
            logger.info(f"买家发送图片: {last_buyer_images}")

        # ===== 新的会话管理系统 =====
        # 使用 user_id + item_id 来管理会话
        session = db_manager.get_or_create_session(
            user_id=user_id,
            item_id=item_id,
            buyer_name=buyer_name,
            order_status=order_status
        )

        if session:
            customer_type = session.get('customer_type', 'new')
            conversation_id = session.get('conversation_id')
            logger.info(f"[会话] 用户类型: {customer_type}, conversation_id: {conversation_id}")

            # 用户发了新消息，重置 inactive 状态并取消定时器
            db_manager.reset_user_inactive_status(user_id)
            self._cancel_inactive_timer(user_id)
        else:
            conversation_id = None
            customer_type = 'new'

        # 如果还没有 conversation_id，创建新会话
        if not conversation_id:
            logger.info(f"[会话] 为用户 {buyer_name} 创建新的 Coze 会话...")
            conversation_id = await self.coze_client.create_conversation(buyer_name)
            if conversation_id:
                db_manager.update_session_conversation_id(user_id, item_id, conversation_id)
                logger.info(f"[会话] 新会话已创建: {conversation_id}")

        # 添加客户类型到自定义变量
        custom_vars['customer_type'] = customer_type

        # 同时保持旧的 users 表兼容
        db_manager.update_conversation_id(buyer_name, conversation_id)

        return {
            'buyer_name': buyer_name,
            'user_id': user_id,
            'item_id': item_id,
            'product_info': product_info,
            'order_status': order_status,
            'custom_vars': custom_vars,
            'last_buyer_message': last_buyer_message,
            'last_buyer_images': last_buyer_images,
            'full_message': full_message,
            'conversation_id': conversation_id,
            'customer_type': customer_type,
        }

    async def _handle_conversation(self, conversation: dict):
        """处理单个会话（自动模式）"""
        try:
            # 准备数据
            data = await self._prepare_conversation(conversation)
            if not data:
                return

            buyer_name = data['buyer_name']
            user_id = data['user_id']
            item_id = data['item_id']
            full_message = data['full_message']

            # 重复消息检查（仅自动模式）
            msg_id = f"{buyer_name}:{full_message}"
            if self.skip_duplicate_msg and msg_id in self.processed_messages:
                last_processed_time = self.processed_messages[msg_id]
                time_since = time.time() - last_processed_time
                if time_since < self.message_expire_seconds:
                    logger.debug(f"消息刚处理过 ({time_since:.0f}秒前)，跳过")
                    await self.browser.go_back_to_list()
                    return

            # 调用 Coze 获取回复
            reply, new_conv_id = await self.coze_client.chat(
                user_message=full_message,
                user_id=buyer_name,
                conversation_id=data['conversation_id'],
                custom_variables=data['custom_vars'],
            )

            logger.info(f"AI回复: {reply}")

            # 保存对话记录（同时更新新旧两套系统）
            if new_conv_id:
                db_manager.update_conversation_id(buyer_name, new_conv_id)
                db_manager.update_session_conversation_id(user_id, item_id, new_conv_id)
            db_manager.add_message(buyer_name, "user", full_message, new_conv_id)
            db_manager.add_message(buyer_name, "assistant", reply, new_conv_id)

            # 更新会话的最后消息时间
            db_manager.update_session_message_time(user_id, item_id)

            # 标记消息为已处理
            if self.skip_duplicate_msg:
                self.processed_messages[msg_id] = time.time()

            # 发送回复
            if await self.browser.send_message(reply):
                log_conversation(
                    buyer_id=buyer_name,
                    buyer_msg=data['last_buyer_message'],
                    bot_reply=reply,
                    product_info=data['product_info'].get("title", ""),
                    order_status=data['order_status'],
                )
            else:
                logger.error(f"发送回复失败: {buyer_name}")

            # 设置 inactive 定时器（3分钟后检查用户是否回复）
            self._schedule_inactive_check(user_id, buyer_name, new_conv_id or data['conversation_id'])

            await self.browser.go_back_to_list()

        except Exception as e:
            logger.error(f"处理会话出错: {e}")
            await self.browser.go_back_to_list()


class ManualMessageHandler(MessageHandler):
    """手动模式消息处理器 - 需要人工确认才发送"""

    async def _handle_conversation(self, conversation: dict):
        """处理单个会话（手动确认模式）"""
        try:
            # 准备数据（复用基类方法）
            data = await self._prepare_conversation(conversation)
            if not data:
                return

            buyer_name = data['buyer_name']
            user_id = data['user_id']
            item_id = data['item_id']
            full_message = data['full_message']

            # 调用 Coze 获取回复
            reply, new_conv_id = await self.coze_client.chat(
                user_message=full_message,
                user_id=buyer_name,
                conversation_id=data['conversation_id'],
                custom_variables=data['custom_vars'],
            )

            # 手动确认
            print("\n" + "=" * 50)
            print(f"买家: {buyer_name}")
            print(f"用户类型: {data.get('customer_type', 'new')}")
            print(f"商品: {data['product_info'].get('title', '未知')}")
            print(f"订单状态: {data['order_status'] or '未知'}")
            print(f"买家消息: {data['last_buyer_message']}")
            if data['last_buyer_images']:
                print(f"买家图片: {len(data['last_buyer_images'])} 张")
            print(f"AI建议回复: {reply}")
            print("=" * 50)

            confirm = input("发送此回复? (y/n/自定义回复): ").strip()

            if confirm.lower() == "y":
                final_reply = reply
            elif confirm.lower() == "n":
                logger.info("跳过此回复")
                await self.browser.go_back_to_list()
                return
            else:
                final_reply = confirm

            # 保存对话记录（同时更新新旧两套系统）
            if new_conv_id:
                db_manager.update_conversation_id(buyer_name, new_conv_id)
                db_manager.update_session_conversation_id(user_id, item_id, new_conv_id)
            db_manager.add_message(buyer_name, "user", full_message, new_conv_id)
            db_manager.add_message(buyer_name, "assistant", final_reply, new_conv_id)

            # 更新会话的最后消息时间
            db_manager.update_session_message_time(user_id, item_id)

            # 发送回复
            if await self.browser.send_message(final_reply):
                log_conversation(
                    buyer_id=buyer_name,
                    buyer_msg=data['last_buyer_message'],
                    bot_reply=final_reply,
                    product_info=data['product_info'].get("title", ""),
                    order_status=data['order_status'],
                )
            else:
                logger.error(f"发送回复失败: {buyer_name}")

            await self.browser.go_back_to_list()

        except Exception as e:
            logger.error(f"处理会话出错: {e}")
            await self.browser.go_back_to_list()
