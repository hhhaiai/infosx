# config.py
import os

# --- 交易配置 ---
SYMBOL = "BTC-USDT"
FEE_RATE = 0.0005  # Taker 手续费率 0.05% (作为标签阈值基准)

# --- 路径配置 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_DIR = os.path.join(BASE_DIR, "model")

# 自动创建目录
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

# --- 训练参数 ---
# 预测目标：未来 10 个 Tick (约 1 秒) 后的价格变化
PREDICT_HORIZON = 10 
# 标签阈值：只有涨幅 > 手续费 + 0.01% 才标记为 Buy
LABEL_THRESHOLD = FEE_RATE + 0.0001 

# --- 特征列表 (Schema) ---
# 注意：此顺序必须在训练和推理中严格保持一致
FEATURES = [
    'spread', 
    'imbalance_l1', 'imbalance_l5', 
    'ask_sz_0', 'bid_sz_0', 
    'rsi_14', 
    'volatility',
    'trade_flow' 
]