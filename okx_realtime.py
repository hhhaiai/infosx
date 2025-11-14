#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX 实时虚拟币价格获取
依赖: pip install websocket-client
运行: python okx_realtime.py

OKX WebSocket API 公共频道说明:
- 连接地址: wss://ws.okx.com:8443/ws/v5/public
- 订阅格式: {"op": "subscribe", "args": [{"channel": "tickers", "instId": "BTC-USDT"}]}
- 数据格式: 包含价格、涨跌幅、24h交易量等
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


class OKXRealtime:
    """OKX WebSocket 实时价格监控"""

    def __init__(self, top_n=20):
        """
        初始化OKX WebSocket客户端

        OKX WebSocket API 公共频道说明:
        - 连接地址: wss://ws.okx.com:8443/ws/v5/public
        - 订阅格式: {"op": "subscribe", "args": [{"channel": "tickers", "instId": "BTC-USDT"}]}
        - 数据格式: 包含价格、涨跌幅、24h交易量等

        Args:
            top_n (int): 获取市值前N名的币种（默认20）
        """
        # OKX公共频道WebSocket地址
        self.ws_url = "wss://ws.okx.com:8443/ws/v5/public"
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
            list: 币种交易对列表（大写，连字符）
        """
        try:
            from price import fetch_top
            print(f"📊 正在获取市值前{self.top_n}名币种...")
            top_data = fetch_top(self.top_n)
            symbols = []

            # 过滤出在OKX上可用的交易对
            okx_symbols = []
            for coin in top_data:
                symbol = coin['symbol'].upper()
                full_symbol = f"{symbol}-USDT"
                # 检查是否为常见币种
                if len(symbol) <= 5 and symbol.isalpha():
                    okx_symbols.append(full_symbol)
                    if len(okx_symbols) >= self.top_n:
                        break

            print(f"✅ 成功获取 {len(okx_symbols)} 个币种")
            return okx_symbols[:self.top_n]

        except Exception as e:
            print(f"⚠️  获取市值排名失败，使用默认列表: {e}")
            # 返回默认前20名币种
            return ["BTC-USDT", "ETH-USDT", "BNB-USDT", "XRP-USDT", "ADA-USDT",
                    "DOGE-USDT", "SOL-USDT", "DOT-USDT", "MATIC-USDT", "AVAX-USDT",
                    "LINK-USDT", "LTC-USDT", "TRX-USDT", "ETC-USDT", "XLM-USDT",
                    "BCH-USDT", "FIL-USDT", "EOS-USDT", "XTZ-USDT", "AAVE-USDT"]

    def on_message(self, ws, message):
        """处理WebSocket消息"""
        try:
            data = json.loads(message)

            # 检查是否是订阅成功响应
            if 'event' in data and data['event'] == 'subscribe':
                print(f"✅ 订阅成功: {data['arg']['channel']} - {data['arg']['instId']}")
                return

            # 检查是否是取消订阅响应
            if 'event' in data and data['event'] == 'unsubscribe':
                print(f"✅ 取消订阅成功: {data['arg']['channel']} - {data['arg']['instId']}")
                return

            # 检查是否是错误响应
            if 'event' in data and data['event'] == 'error':
                print(f"❌ 订阅错误: {data['msg']}")
                return

            # 处理ticker数据推送
            if 'data' in data and isinstance(data['data'], list):
                for ticker_data in data['data']:
                    self._process_ticker_data(ticker_data)

        except Exception as e:
            print(f"\n❌ 处理消息时出错: {e}")

    def _process_ticker_data(self, data):
        """
        处理ticker数据

        数据格式参考:
        {
            "instType": "SPOT",
            "instId": "BTC-USDT",
            "last": "50000.00",
            "bidSz": "0.1",
            "bidPx": "49999.00",
            "askSz": "0.1",
            "askPx": "50001.00",
            "open24h": "49000.00",
            "high24h": "51000.00",
            "low24h": "48000.00",
            "volCcy24h": "1000000",
            "vol24h": "20.5",
            "ts": "1234567890123"
        }
        """
        try:
            inst_id = data['instId']
            last_price = float(data['last'])
            bid_price = float(data['bidPx'])
            ask_price = float(data['askPx'])
            open_24h = float(data['open24h'])
            high_24h = float(data['high24h'])
            low_24h = float(data['low24h'])
            vol_24h = float(data['vol24h'])
            timestamp = int(data['ts'])

            # 计算24h变化
            if open_24h > 0:
                change_24h = ((last_price - open_24h) / open_24h) * 100
            else:
                change_24h = 0

            # 保存数据
            self.price_data[inst_id] = {
                'last': last_price,
                'bid': bid_price,
                'ask': ask_price,
                'open': open_24h,
                'high': high_24h,
                'low': low_24h,
                'volume': vol_24h,
                'change_24h': change_24h,
                'timestamp': timestamp
            }
            self.last_prices[inst_id] = last_price

            # 定时更新显示
            if not hasattr(self, '_last_display'):
                self._last_display = 0

            if time.time() - self._last_display >= 2:
                self._last_display = time.time()
                self._display_all_prices()

        except KeyError as e:
            print(f"❌ 数据格式错误，缺少字段: {e}")

    def _display_all_prices(self):
        """显示所有币种价格汇总（清屏刷新）"""
        import os
        os.system('cls' if os.name == 'nt' else 'clear')

        print(f"\n✅ OKX WebSocket 实时价格监控")
        print(f"📡 已订阅 {len(self.symbols)} 个交易对 (Ticker频道)")
        print(f"🕐 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 90)
        print(f"{COLOR_BLUE}{'排名':<6} | {'交易对':<12} | {'价格 (USDT)':<20} | {'24h变化':<15} | {'24h最高':<15} | 状态{COLOR_RESET}")
        print("-" * 90)

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

        print("=" * 90)
        print("💡 24h数据来源: OKX官方API")
        print("💡 按 Ctrl+C 退出监控")
        print("=" * 90)

    def on_error(self, ws, error):
        """WebSocket错误处理"""
        print(f"\n❌ WebSocket错误: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """WebSocket连接关闭"""
        print(f"\n\n⚠️  OKX WebSocket连接已关闭")
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

        print(f"\n✅ OKX WebSocket连接已建立")
        print(f"📡 正在订阅ticker频道...")

        # 构建订阅消息
        subscribe_data = {
            "op": "subscribe",
            "args": []
        }

        # 添加所有交易对的订阅
        for symbol in self.symbols:
            subscribe_data["args"].append({
                "channel": "tickers",
                "instId": symbol
            })

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
        print("🚀 启动OKX实时虚拟币价格监控")
        print("💡 使用OKX WebSocket API | Ticker频道推送")
        print("📊 提供24h价格数据、涨跌幅、最高最低价")
        print("⌨️  按 Ctrl+C 退出\n")

        try:
            self.start()
        except KeyboardInterrupt:
            print("\n\n👋 已停止OKX实时价格监控")


if __name__ == '__main__':
    monitor = OKXRealtime()
    monitor.run()
