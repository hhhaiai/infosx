# config.py
import os

# --- 基础配置 ---
SYMBOL = "BTC-USDT"

# [修改点 1] 降低阈值
# 原: 0.0005 (0.05%) -> 改为: 0.00015 (0.015%)
# 逻辑: 高频交易吃的是微利，积少成多，门槛不能太高
LABEL_THRESHOLD = 0.00015 

# [修改点 2] 延长预测视野
# 原: 10 -> 改为: 30
# 逻辑: 10个tick太短(约1秒)，30个tick(约3-4秒)能容纳更多波动
PREDICT_HORIZON = 30

# --- 路径配置 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_DIR = os.path.join(BASE_DIR, "model")
MODEL_NAME = "hft_lgbm_v1.onnx"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

# --- 特征清单 (Schema) ---
FEATURES = [
    'spread',           
    'imbalance_l1',     
    'imbalance_l5',     
    'ask_sz_0',         
    'bid_sz_0',         
    'rsi_14',           
    'volatility',       
    'trade_flow'        
]