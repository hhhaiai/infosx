# run_inference.py
import asyncio
import websockets
import json
import os
import numpy as np
import onnxruntime as ort
from collections import deque
import config
from feature_engine import FeatureEngine

# 历史价格队列 (用于计算 RSI, Volatility)
price_history = deque(maxlen=100)
# 成交信息缓存
last_trade = {"px": 0.0, "sz": 0.0, "side": 0}

def load_model():
    model_path = os.path.join(config.MODEL_DIR, config.MODEL_NAME)
    if not os.path.exists(model_path):
        print(f"❌ 未找到模型文件: {model_path}")
        print("请先运行 train_pipeline.py 生成模型。")
        return None
    
    print(f"🧠 [Inference] 加载模型: {config.MODEL_NAME}")
    # 创建推理会话
    session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
    return session

async def inference_loop():
    session = load_model()
    if session is None: return

    # 获取输入输出节点名称
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[1].name # LGBM输出通常是 [label, probabilities]
    
    uri = "wss://ws.okx.com:8443/ws/v5/public"
    
    print(f"🔥 [Inference] 连接行情: {config.SYMBOL}")
    
    async with websockets.connect(uri) as ws:
        # 订阅
        sub_msg = {
            "op": "subscribe",
            "args": [
                {"channel": "books5", "instId": config.SYMBOL},
                {"channel": "trades", "instId": config.SYMBOL}
            ]
        }
        await ws.send(json.dumps(sub_msg))

        while True:
            try:
                msg = await ws.recv()
                data = json.loads(msg)
                
                if 'data' not in data: continue
                channel = data['arg']['channel']
                res = data['data'][0]

                # 1. 更新成交信息
                if channel == 'trades':
                    last_trade['px'] = float(res['px'])
                    last_trade['sz'] = float(res['sz'])
                    last_trade['side'] = 1 if res['side'] == 'buy' else -1
                
                # 2. 收到盘口 -> 触发推理
                elif channel == 'books5':
                    # 构造 Snapshot
                    snapshot = {
                        'asks': res['asks'], # 原始字符串 list
                        'bids': res['bids'],
                        'lt_px': last_trade['px'],
                        'lt_sz': last_trade['sz'],
                        'lt_side': last_trade['side']
                    }
                    
                    # 维护历史价格 (用于计算指标)
                    mid_price = (float(res['asks'][0][0]) + float(res['bids'][0][0])) / 2
                    price_history.append(mid_price)
                    
                    # 至少需要 20 个点才能算特征
                    if len(price_history) < 20:
                        if len(price_history) % 5 == 0:
                            print(f"⏳ 初始化中... ({len(price_history)}/20)")
                        continue

                    # 计算特征
                    features = FeatureEngine.calculate_realtime_features(
                        snapshot, list(price_history)
                    )
                    
                    if features is None: continue

                    # ONNX 推理
                    # 输入形状必须是 (1, N_Features)
                    pred_onx = session.run([output_name], {input_name: features})
                    
                    # 解析结果
                    # pred_onx[0] 是一个 list of dicts: [{0: 0.9, 1: 0.1}]
                    probs = pred_onx[0][0]
                    buy_prob = probs.get(1, 0.0) # 获取标签为1的概率
                    
                    # 打印高置信度信号
                    if buy_prob > 0.5: # 仅展示 > 50% 的
                        print(f"🚀 信号触发 | 概率: {buy_prob:.4f} | 价格: {mid_price:.2f}")
                    else:
                        # 仅为了展示存活，偶尔打印
                        if np.random.random() < 0.05:
                            print(f"💤 观望中... | 概率: {buy_prob:.4f}")

            except Exception as e:
                print(f"Error: {e}")
                await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(inference_loop())
    except KeyboardInterrupt:
        print("推理停止")