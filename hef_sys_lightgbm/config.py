# config.py
import os

# --- 交易配置 ---
SYMBOL = "BTC-USDT"
FEE_RATE = 0.0005  # Taker 手续费率 0.05%

# --- 路径配置 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_DIR = os.path.join(BASE_DIR, "model")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

# --- 训练参数 ---
PREDICT_HORIZON = 10 
LABEL_THRESHOLD = FEE_RATE + 0.0001 

# --- 特征列表 (Schema) ---
# 顺序严格固定
FEATURES = [
    'spread', 
    'imbalance_l1', 'imbalance_l5', 
    'ask_sz_0', 'bid_sz_0', 
    'rsi_14', 
    'volatility',
    'trade_flow' 
]