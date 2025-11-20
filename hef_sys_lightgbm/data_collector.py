# data_collector.py
import asyncio
import websockets
import json
import csv
import time
import os
from datetime import datetime
import config

WS_URL = "wss://ws.okx.com:8443/ws/v5/public"

# 内存缓存：记录最近一笔成交信息
last_trade_state = {
    "px": 0.0,
    "sz": 0.0,
    "side": 0 
}

async def record_loop():
    print(f"🚀 [Collector] 启动录制: {config.SYMBOL}")
    
    # 初始化文件名
    current_date = datetime.now().strftime('%Y%m%d')
    file_path = os.path.join(config.DATA_DIR, f"{config.SYMBOL}_{current_date}.csv")
    
    headers = [
        "ts_loc", "ts_exch", 
        "ap0", "as0", "ap1", "as1", "ap2", "as2", "ap3", "as3", "ap4", "as4",
        "bp0", "bs0", "bp1", "bs1", "bp2", "bs2", "bp3", "bs3", "bp4", "bs4",
        "lt_px", "lt_sz", "lt_side"
    ]

    # buffering=1: 行缓冲，来一行写一行，防数据丢失
    f = open(file_path, 'a+', newline='', buffering=1)
    writer = csv.writer(f)
    
    # 如果是新文件，写入表头
    if os.path.getsize(file_path) == 0:
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
                print(f"✅ [Collector] WebSocket 已连接 - {datetime.now()}")

                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    
                    if 'data' not in data: continue
                    channel = data['arg']['channel']
                    res = data['data'][0]

                    # 更新最新成交
                    if channel == 'trades':
                        last_trade_state['px'] = float(res['px'])
                        last_trade_state['sz'] = float(res['sz'])
                        last_trade_state['side'] = 1 if res['side'] == 'buy' else -1

                    # 盘口更新 -> 触发写入
                    elif channel == 'books5':
                        ts_loc = time.time()
                        ts_exch = int(res['ts'])
                        
                        # 扁平化 5 档数据
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
            
            # 检查日期变更，切换文件
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