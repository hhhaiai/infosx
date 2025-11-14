#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Binance 实时虚拟币价格获取 - 稳定版
依赖: pip install websocket-client requests
运行: python binance_realtime.py

特性:
✅ 动态获取市值前N名币种（默认20名）
✅ 使用单独流订阅，每个交易对一个WebSocket连接
✅ 24h价格数据、涨跌幅、最高最低价
✅ 自动重连，线程安全
"""

# 版本号
__version__ = "2.0.0"

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


class BinanceRealtime:
    """Binance WebSocket 实时价格监控 - 稳定版

    特性:
    - 动态获取市值前N名币种
    - 单独流订阅（每交易对一个连接）
    - 24h完整价格数据
    - 线程安全
    """

    def __init__(self, top_n=20):
        """
        初始化Binance WebSocket客户端

        单独流订阅方式:
        - 连接地址: wss://stream.binance.com/ws/{symbol}@ticker
        - 不需要发送订阅消息，连接后直接接收数据
        - 每个交易对一个连接

        Args:
            top_n (int): 获取市值前N名的币种（默认20）
        """
        # 动态获取市值前N名币种
        self.top_n = top_n
        self.symbols = self._fetch_top_symbols()

        self.last_prices = {}
        self.price_data = {}
        self.reconnect_count = 0
        self.max_reconnect = 5
        self.connections = {}  # 存储每个交易对的连接
        self.lock = threading.Lock()

    def _fetch_top_symbols(self):
        """
        从CoinGecko获取市值前N名的币种

        Returns:
            list: 币种交易对列表（小写，无分隔符）
        """
        try:
            from price import fetch_top
            print(f"📊 正在获取市值前{self.top_n}名币种...")
            top_data = fetch_top(self.top_n)
            symbols = []

            # 过滤出在Binance上可用的交易对
            binance_symbols = []
            exclude_symbols = ['usdt', 'usdc', 'busd', 'tusd', 'dai', 'steth', 'wbtc', 'shib']  # 排除稳定币等

            for coin in top_data:
                symbol = coin['symbol'].lower()
                full_symbol = f"{symbol}usdt"

                # 过滤条件：
                # 1. 币种符号长度 <= 5
                # 2. 必须是字母（排除数字）
                # 3. 不在排除列表中
                # 4. 避免连字符和特殊字符
                if (len(symbol) <= 5 and
                    symbol.isalpha() and
                    symbol not in exclude_symbols and
                    '-' not in symbol and
                    '_' not in symbol):

                    binance_symbols.append(full_symbol)
                    if len(binance_symbols) >= self.top_n:
                        break

            print(f"✅ 成功获取 {len(binance_symbols)} 个币种")
            return binance_symbols[:self.top_n]

        except Exception as e:
            print(f"⚠️  获取市值排名失败，使用默认列表: {e}")
            # 返回默认前20名币种
            return ["btcusdt", "ethusdt", "bnbusdt", "xrpusdt", "adausdt",
                    "dogeusdt", "solusdt", "dotusdt", "maticusdt", "avaxusdt",
                    "linkusdt", "ltcusdt", "trxusdt", "etcusdt", "xlmusdt",
                    "bchusdt", "filusdt", "eosusdt", "xtzusdt", "aaveusdt"]

    def create_connection(self, symbol):
        """为单个交易对创建WebSocket连接"""
        # 单独流URL格式：wss://stream.binance.com/ws/{symbol}@ticker
        ws_url = f"wss://stream.binance.com/ws/{symbol}@ticker"

        ws = WebSocketApp(
            ws_url,
            on_open=lambda ws: self.on_open(ws, symbol),
            on_message=lambda ws, msg: self.on_message(ws, msg, symbol),
            on_error=lambda ws, error: self.on_error(ws, error, symbol),
            on_close=lambda ws, code, msg: self.on_close(ws, code, msg, symbol)
        )

        # 启动连接
        thread = threading.Thread(target=ws.run_forever, daemon=True)
        thread.start()

        # 存储连接
        with self.lock:
            self.connections[symbol] = {
                'ws': ws,
                'thread': thread,
                'connected': False
            }

        return ws

    def on_message(self, ws, message, symbol):
        """处理 WebSocket 消息"""
        try:
            data = json.loads(message)

            # Binance Ticker 数据格式
            if 'e' in data and data['e'] == '24hrTicker':
                last_price = float(data['c'])
                price_change = float(data['p'])
                price_change_percent = float(data['P'])
                high_24h = float(data['h'])
                low_24h = float(data['l'])
                volume_24h = float(data['v'])
                open_24h = float(data['o'])

                # 保存数据
                with self.lock:
                    self.price_data[symbol] = {
                        'price': last_price,
                        'change': price_change,
                        'change_percent': price_change_percent,
                        'high_24h': high_24h,
                        'low_24h': low_24h,
                        'volume_24h': volume_24h,
                        'open_24h': open_24h,
                        'timestamp': data.get('E', int(time.time()))
                    }
                    self.last_prices[symbol] = last_price

                # 定时更新显示
                if not hasattr(self, '_last_display'):
                    self._last_display = 0

                if time.time() - self._last_display >= 2:
                    self._last_display = time.time()
                    self._display_all_crypto_prices()

        except Exception as e:
            print(f"\n❌ 处理 {symbol} 消息时出错: {e}")

    def _display_all_crypto_prices(self):
        """显示所有币种价格汇总（清屏刷新）"""
        import os
        os.system('cls' if os.name == 'nt' else 'clear')

        print(f"\n✅ Binance WebSocket 实时价格监控 (单独流版本)")
        print(f"📡 已连接 {len(self.symbols)} 个交易对 (每个交易对独立连接)")
        print(f"🕐 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 90)
        print(f"{COLOR_BLUE}{'排名':<6} | {'交易对':<12} | {'价格 (USDT)':<20} | {'24h变化':<15} | {'24h最高':<15} | 状态{COLOR_RESET}")
        print("-" * 90)

        connected_count = 0
        with self.lock:
            for idx, symbol in enumerate(self.symbols, 1):
                if symbol in self.price_data:
                    connected_count += 1
                    data = self.price_data[symbol]
                    price = data['price']
                    change_percent = data['change_percent']
                    high_24h = data['high_24h']

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
                    if change_percent >= 0:
                        change_str = f"{COLOR_GREEN}+{change_percent:.2f}%{COLOR_RESET}"
                    else:
                        change_str = f"{COLOR_RED}{change_percent:.2f}%{COLOR_RESET}"

                    status = f"{COLOR_GREEN}✓ 连接{COLOR_RESET}"

                    print(f"{idx:<6} | {COLOR_BOLD}{symbol.upper():<12}{COLOR_RESET} | {price_str:<20} | {change_str:<15} | {high_str:<15} | {status}")
                else:
                    # 检查连接状态
                    conn_status = "连接中"
                    if symbol in self.connections:
                        if self.connections[symbol]['connected']:
                            conn_status = f"{COLOR_YELLOW}等待数据{COLOR_RESET}"
                        else:
                            conn_status = f"{COLOR_RED}离线{COLOR_RESET}"

                    print(f"{idx:<6} | {COLOR_BOLD}{symbol.upper():<12}{COLOR_RESET} | {COLOR_YELLOW}连接中...{COLOR_RESET:<20} | {COLOR_RED}---{COLOR_RESET} | --- | {conn_status}")

        print("=" * 90)
        print(f"💡 连接状态: {connected_count}/{len(self.symbols)} 已连接")
        print("💡 使用单独流API | 每个交易对独立连接")
        print("💡 按 Ctrl+C 退出监控")
        print("=" * 90)

    def on_error(self, ws, error, symbol):
        """WebSocket 错误处理"""
        print(f"\n❌ {symbol} WebSocket 错误: {error}")
        with self.lock:
            if symbol in self.connections:
                self.connections[symbol]['connected'] = False

    def on_close(self, ws, close_status_code, close_msg, symbol):
        """WebSocket 连接关闭"""
        print(f"\n⚠️  {symbol} WebSocket 连接已关闭")

        with self.lock:
            if symbol in self.connections:
                self.connections[symbol]['connected'] = False

        # 尝试重连
        if self.reconnect_count < self.max_reconnect:
            print(f"🔄 {symbol} 将在 3 秒后重连...")
            time.sleep(3)
            self.reconnect_count += 1
            self.create_connection(symbol)
        else:
            print(f"\n❌ {symbol} 已达到最大重连次数")

    def on_open(self, ws, symbol):
        """WebSocket 连接建立"""
        print(f"✅ {symbol.upper()} 连接已建立")
        with self.lock:
            if symbol in self.connections:
                self.connections[symbol]['connected'] = True

    def start(self):
        """启动所有连接"""
        print("🚀 启动 Binance 实时价格监控 (单独流版本)")
        print(f"📡 正在为 {len(self.symbols)} 个交易对创建连接...")

        # 为每个交易对创建连接
        for symbol in self.symbols:
            self.create_connection(symbol)
            time.sleep(0.1)  # 避免同时创建过多连接

        print(f"✅ 所有连接已创建，等待数据推送...\n")

        # 等待数据并初始化显示
        time.sleep(2)

        # 初始显示界面
        self._display_all_crypto_prices()

        # 持续监控（主线程保持活跃）
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n👋 已停止实时价格监控")

    def run(self):
        """运行监控"""
        self.start()


if __name__ == '__main__':
    monitor = BinanceRealtime(top_n=20)
    monitor.run()
