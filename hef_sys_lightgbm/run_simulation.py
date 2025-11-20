# run_simulation.py
import asyncio
import websockets
import json
import os
import time
import numpy as np
import onnxruntime as ort
from collections import deque
from datetime import datetime
import config
from feature_engine import FeatureEngine

# --- 模拟账户配置 ---
INITIAL_CAPITAL = 10000.0  # 初始资金
TAKER_FEE = 0.0005         # 0.05% 手续费 (OKX VIP0 Taker)
# BUY_THRESHOLD = 0.80       # 买入信号阈值 (置信度)
BUY_THRESHOLD = 0.5  
TP_PERCENT = 0.002         # 止盈 0.2%
SL_PERCENT = -0.001        # 止损 -0.1%
MAX_HOLD_SEC = 30          # 最长持仓时间(秒)

class SimAccount:
    def __init__(self, initial_usdt):
        self.usdt = initial_usdt
        self.btc = 0.0
        self.position = False # False=空仓, True=持仓
        self.entry_price = 0.0
        self.entry_time = 0
        self.trades_count = 0
        self.win_count = 0

    def get_balance(self, current_price):
        """计算当前账户总权益 (Net Asset Value)"""
        if self.position:
            return self.btc * current_price
        return self.usdt

    def buy(self, price, timestamp):
        if self.position: return
        
        # 全仓买入
        buy_cost = self.usdt
        fee = buy_cost * TAKER_FEE
        real_buy_amt = buy_cost - fee
        
        self.btc = real_buy_amt / price
        self.usdt = 0
        self.position = True
        self.entry_price = price
        self.entry_time = timestamp
        
        print(f"\n🔵 [买入] 价格: {price:.2f} | 数量: {self.btc:.6f} | 手续费: {fee:.2f} U")

    def sell(self, price, reason):
        if not self.position: return
        
        sell_value = self.btc * price
        fee = sell_value * TAKER_FEE
        self.usdt = sell_value - fee
        
        # 统计盈亏
        pnl = self.usdt - self.entry_price * self.btc / (1 - TAKER_FEE) * (1 + TAKER_FEE) # 估算
        # 简单计算：当前余额 - 上一次买入前的余额 (比较复杂，这里简化用净值对比)
        
        profit_percent = (price - self.entry_price) / self.entry_price
        is_win = profit_percent > (TAKER_FEE * 2) # 覆盖双边手续费才算赢
        
        if is_win: self.win_count += 1
        self.trades_count += 1
        self.btc = 0
        self.position = False
        
        print(f"🔴 [卖出] 价格: {price:.2f} | 原因: {reason} | 余额: {self.usdt:.2f} U")
        return profit_percent

# --- 核心逻辑 ---

price_history = deque(maxlen=100)
last_trade = {"px": 0.0, "sz": 0.0, "side": 0}
account = SimAccount(INITIAL_CAPITAL)

def load_model():
    model_path = os.path.join(config.MODEL_DIR, config.MODEL_NAME)
    if not os.path.exists(model_path):
        print(f"❌ 未找到模型: {model_path}")
        return None
    return ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])

async def simulation_loop():
    session = load_model()
    if session is None: return
    
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[1].name
    
    uri = "wss://ws.okx.com:8443/ws/v5/public"
    print(f"🎰 [Simulation] 启动模拟盘 | 初始资金: {INITIAL_CAPITAL} USDT")
    print(f"📝 策略: 信号>{BUY_THRESHOLD}买入 | 止盈{TP_PERCENT*100}% | 止损{SL_PERCENT*100}%")
    
    async with websockets.connect(uri) as ws:
        sub_msg = {
            "op": "subscribe",
            "args": [
                {"channel": "books5", "instId": config.SYMBOL},
                {"channel": "trades", "instId": config.SYMBOL}
            ]
        }
        await ws.send(json.dumps(sub_msg))

        last_print_time = time.time()

        while True:
            try:
                msg = await ws.recv()
                data = json.loads(msg)
                if 'data' not in data: continue
                
                channel = data['arg']['channel']
                res = data['data'][0]

                # 1. 更新成交数据
                if channel == 'trades':
                    last_trade['px'] = float(res['px'])
                    last_trade['sz'] = float(res['sz'])
                    last_trade['side'] = 1 if res['side'] == 'buy' else -1
                
                # 2. 盘口数据 -> 驱动策略
                elif channel == 'books5':
                    # 获取买一卖一价 (真实交易要看盘口)
                    ask_price = float(res['asks'][0][0]) # 买入看这里
                    bid_price = float(res['bids'][0][0]) # 卖出看这里
                    mid_price = (ask_price + bid_price) / 2
                    
                    current_time = time.time()

                    # --- A. 卖出检查 (如果有持仓) ---
                    if account.position:
                        # 计算当前浮动盈亏 (基于卖一价)
                        pct_change = (bid_price - account.entry_price) / account.entry_price
                        
                        # 1. 止盈
                        if pct_change >= TP_PERCENT:
                            account.sell(bid_price, "✅ 止盈触发")
                        # 2. 止损
                        elif pct_change <= SL_PERCENT:
                            account.sell(bid_price, "🛡️ 止损触发")
                        # 3. 超时强平
                        elif (current_time - account.entry_time) > MAX_HOLD_SEC:
                            account.sell(bid_price, "⏰ 超时平仓")
                        
                        # 打印持仓心跳
                        if current_time - last_print_time > 1:
                            print(f"⏳ 持仓中... 浮盈: {pct_change*100:.3f}% | 价格: {mid_price:.2f}", end="\r")
                            last_print_time = current_time
                        
                        continue # 持仓时不进行买入预测

                    # --- B. 买入预测 (如果空仓) ---
                    
                    # 维护历史数据
                    price_history.append(mid_price)
                    if len(price_history) < 20:
                        if len(price_history) % 5 == 0: print(f"⏳ 预热数据... {len(price_history)}/20")
                        continue

                    # 构造特征
                    snapshot = {
                        'asks': res['asks'], 'bids': res['bids'],
                        'lt_px': last_trade['px'], 'lt_sz': last_trade['sz'], 'lt_side': last_trade['side']
                    }
                    features = FeatureEngine.calculate_realtime_features(snapshot, list(price_history))
                    if features is None: continue

                    # 推理
                    pred_onx = session.run([output_name], {input_name: features})
                    buy_prob = pred_onx[0][0].get(1, 0.0)

                    # 策略判定
                    if buy_prob > BUY_THRESHOLD:
                        # 🚀 触发买入
                        print(f"🚀 信号触发! 概率: {buy_prob:.4f}")
                        account.buy(ask_price, current_time)
                    else:
                        # 偶尔打印状态
                        if np.random.random() < 0.02:
                            nav = account.get_balance(mid_price)
                            pnl_total = (nav - INITIAL_CAPITAL)
                            color = "🟢" if pnl_total >= 0 else "🔴"
                            print(f"💤 监控中 | Prob: {buy_prob:.4f} | 净值: {nav:.2f} {color} ({pnl_total:+.2f})")

            except Exception as e:
                print(f"Error: {e}")
                await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(simulation_loop())
    except KeyboardInterrupt:
        print("\n🛑 模拟结束")
        # 强制平仓结算
        if account.position:
            print("强制平仓结算中...")
            # 这里没法获取最后价格，只能大致估算
            print(f"最终余额 (未平仓): {account.usdt:.2f} (BTC: {account.btc})")
        else:
            print(f"最终余额: {account.usdt:.2f} USDT")