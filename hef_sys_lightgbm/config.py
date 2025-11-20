# config.py
import os

# --- 基础配置 ---
SYMBOL = "BTC-USDT"
# 标签阈值: 0.05% (覆盖 Taker 手续费)
LABEL_THRESHOLD = 0.0005 
# 预测视野: 未来 10 个 Tick (约 1-2 秒)
PREDICT_HORIZON = 10


# --- 路径配置 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_DIR = os.path.join(BASE_DIR, "model")
MODEL_NAME = "hft_lgbm_v1.onnx"

# 自动创建目录
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

# --- 特征清单 (Schema) ---
# ⚠️ 警告: 此列表的顺序必须在训练和推理中严格保持一致，切勿更改顺序
FEATURES = [
    'spread',           # 盘口价差
    'imbalance_l1',     # 一档买卖失衡
    'imbalance_l5',     # 五档买卖失衡
    'ask_sz_0',         # 卖一量
    'bid_sz_0',         # 买一量
    'rsi_14',           # 相对强弱指标
    'volatility',       # 波动率
    'trade_flow'        # 资金流 (Taker方向 * 数量)
]