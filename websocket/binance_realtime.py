#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Binance 实时虚拟币价格获取 - 稳定增强版
依赖: pip install websocket-client requests
运行: python binance_realtime.py

特性:
✅ 动态获取市值前N名币种（默认20名）
✅ 使用单独流订阅，每个交易对一个WebSocket连接
✅ 24h价格数据、涨跌幅、最高最低价
✅ 自动重连，线程安全，连接状态监控
✅ 异常处理和资源清理
"""

# 版本号
__version__ = "2.1.0"

import json
import time
import threading
import requests
import logging
from websocket import WebSocketApp
from datetime import datetime

# ANSI 颜色码
COLOR_GREEN = '\033[92m'
COLOR_RED = '\033[91m'
COLOR_YELLOW = '\033[93m'
COLOR_BLUE = '\033[94m'
COLOR_RESET = '\033[0m'
COLOR_BOLD = '\033[1m'

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class BinanceRealtime:
    """Binance WebSocket 实时价格监控 - 稳定增强版

    特性:
    - 动态获取市值前N名币种
    - 单独流订阅（每交易对一个连接）
    - 24h完整价格数据
    - 线程安全
    - 连接健康检查
    - 优雅关闭
    """

    def __init__(self, top_n=20):
        """
        初始化Binance WebSocket客户端

        Args:
            top_n (int): 获取市值前N名的币种（默认20）
        """
        self.top_n = top_n
        self.symbols = self._fetch_top_symbols_with_fallback()
        
        # 数据存储
        self.price_data = {}
        self.connections = {}  # 存储每个交易对的连接信息
        self.lock = threading.Lock()
        
        # 连接管理
        self.is_running = False
        self.reconnect_attempts = {}
        self.max_reconnect_per_symbol = 3
        self.connection_timeout = 10
        
        # 显示控制
        self.last_display_time = 0
        self.display_interval = 2  # 显示更新间隔(秒)

    def _fetch_top_symbols_with_fallback(self):
        """
        动态获取市值前N名币种，带多层回退机制
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"🔄 第 {attempt + 1}/{max_retries} 次尝试获取市值前{self.top_n}名币种...")
                symbols = self._fetch_valid_binance_symbols()
                if symbols and len(symbols) >= min(10, self.top_n):
                    logger.info(f"✅ 成功获取 {len(symbols)} 个有效交易对")
                    return symbols
                else:
                    logger.warning(f"⚠️ 第 {attempt + 1} 次获取失败，有效交易对数量不足")
                    if attempt < max_retries - 1:
                        time.sleep(2)
            except Exception as e:
                logger.error(f"❌ 获取币种列表出错: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
        
        # 如果所有重试都失败，使用硬编码的备用列表
        logger.warning("⚠️ 使用备用币种列表")
        return self._get_fallback_symbols()

    def _fetch_valid_binance_symbols(self):
        """
        获取有效的Binance交易对
        """
        try:
            # 首先获取市值排名
            top_coins = self._fetch_market_cap_ranking(self.top_n * 2)
            if not top_coins:
                return None
            
            # 获取Binance交易对信息
            binance_symbols = self._fetch_binance_exchange_info()
            if not binance_symbols:
                return None
            
            # 匹配：找到市值排名中在Binance可用的USDT交易对
            valid_symbols = []
            
            for coin in top_coins:
                symbol_lower = coin['symbol'].lower()
                possible_symbol = f"{symbol_lower}usdt"
                
                if possible_symbol in binance_symbols:
                    valid_symbols.append(possible_symbol)
                    if len(valid_symbols) >= self.top_n:
                        break
            
            logger.info(f"📊 匹配到 {len(valid_symbols)} 个有效交易对")
            return valid_symbols
            
        except Exception as e:
            logger.error(f"❌ 获取有效交易对失败: {e}")
            return None

    def _fetch_market_cap_ranking(self, limit=40):
        """获取市值排名"""
        try:
            logger.info("📈 获取市值排名...")
            url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {
                'vs_currency': 'usd',
                'order': 'market_cap_desc',
                'per_page': limit,
                'page': 1,
                'sparkline': 'false'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # 过滤掉稳定币和无效币种
            filtered_coins = []
            stablecoins = ['usdt', 'usdc', 'busd', 'dai', 'ust', 'tusd', 'usdp']
            
            for coin in data:
                symbol_lower = coin['symbol'].lower()
                if (symbol_lower not in stablecoins and 
                    len(symbol_lower) <= 8 and
                    symbol_lower.isalpha()):
                    filtered_coins.append({
                        'id': coin['id'],
                        'symbol': coin['symbol'],
                        'name': coin['name'],
                        'market_cap_rank': coin['market_cap_rank']
                    })
            
            logger.info(f"✅ 获取到 {len(filtered_coins)} 个有效币种排名")
            return filtered_coins
            
        except Exception as e:
            logger.error(f"❌ 获取市值排名失败: {e}")
            return None

    def _fetch_binance_exchange_info(self):
        """从Binance API获取交易对信息"""
        try:
            logger.info("📊 获取Binance交易对信息...")
            url = "https://api.binance.com/api/v3/exchangeInfo"
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # 提取所有USDT交易对
            usdt_symbols = set()
            for symbol_info in data['symbols']:
                if (symbol_info['quoteAsset'] == 'USDT' and 
                    symbol_info['status'] == 'TRADING'):
                    usdt_symbols.add(symbol_info['symbol'].lower())
            
            logger.info(f"✅ Binance返回 {len(usdt_symbols)} 个可用USDT交易对")
            return usdt_symbols
            
        except Exception as e:
            logger.error(f"❌ 获取Binance交易对失败: {e}")
            return None

    def _get_fallback_symbols(self):
        """获取备用币种列表（确保在Binance上存在）"""
        fallback_symbols = [
            "btcusdt", "ethusdt", "bnbusdt", "solusdt", "xrpusdt",
            "adausdt", "dogeusdt", "maticusdt", "dotusdt", "trxusdt",
            "avaxusdt", "linkusdt", "ltcusdt", "bchusdt", "atomusdt",
            "etcusdt", "xlmusdt", "filusdt", "eosusdt", "xtzusdt"
        ]
        return fallback_symbols[:self.top_n]

    def create_connection(self, symbol):
        """为单个交易对创建WebSocket连接"""
        if not self.is_running:
            return None

        # 检查重连次数
        if symbol not in self.reconnect_attempts:
            self.reconnect_attempts[symbol] = 0
        
        if self.reconnect_attempts[symbol] >= self.max_reconnect_per_symbol:
            logger.warning(f"❌ {symbol} 已达到最大重连次数，停止重连")
            return None

        # 单独流URL格式：wss://stream.binance.com/ws/{symbol}@ticker
        ws_url = f"wss://stream.binance.com/ws/{symbol}@ticker"

        try:
            ws = WebSocketApp(
                ws_url,
                on_open=lambda ws: self.on_open(ws, symbol),
                on_message=lambda ws, msg: self.on_message(ws, msg, symbol),
                on_error=lambda ws, error: self.on_error(ws, error, symbol),
                on_close=lambda ws, code, msg: self.on_close(ws, code, msg, symbol)
            )

            # 存储连接信息
            with self.lock:
                self.connections[symbol] = {
                    'ws': ws,
                    'connected': False,
                    'last_activity': time.time(),
                    'thread': None
                }

            # 启动连接线程
            thread = threading.Thread(
                target=self._run_websocket, 
                args=(ws, symbol),
                daemon=True,
                name=f"WS-{symbol}"
            )
            thread.start()

            with self.lock:
                self.connections[symbol]['thread'] = thread

            logger.info(f"🔗 已为 {symbol.upper()} 创建连接")
            return ws

        except Exception as e:
            logger.error(f"❌ 创建 {symbol} 连接失败: {e}")
            self._schedule_reconnect(symbol)
            return None

    def _run_websocket(self, ws, symbol):
        """运行WebSocket连接（带超时控制）"""
        try:
            # 设置运行超时
            ws.run_forever(
                ping_interval=30,
                ping_timeout=10
            )
        except Exception as e:
            logger.error(f"❌ {symbol} WebSocket运行异常: {e}")
            self._schedule_reconnect(symbol)

    def on_message(self, ws, message, symbol):
        """处理 WebSocket 消息"""
        try:
            data = json.loads(message)

            # 更新活动时间
            with self.lock:
                if symbol in self.connections:
                    self.connections[symbol]['last_activity'] = time.time()

            # Binance Ticker 数据格式
            if 'e' in data and data['e'] == '24hrTicker':
                last_price = float(data['c'])
                price_change = float(data['p'])
                price_change_percent = float(data['P'])
                high_24h = float(data['h'])
                low_24h = float(data['l'])
                volume_24h = float(data['v'])
                open_24h = float(data['o'])
                event_time = data.get('E', int(time.time() * 1000))

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
                        'timestamp': event_time,
                        'last_update': time.time()
                    }

                # 重置重连计数（连接正常）
                self.reconnect_attempts[symbol] = 0

                # 定时更新显示
                current_time = time.time()
                if current_time - self.last_display_time >= self.display_interval:
                    self.last_display_time = current_time
                    self._display_all_prices()

        except Exception as e:
            logger.error(f"❌ 处理 {symbol} 消息时出错: {e}")

    def on_error(self, ws, error, symbol):
        """WebSocket 错误处理"""
        logger.error(f"❌ {symbol} WebSocket 错误: {error}")
        with self.lock:
            if symbol in self.connections:
                self.connections[symbol]['connected'] = False
        
        self._schedule_reconnect(symbol)

    def on_close(self, ws, close_status_code, close_msg, symbol):
        """WebSocket 连接关闭"""
        logger.warning(f"⚠️  {symbol} WebSocket 连接已关闭: {close_status_code} - {close_msg}")
        
        with self.lock:
            if symbol in self.connections:
                self.connections[symbol]['connected'] = False
        
        self._schedule_reconnect(symbol)

    def on_open(self, ws, symbol):
        """WebSocket 连接建立"""
        logger.info(f"✅ {symbol.upper()} 连接已建立")
        with self.lock:
            if symbol in self.connections:
                self.connections[symbol]['connected'] = True
                self.connections[symbol]['last_activity'] = time.time()

    def _schedule_reconnect(self, symbol):
        """安排重连"""
        if not self.is_running:
            return

        # 增加重连计数
        if symbol not in self.reconnect_attempts:
            self.reconnect_attempts[symbol] = 0
        self.reconnect_attempts[symbol] += 1

        if self.reconnect_attempts[symbol] <= self.max_reconnect_per_symbol:
            delay = min(2 ** self.reconnect_attempts[symbol], 30)  # 指数退避，最大30秒
            logger.info(f"🔄 {symbol} 将在 {delay} 秒后重连 (尝试 {self.reconnect_attempts[symbol]}/{self.max_reconnect_per_symbol})")
            
            # 使用定时器进行重连
            timer = threading.Timer(delay, self.create_connection, [symbol])
            timer.daemon = True
            timer.start()
        else:
            logger.error(f"❌ {symbol} 已达到最大重连次数 {self.max_reconnect_per_symbol}")

    def _check_connection_health(self):
        """检查连接健康状态"""
        if not self.is_running:
            return

        current_time = time.time()
        unhealthy_connections = []

        with self.lock:
            for symbol, conn_info in self.connections.items():
                # 检查连接状态和活动时间
                if (not conn_info['connected'] or 
                    current_time - conn_info['last_activity'] > self.connection_timeout):
                    unhealthy_connections.append(symbol)

        # 重新连接不健康的连接
        for symbol in unhealthy_connections:
            logger.warning(f"⚠️  {symbol} 连接不健康，尝试重新连接")
            self._schedule_reconnect(symbol)

    def _display_all_prices(self):
        """显示所有币种价格汇总（清屏刷新）"""
        import os
        os.system('cls' if os.name == 'nt' else 'clear')

        # 统计连接状态
        connected_count = 0
        with self.lock:
            for symbol in self.symbols:
                if (symbol in self.connections and 
                    self.connections[symbol]['connected'] and
                    symbol in self.price_data):
                    connected_count += 1

        print(f"\n{COLOR_BOLD}✅ Binance WebSocket 实时价格监控 - 稳定增强版{COLOR_RESET}")
        print(f"📡 交易对: {len(self.symbols)} 个 | {COLOR_GREEN}在线: {connected_count} 个{COLOR_RESET}")
        print(f"🕐 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 100)
        print(f"{COLOR_BLUE}{'排名':<4} | {'交易对':<12} | {'价格 (USDT)':<18} | {'24h变化':<12} | {'24h最高':<18} | {'状态':<8}{COLOR_RESET}")
        print("-" * 100)

        with self.lock:
            for idx, symbol in enumerate(self.symbols, 1):
                display_symbol = symbol.upper()
                
                if symbol in self.price_data:
                    data = self.price_data[symbol]
                    price = data['price']
                    change_percent = data['change_percent']
                    high_24h = data['high_24h']

                    # 格式化价格显示
                    if price >= 1000:
                        price_str = f"${price:,.2f}"
                        high_str = f"${high_24h:,.2f}"
                    elif price >= 1:
                        price_str = f"${price:,.4f}"
                        high_str = f"${high_24h:,.4f}"
                    else:
                        price_str = f"${price:,.6f}"
                        high_str = f"${high_24h:,.6f}"

                    # 格式化24h变化
                    if change_percent >= 0:
                        change_str = f"{COLOR_GREEN}▲{change_percent:+.2f}%{COLOR_RESET}"
                    else:
                        change_str = f"{COLOR_RED}▼{change_percent:.2f}%{COLOR_RESET}"

                    # 检查数据新鲜度
                    last_update = data.get('last_update', 0)
                    if time.time() - last_update < 10:  # 10秒内算实时
                        status = f"{COLOR_GREEN}实时{COLOR_RESET}"
                    else:
                        status = f"{COLOR_YELLOW}延迟{COLOR_RESET}"

                    print(f"{idx:<4} | {COLOR_BOLD}{display_symbol:<12}{COLOR_RESET} | {price_str:<18} | {change_str:<12} | {high_str:<18} | {status}")
                else:
                    # 检查连接状态
                    conn_status = f"{COLOR_RED}离线{COLOR_RESET}"
                    if symbol in self.connections:
                        if self.connections[symbol]['connected']:
                            conn_status = f"{COLOR_YELLOW}连接中{COLOR_RESET}"
                    
                    print(f"{idx:<4} | {COLOR_BOLD}{display_symbol:<12}{COLOR_RESET} | {COLOR_YELLOW}等待数据...{COLOR_RESET:<18} | {'--':<12} | {'--':<18} | {conn_status}")

        print("=" * 100)
        print(f"📊 数据来源: Binance WebSocket API | 市值排名: CoinGecko")
        print(f"💡 按 Ctrl+C 退出监控 | 版本: {__version__}")
        print("=" * 100)

    def start_health_check(self):
        """启动健康检查线程"""
        def health_check_loop():
            while self.is_running:
                self._check_connection_health()
                time.sleep(30)  # 每30秒检查一次
        
        health_thread = threading.Thread(
            target=health_check_loop,
            daemon=True,
            name="HealthCheck"
        )
        health_thread.start()
        return health_thread

    def start(self):
        """启动所有连接"""
        self.is_running = True
        
        print(f"{COLOR_BOLD}🚀 启动 Binance 实时价格监控 - 稳定增强版{COLOR_RESET}")
        print(f"💡 使用单独流API | 每个交易对独立连接")
        print(f"📊 动态获取市值前{self.top_n}名币种")
        print(f"🛡️  自动重连 | 健康检查 | 异常处理")
        print(f"📡 正在为 {len(self.symbols)} 个交易对创建连接...\n")

        # 为每个交易对创建连接
        connection_delay = 0.2  # 连接间延迟，避免同时创建过多连接
        for symbol in self.symbols:
            if not self.is_running:
                break
            self.create_connection(symbol)
            time.sleep(connection_delay)

        # 启动健康检查
        self.start_health_check()
        
        print(f"✅ 所有连接已创建，等待数据推送...\n")
        time.sleep(2)

        # 初始显示
        self._display_all_prices()

        # 主循环
        try:
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
        except Exception as e:
            logger.error(f"❌ 主循环异常: {e}")
            self.stop()

    def stop(self):
        """停止所有连接"""
        logger.info("🛑 正在停止监控...")
        self.is_running = False
        
        # 关闭所有WebSocket连接
        with self.lock:
            for symbol, conn_info in self.connections.items():
                try:
                    if conn_info['ws']:
                        conn_info['ws'].close()
                except Exception as e:
                    logger.error(f"❌ 关闭 {symbol} 连接时出错: {e}")
            
            self.connections.clear()
            self.price_data.clear()
        
        print(f"\n\n👋 已停止Binance实时价格监控")

    def run(self):
        """运行监控"""
        try:
            self.start()
        except Exception as e:
            logger.error(f"❌ 运行监控时发生异常: {e}")
            self.stop()


if __name__ == '__main__':
    # 设置全局超时
    import socket
    socket.setdefaulttimeout(15)
    
    # 创建并运行监控
    monitor = BinanceRealtime(top_n=20)
    
    try:
        monitor.run()
    except KeyboardInterrupt:
        print(f"\n👋 用户中断程序")
    except Exception as e:
        logger.error(f"❌ 程序异常: {e}")
    finally:
        monitor.stop()