"""
trades 表：存储毫秒级原始交易数据
ohlcv_1s 表：存储秒级聚合的OHLCV数据

"""
import asyncio
import websockets
import json
import sqlite3
from datetime import datetime
import logging
from collections import defaultdict
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MillisecondCryptoCollector:
    """毫秒级加密货币数据收集器 - 修复版"""
    
    BINANCE_WS = "wss://stream.binance.com:9443/ws"
    
    def __init__(self, db_path="crypto_ms.db"):
        self.db_path = db_path
        self.trade_buffer = []
        self.ohlcv_buffer = defaultdict(dict)  # 用于实时聚合OHLCV数据
        self.buffer_size = 100
        self._init_database()
    
    def _init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建实时交易表（毫秒级）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                symbol TEXT,
                timestamp_ms INTEGER,
                price REAL,
                quantity REAL,
                trade_time DATETIME,
                PRIMARY KEY (symbol, timestamp_ms)
            )
        ''')
        
        # 创建聚合表（每秒OHLCV）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ohlcv_1s (
                symbol TEXT,
                timestamp INTEGER,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                trade_count INTEGER,
                PRIMARY KEY (symbol, timestamp)
            )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol_time ON trades(symbol, timestamp_ms)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trade_time ON trades(trade_time)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_time ON ohlcv_1s(symbol, timestamp)')
        
        conn.commit()
        conn.close()
        logger.info("✅ 数据库初始化完成")
    
    def get_top_symbols(self, n=50):
        """获取Top N交易对"""
        top_symbols = [
            'btcusdt', 'ethusdt', 'bnbusdt', 'solusdt', 'xrpusdt',
            'adausdt', 'dogeusdt', 'dotusdt', 'maticusdt', 'avaxusdt',
            'linkusdt', 'uniusdt', 'atomusdt', 'ltcusdt', 'etcusdt',
            'filusdt', 'trxusdt', 'xlmusdt', 'vetusdt', 'algousdt'
        ]
        return top_symbols[:n]
    
    async def collect_trades(self, symbols):
        """收集实时交易数据并实时聚合OHLCV"""
        streams = [f"{symbol}@trade" for symbol in symbols]
        params = "/".join(streams)
        url = f"{self.BINANCE_WS}/{params}"
        
        logger.info(f"🚀 开始连接币安WebSocket...")
        logger.info(f"📊 监听 {len(symbols)} 个交易对: {', '.join(symbols[:5])}...")
        
        # 上一次聚合的时间戳
        last_aggregation_time = int(time.time())
        
        try:
            async with websockets.connect(url) as ws:
                logger.info("✅ WebSocket连接成功！开始接收数据...")
                
                trade_count = 0
                
                while True:
                    try:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        
                        # 解析交易数据
                        trade = {
                            'symbol': data['s'],
                            'timestamp_ms': data['T'],
                            'price': float(data['p']),
                            'quantity': float(data['q']),
                            'trade_time': datetime.fromtimestamp(data['T'] / 1000)
                        }
                        
                        # 添加到缓冲区
                        self.trade_buffer.append(trade)
                        trade_count += 1
                        
                        # 实时聚合OHLCV数据
                        self._update_ohlcv_buffer(trade)
                        
                        # 实时显示
                        if trade_count % 10 == 0:
                            logger.info(f"📈 {trade['symbol']}: ${trade['price']:.4f} | "
                                      f"数量: {trade['quantity']:.6f} | "
                                      f"时间: {trade['trade_time'].strftime('%H:%M:%S.%f')[:-3]}")
                        
                        # 批量写入数据库
                        if len(self.trade_buffer) >= self.buffer_size:
                            self._flush_trade_buffer()
                            logger.info(f"💾 已保存 {trade_count} 笔交易到数据库")
                        
                        # 每秒聚合一次OHLCV数据
                        current_time = int(time.time())
                        if current_time > last_aggregation_time:
                            self._flush_ohlcv_buffer()
                            last_aggregation_time = current_time
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ JSON解析错误: {e}")
                        continue
                    except KeyError as e:
                        logger.error(f"❌ 数据格式错误: {e}")
                        continue
                        
        except websockets.exceptions.WebSocketException as e:
            logger.error(f"❌ WebSocket连接错误: {e}")
        except Exception as e:
            logger.error(f"❌ 未知错误: {e}")
        finally:
            # 确保退出时保存剩余数据
            if self.trade_buffer:
                self._flush_trade_buffer()
            if self.ohlcv_buffer:
                self._flush_ohlcv_buffer()
            logger.info("💾 已保存所有剩余数据")
    
    def _update_ohlcv_buffer(self, trade):
        """更新OHLCV缓冲区"""
        symbol = trade['symbol']
        timestamp_sec = trade['timestamp_ms'] // 1000  # 转换为秒级时间戳
        price = trade['price']
        quantity = trade['quantity']
        
        # 获取或初始化该秒的OHLCV数据
        if timestamp_sec not in self.ohlcv_buffer[symbol]:
            self.ohlcv_buffer[symbol][timestamp_sec] = {
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': quantity,
                'trade_count': 1
            }
        else:
            ohlcv = self.ohlcv_buffer[symbol][timestamp_sec]
            ohlcv['high'] = max(ohlcv['high'], price)
            ohlcv['low'] = min(ohlcv['low'], price)
            ohlcv['close'] = price
            ohlcv['volume'] += quantity
            ohlcv['trade_count'] += 1
    
    def _flush_trade_buffer(self):
        """批量写入交易数据到数据库"""
        if not self.trade_buffer:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.executemany('''
                INSERT OR REPLACE INTO trades 
                (symbol, timestamp_ms, price, quantity, trade_time)
                VALUES (?, ?, ?, ?, ?)
            ''', [
                (t['symbol'], t['timestamp_ms'], t['price'], t['quantity'], t['trade_time'])
                for t in self.trade_buffer
            ])
            
            conn.commit()
            self.trade_buffer.clear()
            
        except Exception as e:
            logger.error(f"❌ 交易数据写入错误: {e}")
        finally:
            conn.close()
    
    def _flush_ohlcv_buffer(self):
        """批量写入OHLCV数据到数据库"""
        if not self.ohlcv_buffer:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            data_to_insert = []
            for symbol, timestamps in self.ohlcv_buffer.items():
                for timestamp_sec, ohlcv in timestamps.items():
                    data_to_insert.append((
                        symbol,
                        timestamp_sec,
                        ohlcv['open'],
                        ohlcv['high'],
                        ohlcv['low'],
                        ohlcv['close'],
                        ohlcv['volume'],
                        ohlcv['trade_count']
                    ))
            
            cursor.executemany('''
                INSERT OR REPLACE INTO ohlcv_1s 
                (symbol, timestamp, open, high, low, close, volume, trade_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', data_to_insert)
            
            conn.commit()
            logger.info(f"📊 已聚合 {len(data_to_insert)} 个OHLCV数据点")
            self.ohlcv_buffer.clear()
            
        except Exception as e:
            logger.error(f"❌ OHLCV数据写入错误: {e}")
        finally:
            conn.close()
    
    def get_statistics(self):
        """获取数据库统计信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 总交易数
        cursor.execute("SELECT COUNT(*) FROM trades")
        total_trades = cursor.fetchone()[0]
        
        # OHLCV数据统计
        cursor.execute("SELECT COUNT(*) FROM ohlcv_1s")
        total_ohlcv = cursor.fetchone()[0]
        
        # 每个币种的交易数
        cursor.execute("""
            SELECT symbol, COUNT(*) as count, 
                   MIN(price) as min_price, 
                   MAX(price) as max_price,
                   AVG(price) as avg_price
            FROM trades
            GROUP BY symbol
            ORDER BY count DESC
            LIMIT 10
        """)
        
        symbol_stats = cursor.fetchall()
        
        conn.close()
        
        print("\n" + "="*70)
        print("📊 数据统计")
        print("="*70)
        print(f"总交易笔数 (trades表): {total_trades:,}")
        print(f"总OHLCV数据点 (ohlcv_1s表): {total_ohlcv:,}")
        print(f"\nTop 10 活跃交易对:")
        print("-"*70)
        print(f"{'交易对':<12} {'交易数':<12} {'最低价':<15} {'最高价':<15} {'平均价':<15}")
        print("-"*70)
        
        for symbol, count, min_p, max_p, avg_p in symbol_stats:
            print(f"{symbol:<12} {count:<12,} ${min_p:<14.4f} ${max_p:<14.4f} ${avg_p:<14.4f}")
        
        print("="*70)
    
    def generate_historical_ohlcv(self):
        """从已有的trades数据生成历史OHLCV数据（一次性操作）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        logger.info("🔄 从历史交易数据生成OHLCV数据...")
        
        try:
            # 删除现有的OHLCV数据
            cursor.execute("DELETE FROM ohlcv_1s")
            
            # 从trades表聚合生成OHLCV数据
            cursor.execute('''
                INSERT INTO ohlcv_1s
                SELECT 
                    symbol,
                    timestamp_ms / 1000 as timestamp,
                    FIRST_VALUE(price) OVER (PARTITION BY symbol, timestamp_ms / 1000 ORDER BY timestamp_ms) as open,
                    MAX(price) as high,
                    MIN(price) as low,
                    LAST_VALUE(price) OVER (PARTITION BY symbol, timestamp_ms / 1000 ORDER BY timestamp_ms) as close,
                    SUM(quantity) as volume,
                    COUNT(*) as trade_count
                FROM trades
                GROUP BY symbol, timestamp_ms / 1000
            ''')
            
            conn.commit()
            
            cursor.execute("SELECT COUNT(*) FROM ohlcv_1s")
            count = cursor.fetchone()[0]
            
            logger.info(f"✅ 成功生成 {count} 个历史OHLCV数据点")
            
        except Exception as e:
            logger.error(f"❌ 生成历史OHLCV数据失败: {e}")
            conn.rollback()
        finally:
            conn.close()


async def main():
    """主函数"""
    print("💰 毫秒级加密货币数据收集器")
    print("="*70)
    
    # 初始化收集器
    collector = MillisecondCryptoCollector()
    
    print("1. 开始实时数据收集")
    print("2. 从历史数据生成OHLCV")
    print("3. 查看数据统计")
    
    choice = input("\n请选择 (1-3): ").strip()
    
    if choice == '1':
        # 获取Top N交易对
        n = int(input("收集前多少名币种? (默认10): ") or "10")
        symbols = collector.get_top_symbols(n)
        
        print(f"\n将收集以下 {len(symbols)} 个交易对的数据:")
        print(", ".join(symbols))
        print("\n按 Ctrl+C 停止收集\n")
        
        try:
            # 开始收集数据
            await collector.collect_trades(symbols)
            
        except KeyboardInterrupt:
            print("\n\n⏹️  停止收集数据...")
            collector.get_statistics()
            print("\n👋 感谢使用！")
    
    elif choice == '2':
        print("\n🔄 从历史交易数据生成OHLCV数据...")
        collector.generate_historical_ohlcv()
        collector.get_statistics()
    
    elif choice == '3':
        collector.get_statistics()
    
    else:
        print("❌ 无效选择")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序已退出")