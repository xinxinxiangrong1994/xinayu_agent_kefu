"""消息处理模块 - 监控和自动回复逻辑"""
import asyncio
from typing import Dict, Optional
from loguru import logger
import time
from xianyu_browser import XianyuBrowser
from coze_client import CozeClient
from logger_setup import log_conversation, log_system_message
from config import Config, CozeVars
from db_manager import db_manager


async def build_memory_context(coze_client: CozeClient, user_id: str, current_item_id: str, current_message: str) -> Optional[dict]:
    """
    为回头客构建新会话回忆上下文

    当用户从新商品发起会话时，获取其旧商品会话的历史记录，
    构建一个上下文字符串用于传递给新会话的第一条消息。

    Args:
        coze_client: Coze客户端实例
        user_id: 用户ID
        current_item_id: 当前商品ID（排除）
        current_message: 当前用户消息

    Returns:
        dict: 包含两个字段：
            - prefix: 历史前缀（不含当前消息），用于消息合并时拼接
            - full_message: 完整的上下文消息（含当前消息）
        格式如：
            [历史会话记录]
            会话ID: 7593074481959125027
            商品ID: 123456
            商品标题：小米10 PRO 内存12+512

            对话内容:
            user：这个手机是什么颜色的？
            AI：这款是黑色的哦
            ...

            当前消息：你好，这个耳机还在吗？
    """
    if not Config.MEMORY_ENABLED:
        return None

    # 获取用户的其他会话（有conversation_id的）
    other_sessions = db_manager.get_user_other_sessions(user_id, current_item_id)
    if not other_sessions:
        logger.debug(f"[新会话回忆] 用户 {user_id} 没有其他会话")
        return None

    # 取最近的一个会话
    latest_session = other_sessions[0]
    old_conv_id = latest_session.get('conversation_id')
    old_item_id = latest_session.get('item_id', '未知')
    old_product_title = latest_session.get('product_title', '')

    if not old_conv_id:
        return None

    logger.info(f"[新会话回忆] 用户 {user_id} 有旧会话: conv_id={old_conv_id}, item_id={old_item_id}, title={old_product_title}")

    # 从 Coze API 获取旧会话的历史消息
    limit = Config.MEMORY_CONTEXT_ROUNDS * 2  # 每轮对话包含问+答
    history = await coze_client.get_conversation_history(old_conv_id, limit)

    if not history:
        logger.warning(f"[新会话回忆] 无法获取旧会话历史: {old_conv_id}")
        return None

    # 构建上下文前缀（不含当前消息）
    context_lines = [
        "[历史会话记录]",
        f"会话ID: {old_conv_id}",
        f"商品ID: {old_item_id}",
    ]

    # 添加商品标题（如果有）
    if old_product_title:
        context_lines.append(f"商品标题：{old_product_title}")

    context_lines.append("")  # 空行
    context_lines.append("对话内容:")

    for msg in history:
        role = "user" if msg.get('role') == 'user' else "AI"
        content = msg.get('content', '')
        # 跳过系统消息如 [inactive]
        if content.startswith('[') and content.endswith(']'):
            continue
        context_lines.append(f"{role}：{content}")

    context_lines.append("")  # 空行
    context_lines.append("当前消息：")  # 不包含具体消息，留给合并逻辑拼接

    # 前缀：历史记录 + "当前消息："
    prefix = "\n".join(context_lines)
    # 完整消息：前缀 + 当前消息
    full_message = prefix + current_message

    logger.info(f"[新会话回忆] 已构建上下文，共 {len(history)} 条历史消息")
    logger.debug(f"[新会话回忆] 上下文内容:\n{full_message}")

    return {
        'prefix': prefix,
        'full_message': full_message
    }


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
        # ===== 消息合并功能 =====
        # 消息合并配置
        self.merge_enabled = Config.MESSAGE_MERGE_ENABLED
        self.merge_wait_seconds = Config.MESSAGE_MERGE_WAIT_SECONDS
        self.merge_min_length = Config.MESSAGE_MERGE_MIN_LENGTH
        # 消息合并队列: user_id -> {'messages': [], 'conversation': dict, 'data': dict}
        self._merge_queues: Dict[str, dict] = {}
        # 消息合并定时器: user_id -> asyncio.Task
        self._merge_timers: Dict[str, asyncio.Task] = {}
        # 消息合并锁
        self._merge_lock = asyncio.Lock()
        # 已入队消息跟踪: user_id -> set of message contents (用于增量入队，避免重复)
        self._queued_messages: Dict[str, set] = {}

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

        # 显示消息合并配置
        if self.merge_enabled:
            logger.info(f"消息合并: 已启用 (等待: {self.merge_wait_seconds}秒, 短消息阈值: {self.merge_min_length}字)")
        else:
            logger.info("消息合并: 已关闭")

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

    # ===== 消息合并相关方法 =====

    def _cancel_merge_timer(self, user_id: str):
        """取消用户的消息合并定时器"""
        if user_id in self._merge_timers:
            self._merge_timers[user_id].cancel()
            del self._merge_timers[user_id]
            logger.debug(f"[消息合并] 取消定时器: user_id={user_id}")

    def _should_trigger_merge_wait(self, message: str) -> bool:
        """判断消息是否应该触发合并等待（短消息）"""
        if not message:
            return False
        # 去除空白字符后判断长度
        clean_msg = message.strip()
        return len(clean_msg) < self.merge_min_length

    async def _add_to_merge_queue(self, user_id: str, message: str, conversation: dict, data: dict):
        """将消息添加到合并队列，并启动/重置定时器"""
        async with self._merge_lock:
            if user_id not in self._merge_queues:
                self._merge_queues[user_id] = {
                    'messages': [],
                    'conversation': conversation,
                    'data': data,
                }

            # 添加消息到队列
            self._merge_queues[user_id]['messages'].append(message)
            # 更新最新的 conversation 和 data
            self._merge_queues[user_id]['conversation'] = conversation
            self._merge_queues[user_id]['data'] = data

            logger.info(f"[消息合并] 用户 {data.get('buyer_name', user_id)} 消息入队: '{message}' (队列长度: {len(self._merge_queues[user_id]['messages'])})")

            # 取消旧的定时器（如果有）
            self._cancel_merge_timer(user_id)

            # 创建新的定时任务
            async def delayed_process():
                await asyncio.sleep(self.merge_wait_seconds)
                await self._on_merge_timeout(user_id)

            task = asyncio.create_task(delayed_process())
            self._merge_timers[user_id] = task
            logger.debug(f"[消息合并] 设置定时器: user_id={user_id}, {self.merge_wait_seconds}秒后处理")

    async def _on_merge_timeout(self, user_id: str):
        """合并定时器触发：处理合并后的消息"""
        try:
            # 从定时器列表中移除
            if user_id in self._merge_timers:
                del self._merge_timers[user_id]

            async with self._merge_lock:
                if user_id not in self._merge_queues:
                    return

                queue_data = self._merge_queues.pop(user_id)
                messages = queue_data['messages']
                data = queue_data['data']

                if not messages:
                    return

                # 合并所有消息
                merged_message = ''.join(messages)
                buyer_name = data.get('buyer_name', '未知')

                logger.info(f"[消息合并] 用户 {buyer_name} 合并 {len(messages)} 条消息: {messages} -> '{merged_message}'")

                # 清空已入队消息集合
                if user_id in self._queued_messages:
                    self._queued_messages[user_id].clear()

            # 处理合并后的消息
            await self._process_merged_message(data, merged_message)

        except asyncio.CancelledError:
            logger.debug(f"[消息合并] 定时器已取消: user_id={user_id}")
        except Exception as e:
            logger.error(f"[消息合并] 处理超时出错: {e}")

    async def _flush_merge_queue(self, user_id: str, new_message: str) -> Optional[str]:
        """立即刷新合并队列，返回合并后的完整消息（包含新消息）"""
        async with self._merge_lock:
            # 取消定时器
            self._cancel_merge_timer(user_id)

            if user_id not in self._merge_queues:
                return new_message

            queue_data = self._merge_queues.pop(user_id)
            messages = queue_data['messages']

            if not messages:
                return new_message

            # 合并所有排队消息 + 新消息
            messages.append(new_message)
            merged_message = ''.join(messages)

            logger.info(f"[消息合并] 立即合并 {len(messages)} 条消息: '{merged_message}'")
            return merged_message

    async def _flush_merge_queue_incremental(self, user_id: str, new_messages: list) -> str:
        """立即刷新合并队列（增量模式），返回合并后的完整消息"""
        async with self._merge_lock:
            # 取消定时器
            self._cancel_merge_timer(user_id)

            all_messages = []

            # 获取队列中已有的消息
            if user_id in self._merge_queues:
                queue_data = self._merge_queues.pop(user_id)
                all_messages = queue_data['messages']

            # 添加新消息（去重）
            existing_set = set(all_messages)
            for msg in new_messages:
                if msg not in existing_set:
                    all_messages.append(msg)

            if not all_messages:
                return ''.join(new_messages) if new_messages else ""

            merged_message = ''.join(all_messages)
            logger.info(f"[消息合并] 增量合并 {len(all_messages)} 条消息: {all_messages} -> '{merged_message}'")
            return merged_message

    async def _process_merged_message(self, data: dict, merged_message: str):
        """处理合并后的消息（发送给 Coze 并回复）"""
        try:
            buyer_name = data['buyer_name']
            user_id = data['user_id']
            item_id = data['item_id']
            conversation_id = data['conversation_id']
            custom_vars = data['custom_vars']

            # 更新消息内容为合并后的
            data['full_message'] = merged_message
            data['last_buyer_message'] = merged_message

            # 重复消息检查
            msg_id = f"{buyer_name}:{merged_message}"
            if self.skip_duplicate_msg and msg_id in self.processed_messages:
                last_processed_time = self.processed_messages[msg_id]
                time_since = time.time() - last_processed_time
                if time_since < self.message_expire_seconds:
                    logger.debug(f"[消息合并] 消息刚处理过 ({time_since:.0f}秒前)，跳过")
                    return

            # 调用 Coze 获取回复
            reply, new_conv_id = await self.coze_client.chat(
                user_message=merged_message,
                user_id=buyer_name,
                conversation_id=conversation_id,
                custom_variables=custom_vars,
            )

            logger.info(f"[消息合并] AI回复: {reply}")

            # 保存对话记录
            if new_conv_id:
                db_manager.update_conversation_id(buyer_name, new_conv_id)
                db_manager.update_session_conversation_id(user_id, item_id, new_conv_id)
            db_manager.add_message(buyer_name, "user", merged_message, new_conv_id)
            db_manager.add_message(buyer_name, "assistant", reply, new_conv_id)

            # 更新会话的最后消息时间
            db_manager.update_session_message_time(user_id, item_id)

            # 标记消息为已处理
            if self.skip_duplicate_msg:
                self.processed_messages[msg_id] = time.time()

            # 进入会话发送回复
            conversations = await self.browser.get_conversation_list()
            for conv in conversations:
                if conv.get('buyer_name') == buyer_name:
                    if await self.browser.enter_conversation(conv):
                        if await self.browser.send_message(reply):
                            log_conversation(
                                buyer_id=buyer_name,
                                buyer_msg=merged_message,
                                bot_reply=reply,
                                product_info=data['product_info'].get("title", ""),
                                order_status=data['order_status'],
                                conversation_id=new_conv_id or conversation_id,
                                user_msg_time=data.get('user_msg_time'),
                            )
                        else:
                            logger.error(f"[消息合并] 发送回复失败: {buyer_name}")

                        # 设置 inactive 定时器
                        self._schedule_inactive_check(user_id, buyer_name, new_conv_id or conversation_id)

                        await self.browser.go_back_to_list()
                    break

        except Exception as e:
            logger.error(f"[消息合并] 处理消息出错: {e}")

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
                await self._send_inactive_message_to_user(user_id, buyer_name, reply, conversation_id)

            # 标记该用户已发送过 inactive
            db_manager.set_inactive_sent(user_id, True)

        except asyncio.CancelledError:
            # 定时器被取消（用户有新消息了）
            logger.debug(f"[Inactive] 定时器已取消: user_id={user_id}")
        except Exception as e:
            logger.error(f"[Inactive] 处理超时出错: {e}")

    async def _send_inactive_message_to_user(self, user_id: str, buyer_name: str, message: str, conversation_id: str = ""):
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
            # 使用 log_system_message 只记录AI发送的消息，不记录内部触发标记
            log_system_message(
                buyer_id=buyer_name,
                message=message,
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
        import datetime
        # 记录用户消息的接收时间（用于日志显示）
        user_msg_time = datetime.datetime.now().strftime("%H:%M:%S")

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

        # 从数据库获取商品信息并组装格式化字符串
        if item_id and item_id != "unknown":
            db_product = db_manager.get_product(item_id)
            if db_product:
                # 组装格式化的商品信息
                formatted_info = "[当前会话-商品信息]\n"
                formatted_info += f"标题：{db_product.get('title', '')}\n"
                formatted_info += f"价格：{db_product.get('price', '')}\n"
                if db_product.get('notes'):
                    formatted_info += f"备注：{db_product.get('notes')}"
                product_info["notes"] = formatted_info
                logger.debug(f"获取到商品信息: {item_id}")

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

        # 提取买家消息（获取最后一条卖家消息之后的所有买家消息）
        # 这样可以处理用户快速连续发送多条消息的情况
        buyer_messages = []
        buyer_images = []

        # 找到最后一条卖家消息的位置
        last_seller_idx = -1
        for i, msg in enumerate(messages):
            if msg.sender == "seller" and not msg.is_system:
                last_seller_idx = i

        # 获取最后一条卖家消息之后的所有买家消息
        for i, msg in enumerate(messages):
            if i > last_seller_idx and msg.sender == "buyer" and not msg.is_system:
                if msg.content:
                    buyer_messages.append(msg.content)
                if msg.image_urls:
                    buyer_images.extend(msg.image_urls)

        # 合并所有买家消息
        last_buyer_message = ''.join(buyer_messages) if buyer_messages else None
        last_buyer_images = buyer_images

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

        # 显示合并信息
        if len(buyer_messages) > 1:
            logger.info(f"[消息合并] 合并了 {len(buyer_messages)} 条买家消息: {buyer_messages} -> '{last_buyer_message}'")
        else:
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
        # 同时检查是否需要添加新会话回忆上下文
        memory_prefix = None  # 历史上下文前缀，用于消息合并时拼接
        if not conversation_id:
            logger.info(f"[会话] 为用户 {buyer_name} 创建新的 Coze 会话...")
            conversation_id = await self.coze_client.create_conversation(buyer_name)
            if conversation_id:
                db_manager.update_session_conversation_id(user_id, item_id, conversation_id)
                logger.info(f"[会话] 新会话已创建: {conversation_id}")

            # 如果是回头客的新会话，获取历史上下文
            if customer_type == 'returning' and Config.MEMORY_ENABLED:
                logger.info(f"[新会话回忆] 检测到回头客，准备获取历史上下文")
                memory_result = await build_memory_context(
                    self.coze_client, user_id, item_id, full_message
                )
                if memory_result:
                    # 保存前缀（用于消息合并时拼接）和完整消息
                    memory_prefix = memory_result['prefix']
                    full_message = memory_result['full_message']
                    logger.info(f"[新会话回忆] 已构建包含历史上下文的消息")

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
            'buyer_messages': buyer_messages,  # 原始消息列表（用于增量入队）
            'last_buyer_message': last_buyer_message,  # 合并后的消息（用于非合并模式）
            'last_buyer_images': last_buyer_images,
            'full_message': full_message,
            'conversation_id': conversation_id,
            'customer_type': customer_type,
            'memory_prefix': memory_prefix,  # 历史上下文前缀（如有）
            'user_msg_time': user_msg_time,  # 用户消息接收时间
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
            last_buyer_message = data['last_buyer_message'] or ""
            buyer_messages = data.get('buyer_messages', [])  # 原始消息列表
            memory_prefix = data.get('memory_prefix')  # 历史上下文前缀（如有）

            # ===== 消息合并逻辑（新版：在会话中等待）=====
            if self.merge_enabled and last_buyer_message:
                # 检查当前消息是否是短消息
                if self._should_trigger_merge_wait(last_buyer_message):
                    total_seconds = int(self.merge_wait_seconds)
                    logger.info(f"[消息合并] 检测到短消息，开始等待 {total_seconds} 秒...")

                    # 简单计数器倒计时（避免time.time()受get_messages耗时影响）
                    remaining = total_seconds
                    last_message_count = len(buyer_messages)

                    while remaining > 0:
                        logger.info(f"[消息合并] 倒计时: {remaining}")
                        await asyncio.sleep(1)
                        remaining -= 1

                        # 重新获取消息检测是否有新消息
                        messages = await self.browser.get_current_conversation_messages()
                        if not messages:
                            continue

                        # 重新提取买家消息（找最后一条卖家消息之后的所有买家消息）
                        new_buyer_messages = []
                        last_seller_idx = -1
                        for i, msg in enumerate(messages):
                            if msg.sender == "seller" and not msg.is_system:
                                last_seller_idx = i
                        for i, msg in enumerate(messages):
                            if i > last_seller_idx and msg.sender == "buyer" and not msg.is_system:
                                if msg.content:
                                    new_buyer_messages.append(msg.content)

                        current_count = len(new_buyer_messages)

                        if current_count > last_message_count:
                            # 有新消息，重置倒计时
                            new_msgs = new_buyer_messages[last_message_count:]
                            logger.info(f"[消息合并] 检测到新消息: {new_msgs}，重置倒计时")
                            remaining = total_seconds
                            last_message_count = current_count
                            buyer_messages = new_buyer_messages

                    # 等待结束，合并所有消息
                    merged_message = ''.join(buyer_messages)
                    logger.info(f"[消息合并] 等待结束，合并 {len(buyer_messages)} 条消息: {merged_message}")

                    # 如果有历史上下文前缀，拼接到合并后的消息前面
                    if memory_prefix:
                        full_message = memory_prefix + merged_message
                        logger.info(f"[消息合并] 已拼接历史上下文前缀")
                    else:
                        full_message = merged_message

                    data['full_message'] = full_message
                    data['last_buyer_message'] = merged_message  # 保持原始消息用于日志显示

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
                    conversation_id=new_conv_id or data['conversation_id'],
                    user_msg_time=data.get('user_msg_time'),
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
                    conversation_id=new_conv_id or data.get('conversation_id', ''),
                    user_msg_time=data.get('user_msg_time'),
                )
            else:
                logger.error(f"发送回复失败: {buyer_name}")

            await self.browser.go_back_to_list()

        except Exception as e:
            logger.error(f"处理会话出错: {e}")
            await self.browser.go_back_to_list()
