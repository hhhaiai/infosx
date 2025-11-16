import asyncio
import websockets
import json
import sqlite3
from datetime import datetime, timedelta
import requests
import time
import logging
from typing import List, Dict, Optional
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FixedCryptoCollector:
    """修复版的加密货币数据收集器 - 修复WebSocket问题"""
    
    BINANCE_REST = "https://api.binance.com/api/v3"
    BINANCE_WS = "wss://stream.binance.com:9443/ws"
    
    def __init__(self, db_path="crypto_fixed.db"):
        self.db_path = db_path
        self.trade_buffer = []
        self.buffer_size = 50
        self.reconnect_delay = 5
        self.max_reconnect_attempts = 10
        self._init_database()
    
    def _init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 币种信息表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS symbols (
                symbol TEXT PRIMARY KEY,
                base_asset TEXT,
                quote_asset TEXT,
                status TEXT,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # K线数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS klines (
                symbol TEXT,
                open_time INTEGER,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                close_time INTEGER,
                quote_volume REAL,
                trades INTEGER,
                interval TEXT,
                PRIMARY KEY (symbol, open_time, interval)
            )
        ''')
        
        # 实时交易表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS realtime_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                trade_id INTEGER,
                timestamp_ms INTEGER,
                price REAL,
                quantity REAL,
                buyer_order_id INTEGER,
                seller_order_id INTEGER,
                trade_time DATETIME,
                is_buyer_maker BOOLEAN,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_symbol_time ON realtime_trades(symbol, timestamp_ms)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_klines_symbol_interval ON klines(symbol, interval)')
        
        conn.commit()
        conn.close()
        logger.info("✅ 数据库初始化完成")
    
    def get_top_symbols(self, limit: int = 50) -> List[str]:
        """获取交易量前N的交易对"""
        url = f"{self.BINANCE_REST}/ticker/24hr"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            tickers = response.json()
            
            # 按交易量排序，选择USDT交易对
            usdt_pairs = [
                t for t in tickers 
                if t['symbol'].endswith('USDT') and 'USDT' not in t['symbol'].replace('USDT', '')
            ]
            
            # 按quoteVolume排序
            sorted_pairs = sorted(
                usdt_pairs, 
                key=lambda x: float(x['quoteVolume']), 
                reverse=True
            )[:limit]
            
            symbols = [pair['symbol'] for pair in sorted_pairs]
            
            # 保存符号信息
            self._save_symbols_info(sorted_pairs)
            
            logger.info(f"✅ 获取前{limit}名交易对: {', '.join(symbols[:5])}...")
            return symbols
            
        except Exception as e:
            logger.error(f"❌ 获取交易对失败: {e}")
            # 返回默认交易对
            default_symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT']
            logger.info(f"使用默认交易对: {default_symbols}")
            return default_symbols
    
    def _save_symbols_info(self, tickers: List[Dict]):
        """保存交易对信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for ticker in tickers:
            symbol = ticker['symbol']
            base_asset = symbol.replace('USDT', '')
            
            cursor.execute('''
                INSERT OR REPLACE INTO symbols (symbol, base_asset, quote_asset, status)
                VALUES (?, ?, ?, ?)
            ''', (symbol, base_asset, 'USDT', 'TRADING'))
        
        conn.commit()
        conn.close()
    
    def get_historical_klines_batch(self, symbols: List[str], interval: str = '1m', days_back: int = 7):
        """批量获取多个交易对的历史数据 - 修复版"""
        logger.info(f"📥 开始批量获取 {len(symbols)} 个交易对的{interval}K线数据 ({days_back}天)...")
        
        successful = 0
        for i, symbol in enumerate(symbols, 1):
            try:
                logger.info(f"进度: {i}/{len(symbols)} - 获取 {symbol} 数据")
                klines = self._get_historical_klines_fixed(symbol, interval, days_back)
                
                if klines and len(klines) > 0:
                    successful += 1
                    logger.info(f"✅ {symbol}: 成功获取 {len(klines)} 条K线")
                    # 立即保存
                    self._save_historical_klines(symbol, interval, klines)
                else:
                    logger.warning(f"⚠️  {symbol}: 获取数据为空")
                
                # 速率限制
                time.sleep(0.3)
                
            except Exception as e:
                logger.error(f"❌ {symbol}: 获取失败 - {e}")
                time.sleep(1)
        
        logger.info(f"🎉 批量获取完成: {successful}/{len(symbols)} 成功")
        return successful
    
    def _get_historical_klines_fixed(self, symbol: str, interval: str = '1m', days_back: int = 7) -> Optional[List]:
        """修复版的历史K线数据获取"""
        url = f"{self.BINANCE_REST}/klines"
        
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(days=days_back)).timestamp() * 1000)
        
        logger.info(f"  时间范围: {datetime.fromtimestamp(start_time/1000)} 到 {datetime.fromtimestamp(end_time/1000)}")
        
        all_klines = []
        current_start = start_time
        
        max_requests = 50  # 防止无限循环
        request_count = 0
        
        while current_start < end_time and request_count < max_requests:
            params = {
                'symbol': symbol.upper(),
                'interval': interval,
                'startTime': current_start,
                'endTime': end_time,
                'limit': 1000
            }
            
            try:
                logger.debug(f"  请求参数: {params}")
                response = requests.get(url, params=params, timeout=15)
                
                if response.status_code == 429:
                    logger.warning(f"⚠️  速率限制，等待10秒...")
                    time.sleep(10)
                    continue
                elif response.status_code == 418:  # IP被禁
                    logger.error(f"❌ IP被暂时禁止，等待60秒")
                    time.sleep(60)
                    continue
                elif response.status_code != 200:
                    logger.error(f"❌ HTTP {response.status_code}: {response.text}")
                    break
                
                klines = response.json()
                
                if not klines:
                    logger.info(f"  {symbol}: 没有更多数据")
                    break
                
                all_klines.extend(klines)
                
                # 更新起始时间为最后一条的收盘时间 + 1ms
                current_start = klines[-1][6] + 1
                request_count += 1
                
                logger.info(f"  {symbol}: 已获取 {len(klines)} 条，总计 {len(all_klines)} 条")
                
                # 严格的速率限制
                time.sleep(0.2)
                
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ 网络错误: {e}")
                time.sleep(2)
            except Exception as e:
                logger.error(f"❌ 获取{symbol}数据失败: {e}")
                break
        
        return all_klines
    
    def _save_historical_klines(self, symbol: str, interval: str, klines: List):
        """保存历史K线数据 - 修复版"""
        if not klines:
            logger.warning(f"⚠️  {symbol}: 没有数据可保存")
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            data = [
                (
                    symbol, int(k[0]), float(k[1]), float(k[2]), float(k[3]),
                    float(k[4]), float(k[5]), int(k[6]), float(k[7]), int(k[8]), interval
                )
                for k in klines
            ]
            
            cursor.executemany('''
                INSERT OR REPLACE INTO klines 
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ''', data)
            
            conn.commit()
            logger.info(f"💾 {symbol}: 成功保存 {len(klines)} 条K线到数据库")
            
        except Exception as e:
            logger.error(f"❌ 保存{symbol}数据失败: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    async def collect_realtime_trades(self, symbols: List[str]):
        """收集实时交易数据 - 修复WebSocket问题"""
        reconnect_attempts = 0
        
        while reconnect_attempts < self.max_reconnect_attempts:
            try:
                logger.info(f"🔄 连接尝试 {reconnect_attempts + 1}/{self.max_reconnect_attempts}")
                await self._start_websocket_fixed(symbols)
                
            except websockets.exceptions.ConnectionClosed:
                reconnect_attempts += 1
                logger.warning(f"🔌 WebSocket连接断开，{self.reconnect_delay}秒后重试...")
                await asyncio.sleep(self.reconnect_delay)
                
            except Exception as e:
                reconnect_attempts += 1
                logger.error(f"❌ WebSocket错误: {e}")
                await asyncio.sleep(self.reconnect_delay)
        
        logger.error("🔴 达到最大重连次数，停止实时数据收集")
    
    async def _start_websocket_fixed(self, symbols: List[str]):
        """修复版的WebSocket连接处理"""
        streams = [f"{symbol.lower()}@trade" for symbol in symbols]
        combined_stream = "/".join(streams)
        url = f"{self.BINANCE_WS}/{combined_stream}"
        
        logger.info(f"🚀 连接WebSocket，监控 {len(symbols)} 个交易对: {', '.join(symbols[:3])}...")
        
        async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
            logger.info("✅ WebSocket连接成功，开始接收实时数据...")
            
            trade_count = 0
            last_log_time = time.time()
            
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=30)
                    
                    # 调试：打印原始消息（前200字符）
                    logger.debug(f"📨 收到消息: {msg[:200]}...")
                    
                    data = json.loads(msg)
                    
                    # 修复：检查消息类型，只处理交易消息
                    if data.get('e') != 'trade':
                        logger.debug(f"跳过非交易消息: {data.get('e')}")
                        continue
                    
                    # 修复：使用更安全的字段访问方式
                    trade = {
                        'symbol': data.get('s', 'UNKNOWN'),
                        'trade_id': data.get('t', 0),
                        'timestamp_ms': data.get('T', 0),
                        'price': float(data.get('p', 0)),
                        'quantity': float(data.get('q', 0)),
                        'buyer_order_id': data.get('b', 0),
                        'seller_order_id': data.get('a', 0),
                        'trade_time': datetime.fromtimestamp(data.get('T', 0) / 1000),
                        'is_buyer_maker': data.get('m', False)
                    }
                    
                    # 验证必要字段
                    if trade['symbol'] == 'UNKNOWN' or trade['timestamp_ms'] == 0:
                        logger.warning(f"⚠️ 跳过无效交易数据: {trade}")
                        continue
                    
                    self.trade_buffer.append(trade)
                    trade_count += 1
                    
                    # 定期显示进度
                    current_time = time.time()
                    if current_time - last_log_time >= 10:  # 每10秒日志一次
                        logger.info(f"📈 已接收 {trade_count} 笔实时交易")
                        last_log_time = current_time
                    
                    # 缓冲区满时保存
                    if len(self.trade_buffer) >= self.buffer_size:
                        await self._flush_realtime_buffer_async()
                        
                except asyncio.TimeoutError:
                    logger.warning("⏰ WebSocket接收超时，发送ping...")
                    await ws.ping()
                    continue
                except json.JSONDecodeError as e:
                    logger.error(f"❌ JSON解析错误: {e}")
                    continue
                except Exception as e:
                    logger.error(f"❌ 处理消息错误: {e}")
                    # 打印错误详情但不中断循环
                    continue
    
    async def _flush_realtime_buffer_async(self):
        """异步保存实时交易数据"""
        if not self.trade_buffer:
            return
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._flush_realtime_buffer_sync)
    
    def _flush_realtime_buffer_sync(self):
        """同步保存实时交易数据"""
        if not self.trade_buffer:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.executemany('''
                INSERT INTO realtime_trades 
                (symbol, trade_id, timestamp_ms, price, quantity, buyer_order_id, seller_order_id, trade_time, is_buyer_maker)
                VALUES (?,?,?,?,?,?,?,?,?)
            ''', [
                (t['symbol'], t['trade_id'], t['timestamp_ms'], t['price'], 
                 t['quantity'], t['buyer_order_id'], t['seller_order_id'], 
                 t['trade_time'], t['is_buyer_maker'])
                for t in self.trade_buffer
            ])
            
            conn.commit()
            logger.info(f"💾 保存 {len(self.trade_buffer)} 笔交易到数据库")
            
        except Exception as e:
            logger.error(f"❌ 保存交易数据失败: {e}")
            conn.rollback()
        finally:
            conn.close()
            self.trade_buffer.clear()
    
    def get_data_summary(self):
        """查看详细数据统计"""
        conn = sqlite3.connect(self.db_path)
        
        print("\n" + "="*80)
        print("📊 详细数据统计")
        print("="*80)
        
        # 交易对统计
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM symbols")
        symbol_count = cursor.fetchone()[0]
        print(f"\n🗂️  交易对数量: {symbol_count}")
        
        # K线数据统计
        cursor.execute('''
            SELECT symbol, interval, COUNT(*) as count, 
                   MIN(open_time) as first_time, MAX(open_time) as last_time
            FROM klines 
            GROUP BY symbol, interval
        ''')
        klines_stats = cursor.fetchall()
        
        if klines_stats:
            print("\n📈 K线数据统计:")
            for symbol, interval, count, first_time, last_time in klines_stats:
                first_dt = datetime.fromtimestamp(first_time/1000)
                last_dt = datetime.fromtimestamp(last_time/1000)
                print(f"  {symbol} ({interval}): {count:,} 条 | {first_dt.strftime('%Y-%m-%d %H:%M')} 到 {last_dt.strftime('%Y-%m-%d %H:%M')}")
        else:
            print("\n❌ 没有K线数据")
        
        # 实时交易统计
        cursor.execute('''
            SELECT symbol, COUNT(*) as count, 
                   MIN(timestamp_ms) as first_trade, MAX(timestamp_ms) as last_trade
            FROM realtime_trades 
            GROUP BY symbol
        ''')
        trades_stats = cursor.fetchall()
        
        if trades_stats:
            print("\n⚡ 实时交易数据:")
            for symbol, count, first_trade, last_trade in trades_stats:
                first_dt = datetime.fromtimestamp(first_trade/1000)
                last_dt = datetime.fromtimestamp(last_trade/1000)
                print(f"  {symbol}: {count:,} 笔交易 | {first_dt.strftime('%Y-%m-%d %H:%M:%S')} 到 {last_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print("\n❌ 没有实时交易数据")
        
        conn.close()


async def run_complete_collection():
    """运行完整的数据收集（历史 + 实时）"""
    collector = FixedCryptoCollector()
    
    print("\n💰 完整加密货币数据收集器")
    print("="*70)
    
    # 获取前N名币种
    limit = int(input("处理前多少名币种? (默认10): ") or "10")
    days = int(input("获取多少天历史数据? (默认1): ") or "1")
    
    symbols = collector.get_top_symbols(limit)
    
    print(f"\n🎯 目标币种: {', '.join(symbols)}")
    
    # 第一步：获取历史数据
    print("\n📥 第一步: 获取历史数据...")
    success_count = collector.get_historical_klines_batch(symbols, '1m', days)
    
    if success_count == 0:
        print("❌ 历史数据获取失败，无法继续实时监控")
        return
    
    # 显示数据统计
    collector.get_data_summary()
    
    # 确认是否继续实时监控
    continue_realtime = input("\n是否开始实时监控? (y/n, 默认y): ").strip().lower()
    if continue_realtime not in ['', 'y', 'yes']:
        print("👋 程序结束")
        return
    
    # 第二步：实时监控
    print("\n📡 第二步: 开始实时监控...")
    print("按 Ctrl+C 停止实时监控")
    
    try:
        await collector.collect_realtime_trades(symbols)
    except KeyboardInterrupt:
        print("\n\n🛑 用户停止实时监控")
    
    # 最终数据统计
    print("\n" + "="*70)
    print("📊 最终数据统计")
    print("="*70)
    collector.get_data_summary()


async def main():
    """主程序"""
    collector = FixedCryptoCollector()
    
    print("\n💰 修复版加密货币数据收集器")
    print("="*70)
    print("1. 只获取历史数据")
    print("2. 只实时监控")
    print("3. 历史 + 实时（完整收集）")
    print("4. 查看数据统计")
    print("="*70)
    
    choice = input("\n请选择 (1-4): ").strip()
    
    if choice == '1':
        limit = int(input("获取前多少名币种? (默认10): ") or "10")
        days = int(input("获取多少天历史数据? (默认1): ") or "1")
        interval = input("K线间隔? (1m/5m/1h/1d, 默认1m): ") or "1m"
        
        symbols = collector.get_top_symbols(limit)
        collector.get_historical_klines_batch(symbols, interval, days)
        collector.get_data_summary()
    
    elif choice == '2':
        limit = int(input("实时监控前多少名币种? (默认5): ") or "5")
        symbols = collector.get_top_symbols(limit)
        await collector.collect_realtime_trades(symbols)
    
    elif choice == '3':
        await run_complete_collection()
    
    elif choice == '4':
        collector.get_data_summary()
    
    else:
        print("❌ 无效选择")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 程序被用户中断")
    except Exception as e:
        print(f"\n💥 程序异常: {e}")