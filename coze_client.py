"""Coze API 客户端模块"""
import httpx
from typing import Optional
from loguru import logger
from config import Config


class CozeClient:
    """Coze 智能体 API 客户端"""

    def __init__(self):
        self.api_token = Config.COZE_API_TOKEN
        self.bot_id = Config.COZE_BOT_ID
        self.base_url = Config.COZE_API_BASE
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    async def clear_conversation_context(self, conversation_id: str) -> bool:
        """
        清除指定会话的上下文（不删除消息记录）- 异步版本

        调用 Coze API: POST /v1/conversations/{conversation_id}/clear
        清除后，历史消息不会作为上下文被输入给模型，
        但通过查看消息列表等 API 仍能查看到消息内容。

        Args:
            conversation_id: 会话ID

        Returns:
            是否清除成功
        """
        if not conversation_id:
            logger.warning("[Coze] 清除上下文失败: conversation_id 为空")
            return False

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/v1/conversations/{conversation_id}/clear",
                    headers=self.headers,
                )
                response.raise_for_status()
                data = response.json()

                logger.debug(f"清除上下文响应: {data}")

                if data.get("code") == 0:
                    logger.info(f"[Coze] 成功清除会话上下文: {conversation_id}")
                    return True
                else:
                    logger.error(f"清除上下文失败: {data}")
                    return False

        except Exception as e:
            logger.error(f"清除上下文异常: {e}")
            return False

    def clear_conversation_context_sync(self, conversation_id: str) -> bool:
        """
        清除指定会话的上下文（不删除消息记录）- 同步版本

        供 GUI 等同步环境调用，避免异步调用的复杂性。

        Args:
            conversation_id: 会话ID

        Returns:
            是否清除成功
        """
        if not conversation_id:
            logger.warning("[Coze] 清除上下文失败: conversation_id 为空")
            return False

        try:
            # 使用同步客户端
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self.base_url}/v1/conversations/{conversation_id}/clear",
                    headers=self.headers,
                )
                response.raise_for_status()
                data = response.json()

                logger.debug(f"清除上下文响应: {data}")

                if data.get("code") == 0:
                    logger.info(f"[Coze] 成功清除会话上下文: {conversation_id}")
                    return True
                else:
                    logger.error(f"清除上下文失败: {data}")
                    return False

        except Exception as e:
            logger.error(f"清除上下文异常: {e}")
            return False

    async def create_conversation(self, user_id: str) -> Optional[str]:
        """
        为用户创建一个新的会话

        Args:
            user_id: 用户标识

        Returns:
            conversation_id 或 None
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/v1/conversation/create",
                    headers=self.headers,
                    json={}
                )
                response.raise_for_status()
                data = response.json()

                logger.debug(f"创建会话响应: {data}")

                if data.get("code") == 0:
                    conv_id = data.get("data", {}).get("id")
                    logger.info(f"[Coze] 成功创建新会话: {conv_id}")
                    return conv_id
                else:
                    logger.error(f"创建会话失败: {data}")
                    return None

        except Exception as e:
            logger.error(f"创建会话异常: {e}")
            return None

    async def chat(
        self,
        user_message: str,
        user_id: str = "default_user",
        conversation_id: Optional[str] = None,
        additional_context: Optional[str] = None,
        custom_variables: Optional[dict] = None,
    ) -> tuple:
        """
        发送消息给 Coze 智能体并获取回复

        Args:
            user_message: 用户消息
            user_id: 用户标识
            conversation_id: 会话ID，用于保持上下文
            additional_context: 额外上下文信息（如商品信息）
            custom_variables: 自定义变量，如 {"buyer_name": "张三", "product_name": "iPhone"}

        Returns:
            tuple: (回复内容, conversation_id)
        """
        # 直接使用纯文本格式发送消息（包含图片URL）
        # 图片URL格式: [图片] https://xxx.alicdn.com/xxx
        # Coze 工作流会通过 USER_INPUT 参数接收并处理

        # 构建请求payload
        # additional_messages 用于聊天记录，parameters 用于对话流开始节点输入
        payload = {
            "bot_id": self.bot_id,
            "user_id": user_id,
            "stream": False,
            "auto_save_history": True,
            "additional_messages": [
                {
                    "role": "user",
                    "content": user_message,
                    "content_type": "text",
                }
            ],
        }

        # 构建对话流开始节点的输入参数
        parameters = {}

        # 关键：将用户消息通过 USER_INPUT 参数传递给对话流开始节点
        # 对于图片消息，传递原始消息（包含 [图片] URL 格式）以便工作流处理
        parameters["USER_INPUT"] = user_message

        # 添加 CONVERSATION_NAME 参数（对话流开始节点可能需要）
        parameters["CONVERSATION_NAME"] = user_id

        # 合并其他自定义变量（buyer_name, order_status 等）
        if custom_variables:
            parameters.update(custom_variables)
            # custom_variables: 同时用于替换提示词模板中的 {{variable}} 变量
            payload["custom_variables"] = custom_variables

        # parameters: 用于传递对话流开始节点的输入参数
        payload["parameters"] = parameters
        logger.info(f"[Coze] 传递对话流参数: {parameters}")

        # 调试日志：详细请求内容（使用debug级别避免刷屏）
        logger.debug(f"[Coze] 用户消息内容: {user_message}")
        logger.debug(f"[Coze] parameters内容: {parameters}")
        logger.debug(f"[Coze] custom_variables内容: {payload.get('custom_variables', {})}")
        logger.debug(f"[Coze] 完整请求payload: {payload}")

        # conversation_id 必须作为 URL 查询参数传递！
        url = f"{self.base_url}/v3/chat"
        params = {}
        if conversation_id:
            params["conversation_id"] = conversation_id
            logger.info(f"[Coze] 使用已有会话ID (URL参数): {conversation_id}")
        else:
            logger.info("[Coze] 未提供会话ID，将创建新会话")

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    url,
                    headers=self.headers,
                    params=params,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                logger.debug(f"Coze API 响应: {data}")

                # 解析响应获取回复内容
                if data.get("code") == 0:
                    # v3 API 返回的是 chat 对象，需要轮询获取结果
                    chat_id = data.get("data", {}).get("id")
                    conv_id = data.get("data", {}).get("conversation_id")
                    logger.info(f"[Coze] API返回会话ID: {conv_id}")

                    if chat_id and conv_id:
                        reply = await self._poll_chat_result(chat_id, conv_id)
                        return (reply, conv_id)

                logger.error(f"Coze API 返回错误: {data}")
                return ("抱歉，系统暂时无法处理您的请求，请稍后再试。", None)

        except httpx.TimeoutException:
            logger.error("Coze API 请求超时")
            return ("抱歉，响应超时，请稍后再试。", None)
        except Exception as e:
            logger.error(f"Coze API 请求失败: {e}")
            return ("抱歉，系统出现错误，请稍后再试。", None)

    async def _poll_chat_result(
        self, chat_id: str, conversation_id: str, max_attempts: int = 30
    ) -> str:
        """
        轮询获取聊天结果

        Args:
            chat_id: 聊天ID
            conversation_id: 会话ID
            max_attempts: 最大尝试次数

        Returns:
            智能体回复内容
        """
        import asyncio

        for _ in range(max_attempts):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(
                        f"{self.base_url}/v3/chat/retrieve",
                        headers=self.headers,
                        params={
                            "chat_id": chat_id,
                            "conversation_id": conversation_id,
                        },
                    )
                    response.raise_for_status()
                    data = response.json()

                    if data.get("code") == 0:
                        status = data.get("data", {}).get("status")

                        if status == "completed":
                            # 获取消息列表
                            return await self._get_chat_messages(chat_id, conversation_id)
                        elif status == "failed":
                            logger.error(f"Coze 聊天失败: {data}")
                            return "抱歉，AI处理失败，请稍后再试。"

                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"轮询聊天结果失败: {e}")
                await asyncio.sleep(1)

        return "抱歉，等待回复超时，请稍后再试。"

    async def _get_chat_messages(self, chat_id: str, conversation_id: str) -> str:
        """获取聊天消息列表，提取助手回复"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/v3/chat/message/list",
                    headers=self.headers,
                    params={
                        "chat_id": chat_id,
                        "conversation_id": conversation_id,
                    },
                )
                response.raise_for_status()
                data = response.json()

                if data.get("code") == 0:
                    messages = data.get("data", [])
                    # 找到助手的回复消息
                    for msg in messages:
                        if msg.get("role") == "assistant" and msg.get("type") == "answer":
                            return msg.get("content", "")

                return "抱歉，未能获取到回复内容。"

        except Exception as e:
            logger.error(f"获取聊天消息失败: {e}")
            return "抱歉，获取回复失败。"


# 简单测试
if __name__ == "__main__":
    import asyncio

    async def test():
        client = CozeClient()
        reply, conv_id = await client.chat("你好，这个商品还在吗？")
        print(f"回复: {reply}")
        print(f"会话ID: {conv_id}")

    asyncio.run(test())
