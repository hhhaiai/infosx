#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX 实时虚拟币价格获取 - 修复版
动态获取市值前20名币种，确保交易对有效
依赖: pip install websocket-client requests
运行: python okx_realtime.py
"""

import json
import time
import threading
import requests
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
    """OKX WebSocket 实时价格监控 - 修复版"""

    def __init__(self, top_n=20):
        """
        初始化OKX WebSocket客户端

        Args:
            top_n (int): 获取市值前N名的币种（默认20）
        """
        # OKX公共频道WebSocket地址
        self.ws_url = "wss://ws.okx.com:8443/ws/v5/public"
        self.top_n = top_n
        self.symbols = []
        
        # 存储价格数据
        self.price_data = {}
        self.reconnect_count = 0
        self.max_reconnect = 5
        self.ws_connected = False
        self.last_display_time = 0
        
        # 初始化币种列表
        self._initialize_symbols()

    def _initialize_symbols(self):
        """初始化币种列表，带重试机制"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"🔄 第 {attempt + 1}/{max_retries} 次尝试获取市值前{self.top_n}名币种...")
                self.symbols = self._fetch_valid_okx_symbols()
                if self.symbols and len(self.symbols) >= 10:  # 至少获取10个有效交易对
                    print(f"✅ 成功获取 {len(self.symbols)} 个有效交易对")
                    return
                else:
                    print(f"⚠️ 第 {attempt + 1} 次获取失败，有效交易对数量不足")
                    if attempt < max_retries - 1:
                        time.sleep(2)
            except Exception as e:
                print(f"❌ 获取币种列表出错: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
        
        # 如果所有重试都失败，使用硬编码的备用列表
        print("⚠️ 使用备用币种列表")
        self.symbols = self._get_fallback_symbols()

    def _fetch_valid_okx_symbols(self):
        """
        获取有效的OKX交易对，确保交易对在OKX上真实存在
        """
        try:
            # 首先获取OKX所有可用的USDT交易对
            okx_symbols = self._fetch_okx_spot_symbols()
            if not okx_symbols:
                return None
            
            # 获取市值排名
            top_coins = self._fetch_market_cap_ranking(self.top_n * 2)  # 多获取一些
            if not top_coins:
                return list(okx_symbols)[:self.top_n]  # 返回OKX的前N个交易对
            
            # 匹配：找到市值排名中在OKX可用的交易对
            valid_symbols = []
            used_symbols = set()
            
            for coin in top_coins:
                # 尝试多种可能的符号匹配
                possible_symbols = self._get_possible_symbols(coin)
                
                for symbol in possible_symbols:
                    if symbol in okx_symbols and symbol not in used_symbols:
                        valid_symbols.append(symbol)
                        used_symbols.add(symbol)
                        break
                
                if len(valid_symbols) >= self.top_n:
                    break
            
            print(f"📊 匹配到 {len(valid_symbols)} 个有效交易对")
            return valid_symbols[:self.top_n]
            
        except Exception as e:
            print(f"❌ 获取有效交易对失败: {e}")
            return None

    def _fetch_okx_spot_symbols(self):
        """从OKX API获取所有可用的现货交易对"""
        try:
            print("📊 获取OKX现货交易对列表...")
            url = "https://www.okx.com/api/v5/public/instruments"
            params = {'instType': 'SPOT'}
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data['code'] != '0':
                return None
                
            # 获取所有USDT交易对
            usdt_pairs = set()
            for instrument in data['data']:
                inst_id = instrument['instId']
                if (inst_id.endswith('-USDT') and 
                    instrument['state'] == 'live' and 
                    not self._is_wrapped_token(inst_id)):
                    usdt_pairs.add(inst_id)
            
            print(f"✅ OKX返回 {len(usdt_pairs)} 个可用USDT交易对")
            return usdt_pairs
            
        except Exception as e:
            print(f"❌ 获取OKX交易对失败: {e}")
            return None

    def _is_wrapped_token(self, symbol):
        """检查是否为包装代币（通常流动性较差）"""
        wrapped_keywords = ['WSTETH', 'WBTC', 'WETH', 'WEETH', 'WLD', 'WBTC', 'W']
        return any(keyword in symbol for keyword in wrapped_keywords)

    def _fetch_market_cap_ranking(self, limit=40):
        """获取市值排名"""
        try:
            print("📈 获取市值排名...")
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
                    not self._is_wrapped_token(coin['symbol'].upper())):
                    filtered_coins.append({
                        'id': coin['id'],
                        'symbol': coin['symbol'].upper(),
                        'name': coin['name'],
                        'market_cap_rank': coin['market_cap_rank']
                    })
            
            print(f"✅ 获取到 {len(filtered_coins)} 个有效币种排名")
            return filtered_coins
            
        except Exception as e:
            print(f"❌ 获取市值排名失败: {e}")
            return None

    def _get_possible_symbols(self, coin):
        """为币种生成可能的交易对符号"""
        symbol = coin['symbol'].upper()
        name = coin['name'].upper()
        
        possible_symbols = []
        
        # 主要使用符号
        possible_symbols.append(f"{symbol}-USDT")
        
        # 对于名称与符号不同的币种，也尝试名称
        if symbol != name and len(name) <= 8:
            # 移除常见前缀后缀
            clean_name = name.replace(' ', '')
            for prefix in ['THE ', 'NEW ', 'OLD ']:
                if clean_name.startswith(prefix):
                    clean_name = clean_name[len(prefix):]
            
            if clean_name and clean_name != symbol:
                possible_symbols.append(f"{clean_name}-USDT")
        
        # 特殊处理一些知名币种
        special_cases = {
            'BTC': ['BTC-USDT', 'XBT-USDT'],
            'ETH': ['ETH-USDT'],
            'BNB': ['BNB-USDT'],
            'XRP': ['XRP-USDT'],
            'ADA': ['ADA-USDT'],
            'SOL': ['SOL-USDT'],
            'DOT': ['DOT-USDT'],
            'DOGE': ['DOGE-USDT', 'XDG-USDT'],
            'MATIC': ['MATIC-USDT', 'POL-USDT'],
            'LTC': ['LTC-USDT'],
            'BCH': ['BCH-USDT', 'BCC-USDT'],
            'LINK': ['LINK-USDT'],
            'XLM': ['XLM-USDT'],
            'UNI': ['UNI-USDT'],
            'ATOM': ['ATOM-USDT'],
            'ETC': ['ETC-USDT'],
            'XMR': ['XMR-USDT'],
            'XTZ': ['XTZ-USDT'],
            'EOS': ['EOS-USDT'],
            'AAVE': ['AAVE-USDT'],
            'ALGO': ['ALGO-USDT'],
            'TRX': ['TRX-USDT'],
            'FIL': ['FIL-USDT'],
            'AVAX': ['AVAX-USDT'],
            'ICP': ['ICP-USDT'],
            'APE': ['APE-USDT'],
            'NEAR': ['NEAR-USDT'],
            'QNT': ['QNT-USDT'],
            'CHZ': ['CHZ-USDT'],
            'FTM': ['FTM-USDT'],
            'GRT': ['GRT-USDT'],
            'SAND': ['SAND-USDT'],
            'MANA': ['MANA-USDT'],
            'ENJ': ['ENJ-USDT'],
            'BAT': ['BAT-USDT'],
            'ZEC': ['ZEC-USDT'],
            'DASH': ['DASH-USDT'],
            'ZIL': ['ZIL-USDT'],
            'IOTA': ['IOTA-USDT', 'MIOTA-USDT'],
        }
        
        if symbol in special_cases:
            possible_symbols.extend(special_cases[symbol])
        
        return possible_symbols

    def _get_fallback_symbols(self):
        """获取备用币种列表（确保在OKX上存在）"""
        fallback_symbols = [
            "BTC-USDT", "ETH-USDT", "BNB-USDT", "SOL-USDT", "XRP-USDT",
            "ADA-USDT", "DOGE-USDT", "AVAX-USDT", "DOT-USDT", "TRX-USDT",
            "MATIC-USDT", "LINK-USDT", "LTC-USDT", "BCH-USDT", "ATOM-USDT",
            "ETC-USDT", "XLM-USDT", "FIL-USDT", "APT-USDT", "ARB-USDT"
        ]
        return fallback_symbols[:self.top_n]

    def on_message(self, ws, message):
        """处理WebSocket消息"""
        try:
            data = json.loads(message)

            # 处理订阅响应
            if 'event' in data:
                if data['event'] == 'subscribe':
                    print(f"✅ 订阅成功: {data['arg']['channel']} - {data['arg']['instId']}")
                elif data['event'] == 'error':
                    print(f"❌ 订阅错误: {data.get('msg', '未知错误')} - {data.get('arg', {})}")
                return

            # 处理ticker数据推送
            if 'data' in data and isinstance(data['data'], list):
                for ticker_data in data['data']:
                    self._process_ticker_data(ticker_data)

        except Exception as e:
            print(f"\n❌ 处理消息时出错: {e}")

    def _process_ticker_data(self, data):
        """处理ticker数据"""
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
                'timestamp': timestamp,
                'last_update': time.time()
            }

            # 定时更新显示（每2秒）
            current_time = time.time()
            if current_time - self.last_display_time >= 2:
                self.last_display_time = current_time
                self._display_all_prices()

        except (KeyError, ValueError) as e:
            print(f"❌ 处理ticker数据出错: {e}")

    def _display_all_prices(self):
        """显示所有币种价格汇总（清屏刷新）"""
        import os
        os.system('cls' if os.name == 'nt' else 'clear')

        online_count = self._get_online_count()
        
        print(f"\n{COLOR_BOLD}✅ OKX WebSocket 实时价格监控 - 动态市值前{self.top_n}名{COLOR_RESET}")
        print(f"📡 已订阅 {len(self.symbols)} 个交易对 | {COLOR_GREEN}在线 {online_count} 个{COLOR_RESET}")
        print(f"🕐 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 100)
        print(f"{COLOR_BLUE}{'排名':<4} | {'交易对':<12} | {'价格 (USDT)':<18} | {'24h变化':<12} | {'24h最高':<18} | {'状态':<8}{COLOR_RESET}")
        print("-" * 100)

        for idx, symbol in enumerate(self.symbols, 1):
            if symbol in self.price_data:
                data = self.price_data[symbol]
                price = data['last']
                change_24h = data['change_24h']
                high_24h = data['high']

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
                if change_24h >= 0:
                    change_str = f"{COLOR_GREEN}▲{change_24h:+.2f}%{COLOR_RESET}"
                else:
                    change_str = f"{COLOR_RED}▼{change_24h:.2f}%{COLOR_RESET}"

                # 检查数据新鲜度
                last_update = data.get('last_update', 0)
                if time.time() - last_update < 10:  # 10秒内更新的数据
                    status = f"{COLOR_GREEN}实时{COLOR_RESET}"
                else:
                    status = f"{COLOR_YELLOW}延迟{COLOR_RESET}"

                print(f"{idx:<4} | {COLOR_BOLD}{symbol:<12}{COLOR_RESET} | {price_str:<18} | {change_str:<12} | {high_str:<18} | {status}")
            else:
                print(f"{idx:<4} | {COLOR_BOLD}{symbol:<12}{COLOR_RESET} | {COLOR_YELLOW}等待数据...{COLOR_RESET:<18} | {'--':<12} | {'--':<18} | {COLOR_RED}离线{COLOR_RESET}")

        print("=" * 100)
        print(f"📊 数据来源: OKX官方WebSocket API | 市值排名: CoinGecko")
        print(f"💡 按 Ctrl+C 退出监控 | 自动重连: {self.reconnect_count}/{self.max_reconnect}")
        print("=" * 100)

    def _get_online_count(self):
        """获取在线币种数量"""
        count = 0
        current_time = time.time()
        for symbol in self.symbols:
            if symbol in self.price_data:
                last_update = self.price_data[symbol].get('last_update', 0)
                if current_time - last_update < 30:  # 30秒内算在线
                    count += 1
        return count

    def on_error(self, ws, error):
        """WebSocket错误处理"""
        print(f"\n❌ WebSocket错误: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """WebSocket连接关闭"""
        self.ws_connected = False
        print(f"\n\n⚠️  OKX WebSocket连接已关闭")
        print(f"状态码: {close_status_code}, 消息: {close_msg}")

        if self.reconnect_count < self.max_reconnect:
            print(f"🔄 第 {self.reconnect_count + 1}/{self.max_reconnect} 次重连将在 5 秒后进行...")
            time.sleep(5)
            self.reconnect_count += 1
            self.start()
        else:
            print(f"\n❌ 已达到最大重连次数 {self.max_reconnect}，程序退出")

    def on_open(self, ws):
        """WebSocket连接建立"""
        self.ws_connected = True
        self.reconnect_count = 0
        self.last_display_time = 0

        print(f"\n✅ OKX WebSocket连接已建立")
        print(f"📡 正在订阅 {len(self.symbols)} 个交易对的ticker频道...")

        # 分批订阅，避免消息过大
        batch_size = 5  # 更小的批次避免订阅错误
        successful_subs = 0
        
        for i in range(0, len(self.symbols), batch_size):
            batch = self.symbols[i:i + batch_size]
            subscribe_data = {
                "op": "subscribe",
                "args": [{"channel": "tickers", "instId": symbol} for symbol in batch]
            }
            
            try:
                ws.send(json.dumps(subscribe_data))
                print(f"✅ 已发送批次 {i//batch_size + 1}/{(len(self.symbols)-1)//batch_size + 1}")
                time.sleep(0.5)  # 增加延迟避免速率限制
                successful_subs += len(batch)
            except Exception as e:
                print(f"❌ 发送批次 {i//batch_size + 1} 失败: {e}")

        print(f"✅ 订阅请求发送完成，成功订阅 {successful_subs} 个交易对")
        print("⏳ 等待数据推送...\n")

    def start(self):
        """启动WebSocket连接"""
        try:
            ws = WebSocketApp(
                self.ws_url,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )
            ws.run_forever(ping_interval=20, ping_timeout=10)
        except Exception as e:
            print(f"❌ 启动WebSocket失败: {e}")
            if self.reconnect_count < self.max_reconnect:
                time.sleep(5)
                self.reconnect_count += 1
                self.start()

    def run(self):
        """运行监控"""
        print("🚀 启动OKX实时虚拟币价格监控 - 修复版")
        print("💡 使用OKX WebSocket API | Ticker频道推送")
        print("📊 动态匹配市值前20名币种 | 确保交易对有效")
        print("🛡️  自动重连 | 数据新鲜度检测")
        print("⌨️  按 Ctrl+C 退出\n")

        try:
            self.start()
        except KeyboardInterrupt:
            print(f"\n\n👋 已停止OKX实时价格监控")
            if self.ws_connected:
                print("✅ WebSocket连接已正常关闭")


if __name__ == '__main__':
    # 设置更长的超时时间
    import socket
    socket.setdefaulttimeout(15)
    
    monitor = OKXRealtime(top_n=20)
    monitor.run()