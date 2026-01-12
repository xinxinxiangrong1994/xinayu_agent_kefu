"""闲鱼浏览器自动化模块"""
import asyncio
import json
from typing import Optional, List, Dict
from dataclasses import dataclass, field
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from loguru import logger
from config import Config, CozeVars


@dataclass
class Message:
    """消息数据类"""
    sender: str  # "buyer" 或 "seller"
    content: str
    timestamp: str = ""
    is_system: bool = False  # 是否为系统消息（如下单通知等）
    image_urls: List[str] = field(default_factory=list)  # 图片URL列表


class XianyuBrowser:
    """闲鱼浏览器自动化类"""

    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_logged_in = False

    def _get_status_mapping_js(self) -> str:
        """获取订单状态映射的 JavaScript 对象字符串（仅映射值）"""
        status_mapping = CozeVars.get_status_mapping_simple()
        return json.dumps(status_mapping, ensure_ascii=False)

    async def start(self):
        """启动浏览器"""
        self.playwright = await async_playwright().start()

        # 使用持久化上下文保持登录状态
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=Config.USER_DATA_DIR,
            headless=Config.HEADLESS,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )

        # 获取或创建页面
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = await self.context.new_page()

        logger.info("浏览器已启动")

    async def close(self):
        """关闭浏览器"""
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("浏览器已关闭")

    async def navigate_to_messages(self):
        """导航到消息页面"""
        await self.page.goto(Config.XIANYU_URL, wait_until="networkidle")
        logger.info(f"已导航到: {Config.XIANYU_URL}")
        await asyncio.sleep(2)

    async def check_login_status(self) -> bool:
        """检查登录状态"""
        try:
            # 通过JavaScript检查是否有会话列表（已登录标志）
            result = await self.page.evaluate("""
                () => {
                    // 检查是否有会话列表
                    const convList = document.querySelector('[class*="conversation-item--"]');
                    // 检查是否有用户名显示
                    const header = document.querySelector('header, [class*="header"]');
                    const hasUserName = header && !header.innerText.includes('登录');
                    return !!(convList || hasUserName);
                }
            """)
            self.is_logged_in = result
            return result
        except Exception as e:
            logger.error(f"检查登录状态失败: {e}")
            return False

    async def wait_for_login(self, timeout: int = 300):
        """等待用户手动登录"""
        logger.info("请在浏览器中完成登录...")
        logger.info(f"等待登录，超时时间: {timeout}秒")

        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout:
            if await self.check_login_status():
                logger.info("登录成功!")
                return True
            await asyncio.sleep(2)

        logger.error("登录超时")
        return False

    async def get_conversation_list(self) -> List[Dict]:
        """获取会话列表"""
        try:
            # 获取可配置的状态映射
            status_mapping_js = self._get_status_mapping_js()

            # 使用JavaScript获取会话列表
            conversations = await self.page.evaluate(f"""
                () => {{
                    const items = document.querySelectorAll('[class*="conversation-item--"]');
                    const result = [];

                    // 订单状态映射表：从配置文件动态加载
                    const statusMapping = {status_mapping_js};
                    const orderStatusKeywords = Object.keys(statusMapping);

                    for (let i = 0; i < items.length; i++) {{
                        const item = items[i];
                        const allText = item.innerText;
                        const lines = allText.split('\\n').filter(l => l.trim());

                        // 检查未读徽章
                        const badge = item.querySelector('.ant-badge-count');
                        let unreadCount = 0;
                        if (badge) {{
                            const num = parseInt(badge.innerText);
                            unreadCount = isNaN(num) ? 1 : num;
                        }}

                        // 提取订单状态并转换为简化状态
                        let orderStatus = '';
                        for (const keyword of orderStatusKeywords) {{
                            if (allText.includes(keyword)) {{
                                orderStatus = statusMapping[keyword];
                                break;
                            }}
                        }}

                        // 解析文本行
                        // 格式: [未读数] 名称 [状态] 消息内容 时间
                        let buyerName = '';
                        let lastMessage = '';
                        let timeStr = '';

                        if (lines.length >= 2) {{
                            // 第一行可能是未读数或名称
                            let startIdx = 0;
                            if (/^\\d+$/.test(lines[0])) {{
                                startIdx = 1; // 跳过未读数
                            }}
                            buyerName = lines[startIdx] || '';

                            // 最后一行是时间
                            timeStr = lines[lines.length - 1] || '';

                            // 倒数第二行通常是消息内容
                            if (lines.length > startIdx + 1) {{
                                lastMessage = lines[lines.length - 2] || '';
                            }}
                        }}

                        // 跳过通知消息
                        if (buyerName === '通知消息') {{
                            continue;
                        }}

                        result.push({{
                            index: i,
                            buyer_name: buyerName,
                            last_message: lastMessage,
                            time: timeStr,
                            unread_count: unreadCount,
                            order_status: orderStatus,
                        }});
                    }}

                    return result;
                }}
            """)

            # 使用 debug 级别，避免日志刷屏
            logger.debug(f"找到 {len(conversations)} 个会话")
            return conversations

        except Exception as e:
            logger.error(f"获取会话列表失败: {e}")
            return []

    async def get_unread_conversations(self) -> List[Dict]:
        """获取有未读消息的会话"""
        all_conversations = await self.get_conversation_list()
        unread = [c for c in all_conversations if c.get("unread_count", 0) > 0]
        # 只有当有未读会话时才输出日志，避免日志刷屏
        if unread:
            logger.info(f"找到 {len(unread)} 个未读会话")
        return unread

    async def enter_conversation(self, conversation: Dict) -> bool:
        """进入指定会话"""
        try:
            index = conversation.get("index", 0)
            # 点击对应的会话项
            result = await self.page.evaluate(f"""
                (idx) => {{
                    const items = document.querySelectorAll('[class*="conversation-item--"]');
                    if (items[idx]) {{
                        items[idx].click();
                        return true;
                    }}
                    return false;
                }}
            """, index)

            if result:
                # 使用配置的延迟时间，等待会话内容和输入框加载
                enter_delay = Config.CONVERSATION_ENTER_DELAY
                await asyncio.sleep(enter_delay)
                # 等待输入框出现
                try:
                    await self.page.wait_for_selector('textarea, [contenteditable="true"]', timeout=3000)
                except:
                    logger.warning(f"等待输入框超时，但仍继续: {conversation.get('buyer_name')}")
                logger.info(f"进入会话: {conversation.get('buyer_name')}")
                return True
            return False
        except Exception as e:
            logger.error(f"进入会话失败: {e}")
            return False

    async def get_current_conversation_messages(self) -> List[Message]:
        """获取当前会话的消息列表（包括图片）"""
        try:
            await asyncio.sleep(0.5)

            # 使用JavaScript获取消息（包括图片）
            messages_data = await self.page.evaluate("""
                () => {
                    const messages = [];
                    const main = document.querySelector('main');
                    if (!main) return messages;

                    // 闲鱼系统消息关键词（下单、付款、发货等系统通知）
                    const systemMessageKeywords = [
                        '我已拍下，待付款',
                        '我已付款，等待你发货',
                        '请双方沟通及时确认价格',
                        '请包装好商品',
                        '你已发货',
                        '已发货，等待买家确认',
                        '买家已确认收货',
                        '交易成功',
                        '交易关闭',
                        '订单已取消',
                        '退款成功',
                        '申请退款',
                        '你撤回了一条消息',
                        '对方撤回了一条消息',
                        '对方正在输入',
                    ];

                    // 闲鱼消息结构: 使用 message-row 作为消息容器
                    // 通过头像位置区分买家/卖家: 头像在右边是卖家消息，头像在左边是买家消息
                    const msgRows = main.querySelectorAll('[class*="message-row--"]');

                    msgRows.forEach(row => {
                        // 获取消息内容元素
                        const contentEl = row.querySelector('[class*="message-content--"]');
                        const imageContainer = row.querySelector('[class*="image-container--"]');

                        // 通过头像位置判断发送者（更可靠，不受"已读"状态影响）
                        const avatar = row.querySelector('[class*="avatar"]');
                        let sender = 'buyer';  // 默认为买家
                        if (avatar && contentEl) {
                            const avatarRect = avatar.getBoundingClientRect();
                            const contentRect = contentEl.getBoundingClientRect();
                            // 头像在消息内容右边 = 卖家消息
                            sender = avatarRect.left > contentRect.left ? 'seller' : 'buyer';
                        }

                        // 提取图片URL（只提取原始格式，过滤掉处理过的webp预览版本）
                        const imageUrls = [];
                        if (imageContainer) {
                            const images = imageContainer.querySelectorAll('img');
                            images.forEach(img => {
                                const src = img.src || img.getAttribute('data-src');
                                if (src && src.includes('alicdn')) {
                                    // 过滤掉：占位图、缩略图、处理过的webp预览版本
                                    // 只保留原始格式（如 .heic, .jpg, .png 等，不带处理后缀）
                                    if (!src.includes('2-tps-2-2') &&
                                        !src.includes('_230x') &&
                                        !src.includes('_.webp')) {
                                        imageUrls.push(src);
                                    }
                                }
                            });
                        }

                        // 提取文本内容（去掉"已读"和"未读"标记）
                        let text = '';
                        if (contentEl) {
                            text = contentEl.innerText.replace('已读', '').replace('未读', '').trim();
                            // 如果内容只是"图片"两个字，说明是纯图片消息
                            if (text === '图片' && imageUrls.length > 0) {
                                text = '';
                            }
                        }

                        // 如果既没有文本也没有图片，跳过
                        if (!text && imageUrls.length === 0) return;

                        // 检查是否为系统消息
                        let isSystemMsg = false;
                        if (text) {
                            for (const keyword of systemMessageKeywords) {
                                if (text.includes(keyword)) {
                                    isSystemMsg = true;
                                    break;
                                }
                            }
                        }

                        messages.push({
                            sender: sender,
                            content: text,
                            is_system: isSystemMsg,
                            image_urls: imageUrls
                        });
                    });

                    return messages;
                }
            """)

            return [Message(
                sender=m["sender"],
                content=m["content"],
                is_system=m.get("is_system", False),
                image_urls=m.get("image_urls", [])
            ) for m in messages_data]

        except Exception as e:
            logger.error(f"获取消息列表失败: {e}")
            return []

    async def get_product_info(self) -> Dict:
        """获取当前会话关联的商品信息"""
        try:
            # 获取可配置的状态映射
            status_mapping_js = self._get_status_mapping_js()

            product = await self.page.evaluate(f"""
                () => {{
                    // 查找商品卡片（通常在聊天区域顶部）
                    const main = document.querySelector('main');
                    if (!main) return {{}};

                    // 尝试多种选择器查找商品卡片
                    const card = main.querySelector('a[href*="item"], [class*="product"], [class*="goods"], [class*="item-card"], [class*="order-card"]');
                    if (!card) return {{}};

                    const text = card.innerText;
                    const lines = text.split('\\n').filter(l => l.trim());

                    // 提取价格
                    let price = '';
                    const priceMatch = text.match(/[¥￥]([\\d.]+)/);
                    if (priceMatch) {{
                        price = priceMatch[1];
                    }}

                    // 订单状态映射表：从配置文件动态加载
                    const statusMapping = {status_mapping_js};
                    const orderStatusKeywords = Object.keys(statusMapping);

                    // 提取订单状态并转换为简化状态
                    let orderStatus = '';
                    for (const keyword of orderStatusKeywords) {{
                        if (text.includes(keyword)) {{
                            orderStatus = statusMapping[keyword];
                            break;
                        }}
                    }}

                    return {{
                        title: lines[0] || '',
                        price: price,
                        order_status: orderStatus,
                        info: text
                    }};
                }}
            """)
            return product
        except Exception as e:
            logger.debug(f"获取商品信息失败: {e}")
            return {}

    async def get_user_id(self, max_retries: int = 10) -> Optional[str]:
        """
        获取当前会话的用户唯一ID（闲鱼号）

        从聊天页面的"闲鱼号"链接中提取用户ID
        链接格式: https://www.goofish.com/personal?userId=XXXXXXXXXX

        Args:
            max_retries: 最大重试次数，默认10次（每次间隔1秒）

        Returns:
            用户ID字符串，如果获取失败返回 None
        """
        for attempt in range(max_retries):
            try:
                user_id = await self.page.evaluate("""
                    () => {
                        const main = document.querySelector('main');
                        if (!main) return null;

                        // 查找包含 "闲鱼号" 的链接
                        const links = main.querySelectorAll('a[href*="personal?userId="]');
                        for (const link of links) {
                            const href = link.href || link.getAttribute('href');
                            if (href) {
                                const match = href.match(/userId=(\d+)/);
                                if (match) {
                                    return match[1];
                                }
                            }
                        }

                        // 备选：查找所有链接，找包含 userId 参数的
                        const allLinks = main.querySelectorAll('a');
                        for (const link of allLinks) {
                            const href = link.href || link.getAttribute('href');
                            if (href && href.includes('userId=')) {
                                const match = href.match(/userId=(\d+)/);
                                if (match) {
                                    return match[1];
                                }
                            }
                        }

                        return null;
                    }
                """)

                if user_id:
                    logger.debug(f"获取到用户ID: {user_id}")
                    return user_id

                # 未获取到，等待后重试
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"获取用户ID失败: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)

        logger.warning(f"获取用户ID失败，已重试 {max_retries} 次")
        return None

    async def get_item_id(self, max_retries: int = 10) -> Optional[str]:
        """
        获取当前会话关联的商品ID

        从商品卡片链接中提取商品ID
        链接格式: https://www.goofish.com/item?id=XXXXXXXXXX

        Args:
            max_retries: 最大重试次数，默认10次（每次间隔1秒）

        Returns:
            商品ID字符串，如果获取失败返回 None
        """
        for attempt in range(max_retries):
            try:
                item_id = await self.page.evaluate("""
                    () => {
                        const main = document.querySelector('main');
                        if (!main) return null;

                        // 查找商品链接
                        const itemLink = main.querySelector('a[href*="item?id="], a[href*="item.htm?id="]');
                        if (itemLink) {
                            const href = itemLink.href || itemLink.getAttribute('href');
                            if (href) {
                                const match = href.match(/[?&]id=(\d+)/);
                                if (match) {
                                    return match[1];
                                }
                            }
                        }

                        // 备选：查找所有包含 item 和 id 的链接
                        const allLinks = main.querySelectorAll('a[href*="item"]');
                        for (const link of allLinks) {
                            const href = link.href || link.getAttribute('href');
                            if (href) {
                                const match = href.match(/[?&]id=(\d+)/);
                                if (match) {
                                    return match[1];
                                }
                            }
                        }

                        return null;
                    }
                """)

                if item_id:
                    logger.debug(f"获取到商品ID: {item_id}")
                    return item_id

                # 未获取到，等待后重试
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"获取商品ID失败: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)

        logger.debug("未能获取商品ID（可能是已完成交易的会话）")
        return None

    async def send_message(self, content: str) -> bool:
        """发送消息"""
        max_retries = 3

        for attempt in range(max_retries):
            try:
                # 等待输入框加载（多种选择器尝试）
                input_selectors = [
                    'textarea[placeholder*="输入"]',
                    'textarea[placeholder*="消息"]',
                    'textarea',
                    '[contenteditable="true"]',
                    '[class*="input"][class*="message"]',
                    '[class*="editor"]',
                    'div[class*="textarea"]',
                ]

                input_elem = None
                for selector in input_selectors:
                    input_elem = await self.page.query_selector(selector)
                    if input_elem:
                        logger.debug(f"找到输入框，选择器: {selector}")
                        break

                if not input_elem:
                    if attempt < max_retries - 1:
                        logger.warning(f"未找到消息输入框，重试 {attempt + 1}/{max_retries}")
                        await asyncio.sleep(1)
                        continue
                    else:
                        logger.error("未找到消息输入框，已达最大重试次数")
                        return False

                await input_elem.click()
                await asyncio.sleep(0.2)
                await input_elem.fill(content)
                await asyncio.sleep(0.2)

                # 点击发送按钮或按回车
                send_selectors = [
                    '[class*="send-btn"]',
                    '[class*="send"][class*="button"]',
                    'button:has-text("发送")',
                    '[class*="btn"]:has-text("发送")',
                ]

                send_btn = None
                for selector in send_selectors:
                    send_btn = await self.page.query_selector(selector)
                    if send_btn:
                        break

                if send_btn:
                    await send_btn.click()
                else:
                    await input_elem.press("Enter")

                await asyncio.sleep(0.5)
                logger.info(f"消息已发送: {content[:50]}...")
                return True

            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"发送消息尝试失败: {e}，重试 {attempt + 1}/{max_retries}")
                    await asyncio.sleep(1)
                else:
                    logger.error(f"发送消息失败: {e}")
                    return False

        return False

    async def go_back_to_list(self):
        """切换到通知消息，让其他会话的新消息能显示未读"""
        try:
            # 点击"通知消息"来取消当前会话的选中状态
            await self.page.evaluate("""
                () => {
                    const items = document.querySelectorAll('[class*="conversation-item--"]');
                    for (let item of items) {
                        if (item.innerText.includes('通知消息')) {
                            item.click();
                            return true;
                        }
                    }
                    // 如果没有通知消息，点击第一个会话
                    if (items.length > 0) {
                        items[0].click();
                        return true;
                    }
                    return false;
                }
            """)
            await asyncio.sleep(0.3)  # 短暂等待页面响应
        except Exception as e:
            logger.debug(f"切换会话失败: {e}")
