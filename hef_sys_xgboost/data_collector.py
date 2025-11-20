# data_collector.py
import asyncio
import websockets
import json
import csv
import time
import os
from datetime import datetime
import config

# OKX Public WebSocket URL
WS_URL = "wss://ws.okx.com:8443/ws/v5/public"

# 内存缓存：记录最近一笔成交信息
last_trade_state = {
    "px": 0.0,
    "sz": 0.0,
    "side": 0  # 1=Buy, -1=Sell
}

async def record_loop():
    """
    数据录制主循环 (异步)。
    
    功能:
    1. 连接 OKX 公共 WebSocket 频道。
    2. 订阅 Order Book (books5) 和 Trade (trades) 频道。
    3. 实时接收推送数据：
       - 对于成交数据 (trades): 更新内存中的最新成交状态 (价格, 数量, 方向)。
       - 对于盘口数据 (books5): 结合当前时间戳、盘口深度数据和最新成交状态，组装成一行记录写入 CSV 文件。
    4. 处理断线重连和跨天文件切换。
    """
    print(f"🚀 [Collector] 启动录制: {config.SYMBOL}")
    
    current_date = datetime.now().strftime('%Y%m%d')
    file_path = os.path.join(config.DATA_DIR, f"{config.SYMBOL}_{current_date}.csv")
    

    # 字段说明:
    # | 字段名 | 含义 | 说明 |
    # | :--- | :--- | :--- |
    # | ts_loc | 本地时间戳 | 机器接收到数据时的系统时间 (Unix Timestamp) |
    # | ts_exch | 交易所时间戳 | 交易所撮合引擎生成数据的时间 (Unix Timestamp, 毫秒) |
    # | ap0 ~ ap4 | 卖方价格 (Ask Price) | ap0 是卖一价 (最优卖出价)，ap4 是卖五价 |
    # | as0 ~ as4 | 卖方数量 (Ask Size) | 对应卖一到卖五挂单的数量 |
    # | bp0 ~ bp4 | 买方价格 (Bid Price) | bp0 是买一价 (最优买入价)，bp4 是买五价 |
    # | bs0 ~ bs4 | 买方数量 (Bid Size) | 对应买一到买五挂单的数量 |
    # | lt_px | 最新成交价 | 最近一笔成交的价格 (Last Trade Price) |
    # | lt_sz | 最新成交量 | 最近一笔成交的数量 (Last Trade Size) |
    # | lt_side | 最新成交方向 | 1: 主动买入 (Taker Buy), -1: 主动卖出 (Taker Sell)
    # 定义 CSV 表头
    headers = [
        "ts_loc", "ts_exch", 
        # Ask 1-5 (Price, Size)
        "ap0", "as0", "ap1", "as1", "ap2", "as2", "ap3", "as3", "ap4", "as4",
        # Bid 1-5
        "bp0", "bs0", "bp1", "bs1", "bp2", "bs2", "bp3", "bs3", "bp4", "bs4",
        # Trade Info
        "lt_px", "lt_sz", "lt_side"
    ]

    # 初始化文件
    file_exists = os.path.isfile(file_path)
    # buffering=1: 行缓冲，确保数据实时写入硬盘，不丢失
    f = open(file_path, 'a+', newline='', buffering=1) 
    writer = csv.writer(f)
    if not file_exists:
        writer.writerow(headers)

    subscribe_msg = {
        "op": "subscribe",
        "args": [
            {"channel": "books5", "instId": config.SYMBOL},
            {"channel": "trades", "instId": config.SYMBOL}
        ]
    }

    while True:
        try:
            async with websockets.connect(WS_URL) as ws:
                await ws.send(json.dumps(subscribe_msg))
                print(f"✅ [Collector] WebSocket 已连接")

                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    
                    if 'data' not in data: continue
                    
                    channel = data['arg']['channel']
                    res = data['data'][0]

                    # --- Case A: 成交数据 (更新内存状态) ---
                    if channel == 'trades':
                        last_trade_state['px'] = float(res['px'])
                        last_trade_state['sz'] = float(res['sz'])
                        last_trade_state['side'] = 1 if res['side'] == 'buy' else -1

                    # --- Case B: 盘口数据 (触发写盘) ---
                    elif channel == 'books5':
                        ts_loc = time.time()
                        ts_exch = int(res['ts'])
                        
                        # 提取 5 档数据 (Flatten)
                        asks = [float(x) for item in res['asks'] for x in item[:2]]
                        bids = [float(x) for item in res['bids'] for x in item[:2]]
                        
                        row = [ts_loc, ts_exch] + asks + bids + [
                            last_trade_state['px'], 
                            last_trade_state['sz'], 
                            last_trade_state['side']
                        ]
                        
                        writer.writerow(row)

        except Exception as e:
            print(f"⚠️ [Collector] 连接断开: {e}，3秒后重连...")
            await asyncio.sleep(3)
            
            # 检查是否跨天，切换文件
            new_date = datetime.now().strftime('%Y%m%d')
            if new_date != current_date:
                f.close()
                current_date = new_date
                file_path = os.path.join(config.DATA_DIR, f"{config.SYMBOL}_{current_date}.csv")
                f = open(file_path, 'a+', newline='', buffering=1)
                writer = csv.writer(f)
                writer.writerow(headers)
                print(f"📅 [Collector] 切换新文件: {current_date}")

if __name__ == "__main__":
    try:
        asyncio.run(record_loop())
    except KeyboardInterrupt:
        print("录制停止")