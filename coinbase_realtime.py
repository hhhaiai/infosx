#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coinbase Pro 实时虚拟币价格获取
依赖: pip install websocket-client
运行: python coinbase_realtime.py

Coinbase Pro WebSocket API 公共频道说明:
- 连接地址: wss://ws-feed.exchange.coinbase.com
- 订阅格式: {"type": "subscribe", "product_ids": ["BTC-USD"], "channels": ["ticker"]}
- 数据格式: 包含价格、24h交易量、买卖盘等
- 取消订阅: {"type": "unsubscribe", "product_ids": ["BTC-USD"], "channels": ["ticker"]}
"""

import json
import time
import threading
from websocket import WebSocketApp
from datetime import datetime

# ANSI 颜色码
COLOR_GREEN = '\033[92m'
COLOR_RED = '\033[91m'
COLOR_YELLOW = '\033[93m'
COLOR_BLUE = '\033[94m'
COLOR_RESET = '\033[0m'
COLOR_BOLD = '\033[1m'


class CoinbaseRealtime:
    """Coinbase Pro WebSocket 实时价格监控"""

    def __init__(self, top_n=20):
        """
        初始化Coinbase WebSocket客户端

        Coinbase Pro WebSocket API:
        - 连接地址: wss://ws-feed.exchange.coinbase.com
        - 订阅格式: {"type": "subscribe", "product_ids": ["BTC-USD"], "channels": ["ticker"]}
        - 数据格式: 包含价格、24h交易量、买卖盘等
        - 取消订阅: {"type": "unsubscribe", "product_ids": ["BTC-USD"], "channels": ["ticker"]}

        Args:
            top_n (int): 获取市值前N名的币种（默认20）
        """
        # Coinbase Pro公共频道WebSocket地址
        self.ws_url = "wss://ws-feed.exchange.coinbase.com"
        self.top_n = top_n
        self.symbols = self._fetch_top_symbols()

        # 存储价格数据
        self.last_prices = {}
        self.price_data = {}
        self.reconnect_count = 0
        self.max_reconnect = 5

    def _fetch_top_symbols(self):
        """
        从CoinGecko获取市值前N名的币种

        Returns:
            list: 币种交易对列表（大写，连字符，USD基准）
        """
        try:
            from price import fetch_top
            print(f"📊 正在获取市值前{self.top_n}名币种...")
            top_data = fetch_top(self.top_n)
            symbols = []

            # 过滤出在Coinbase上可用的交易对（使用USD）
            coinbase_symbols = []
            # Coinbase支持的完整币种列表（扩展版）
            supported = [
                # 主流币种
                "BTC", "ETH", "BNB", "XRP", "ADA", "DOGE", "SOL", "DOT",
                "MATIC", "AVAX", "LINK", "LTC", "TRX", "ETC", "XLM", "BCH",
                "FIL", "EOS", "XTZ", "AAVE", "MKR", "UNI", "COMP", "YFI",
                "SUSHI", "CRV", "SNX", "1INCH", "ENJ", "CHZ", "BAT", "ZRX",
                "OMG", "LRC", "GRT", "ALGO", "ATOM", "VET", "ICP", "FTM",
                "NEAR", "FLOW", "THETA", "EGLD", "HBAR", "XDC", "QNT", "AXS",
                "SHIB", "APE", "GMT", "GST", "RUNE", "KSM", "OCEAN",
                "BAL", "REN", "KNC", "ZIL", "ONT", "DGB", "WAVES", "DASH",
                "XMR", "ZEC", "NEO", "IOTA", "QTUM", "LSK", "DCR", "RVN",
                "MANA", "SAND", "GALA", "CRO", "HNT", "MINA", "SUI"
            ]

            for coin in top_data:
                symbol = coin['symbol'].upper()
                full_symbol = f"{symbol}-USD"

                # 检查是否为支持币种
                if symbol in supported:
                    coinbase_symbols.append(full_symbol)
                    if len(coinbase_symbols) >= self.top_n:
                        break

            print(f"✅ 成功获取 {len(coinbase_symbols)} 个币种")
            return coinbase_symbols[:self.top_n]

        except Exception as e:
            print(f"⚠️  获取市值排名失败，使用默认列表: {e}")
            # 返回Coinbase支持的默认币种（扩展到20个）
            supported = [
                "BTC-USD", "ETH-USD", "BNB-USD", "XRP-USD", "ADA-USD",
                "DOGE-USD", "SOL-USD", "DOT-USD", "MATIC-USD", "AVAX-USD",
                "LINK-USD", "LTC-USD", "TRX-USD", "ETC-USD", "XLM-USD",
                "BCH-USD", "FIL-USD", "EOS-USD", "XTZ-USD", "AAVE-USD",
                "MKR-USD", "UNI-USD", "YFI-USD", "SNX-USD", "1INCH-USD"
            ]
            return supported[:self.top_n]

    def on_message(self, ws, message):
        """处理WebSocket消息"""
        try:
            data = json.loads(message)

            # 检查是否是订阅成功响应
            if 'type' in data:
                # 订阅确认
                if data['type'] == 'subscriptions':
                    print(f"✅ 订阅成功:")
                    for channel in data['channels']:
                        print(f"  - {channel['name']}: {', '.join(channel['product_ids'])}")
                    return

                # 取消订阅确认
                if data['type'] == 'unsubscribe':
                    print(f"✅ 取消订阅成功: {data['product_id']}")
                    return

                # ticker数据推送
                if data['type'] == 'ticker' and 'product_id' in data:
                    self._process_ticker_data(data)

                # 心跳机制
                if data['type'] == 'heartbeat':
                    return

        except Exception as e:
            print(f"\n❌ 处理消息时出错: {e}")

    def _process_ticker_data(self, data):
        """
        处理ticker数据

        数据格式参考:
        {
            "type": "ticker",
            "sequence": 12345,
            "product_id": "BTC-USD",
            "price": "50000.00",
            "open_24h": "49000.00",
            "volume_24h": "12055.36",
            "low_24h": "48767.00",
            "high_24h": "50500.00",
            "volume_30d": "365000.00",
            "best_bid": "49819.48",
            "best_ask": "49819.49",
            "side": "buy",
            "time": "2023-10-01T12:00:00.000000Z",
            "trade_id": 12345,
            "last_size": "0.028416"
        }
        """
        try:
            product_id = data['product_id']
            price = float(data['price'])
            open_24h = float(data['open_24h'])
            high_24h = float(data['high_24h'])
            low_24h = float(data['low_24h'])
            volume_24h = float(data['volume_24h'])
            best_bid = float(data['best_bid'])
            best_ask = float(data['best_ask'])

            # 计算24h变化
            if open_24h > 0:
                change_24h = ((price - open_24h) / open_24h) * 100
            else:
                change_24h = 0

            # 保存数据
            self.price_data[product_id] = {
                'last': price,
                'open': open_24h,
                'high': high_24h,
                'low': low_24h,
                'volume': volume_24h,
                'bid': best_bid,
                'ask': best_ask,
                'change_24h': change_24h,
                'trade_id': data.get('trade_id', 0)
            }
            self.last_prices[product_id] = price

            # 定时更新显示
            if not hasattr(self, '_last_display'):
                self._last_display = 0

            if time.time() - self._last_display >= 2:
                self._last_display = time.time()
                self._display_all_prices()

        except (KeyError, ValueError) as e:
            print(f"❌ 数据格式错误: {e}")

    def _display_all_prices(self):
        """显示所有币种价格汇总（清屏刷新）"""
        import os
        os.system('cls' if os.name == 'nt' else 'clear')

        print(f"\n✅ Coinbase Pro WebSocket 实时价格监控")
        print(f"📡 已订阅 {len(self.symbols)} 个交易对 (Ticker频道)")
        print(f"🕐 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 95)
        print(f"{COLOR_BLUE}{'排名':<6} | {'交易对':<12} | {'价格 (USD)':<20} | {'24h变化':<15} | {'24h最高':<15} | 状态{COLOR_RESET}")
        print("-" * 95)

        for idx, symbol in enumerate(self.symbols, 1):
            if symbol in self.price_data:
                data = self.price_data[symbol]
                price = data['last']
                change_24h = data['change_24h']
                high_24h = data['high']

                # 格式化价格显示
                if price >= 10000:
                    price_str = f"${price:,.2f}"
                    high_str = f"${high_24h:,.2f}"
                elif price >= 1:
                    price_str = f"${price:,.4f}"
                    high_str = f"${high_24h:,.4f}"
                else:
                    price_str = f"${price:,.8f}"
                    high_str = f"${high_24h:,.8f}"

                # 格式化24h变化
                if change_24h >= 0:
                    change_str = f"{COLOR_GREEN}+{change_24h:.2f}%{COLOR_RESET}"
                else:
                    change_str = f"{COLOR_RED}{change_24h:.2f}%{COLOR_RESET}"

                status = f"{COLOR_GREEN}✓ 实时{COLOR_RESET}"

                print(f"{idx:<6} | {COLOR_BOLD}{symbol:<12}{COLOR_RESET} | {price_str:<20} | {change_str:<15} | {high_str:<15} | {status}")
            else:
                print(f"{idx:<6} | {COLOR_BOLD}{symbol:<12}{COLOR_RESET} | {COLOR_YELLOW}等待数据...{COLOR_RESET:<20} | {COLOR_RED}离线{COLOR_RESET} | --- | 等待")

        print("=" * 95)
        print("💡 价格基准: USD (美元)")
        print("💡 24h数据来源: Coinbase Pro官方API")
        print("💡 按 Ctrl+C 退出监控")
        print("=" * 95)

    def on_error(self, ws, error):
        """WebSocket错误处理"""
        print(f"\n❌ WebSocket错误: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """WebSocket连接关闭"""
        print(f"\n\n⚠️  Coinbase WebSocket连接已关闭")
        print(f"状态码: {close_status_code}, 消息: {close_msg}")

        if self.reconnect_count < self.max_reconnect:
            print(f"🔄 第 {self.reconnect_count + 1}/{self.max_reconnect} 次重连将在 3 秒后进行...")
            time.sleep(3)
            self.reconnect_count += 1
            self.start()
        else:
            print(f"\n❌ 已达到最大重连次数，程序退出")

    def on_open(self, ws):
        """WebSocket连接建立"""
        self.reconnect_count = 0
        self._last_display = 0

        print(f"\n✅ Coinbase WebSocket连接已建立")
        print(f"📡 正在订阅ticker频道...")

        # 构建订阅消息
        subscribe_data = {
            "type": "subscribe",
            "product_ids": self.symbols,
            "channels": ["ticker"]
        }

        # 发送订阅消息
        ws.send(json.dumps(subscribe_data))
        print(f"✅ 订阅请求已发送，等待数据推送...\n")

        # 等待数据
        time.sleep(1)

    def start(self):
        """启动WebSocket连接"""
        ws = WebSocketApp(
            self.ws_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        ws.run_forever()

    def run(self):
        """运行监控"""
        print("🚀 启动Coinbase Pro实时虚拟币价格监控")
        print("💡 使用Coinbase Pro WebSocket API | Ticker频道推送")
        print("📊 提供24h价格数据、涨跌幅、最高最低价")
        print("🌍 价格基准: USD (美元)")
        print("⌨️  按 Ctrl+C 退出\n")

        try:
            self.start()
        except KeyboardInterrupt:
            print("\n\n👋 已停止Coinbase Pro实时价格监控")


if __name__ == '__main__':
    monitor = CoinbaseRealtime()
    monitor.run()
