# train_pipeline.py
import pandas as pd
import numpy as np
import lightgbm as lgb
import os
import glob
from onnxmltools import convert_lightgbm
from onnxconverter_common.data_types import FloatTensorType
import config
from feature_engine import FeatureEngine

def load_recent_data(days=5):
    """加载最近 N 天的数据"""
    files = sorted(glob.glob(os.path.join(config.DATA_DIR, "*.csv")))
    if not files:
        print("⚠️ 未找到数据文件！请先运行 data_collector.py 录制几分钟数据。")
        return None
    
    recent_files = files[-days:]
    print(f"📚 [Train] 加载文件: {[os.path.basename(f) for f in recent_files]}")
    
    df_list = []
    for f in recent_files:
        try:
            # 简单检查文件是否为空
            if os.path.getsize(f) < 100: continue
            df_list.append(pd.read_csv(f))
        except Exception as e:
            print(f"⚠️ 跳过损坏文件 {f}: {e}")
            
    if not df_list: return None
    return pd.concat(df_list, ignore_index=True)

def train_model():
    # 1. 加载数据
    df = load_recent_data()
    if df is None: return
    
    print(f"📊 [Train] 原始数据行数: {len(df)}")
    
    # 2. 特征计算
    print("⚙️ [Train] 正在计算特征...")
    X = FeatureEngine.calculate_train_features(df)
    
    # 3. 打标签
    # 计算未来价格变化率
    mid_price = (df['ap0'] + df['bp0']) / 2
    future_return = mid_price.shift(-config.PREDICT_HORIZON) / mid_price - 1
    
    # Label: 1 = 涨幅超过阈值, 0 = 其他
    y = np.zeros(len(df))
    y[future_return > config.LABEL_THRESHOLD] = 1
    
    # 清洗无效数据 (NaN)
    valid_idx = ~np.isnan(future_return) & ~X.isnull().any(axis=1)
    X = X[valid_idx]
    y = y[valid_idx]
    
    pos_ratio = np.mean(y==1)
    print(f"🎯 [Train] 正样本(买入信号)比例: {pos_ratio:.2%}")
    
    if len(X) < 1000:
        print("⚠️ 数据量太少，无法有效训练。请继续录制。")
        return

    # 4. 训练 LightGBM
    print("🚀 [Train] 开始训练 LightGBM...")
    model = lgb.LGBMClassifier(
        n_estimators=200,
        learning_rate=0.05,
        num_leaves=31,
        max_depth=-1,
        n_jobs=-1,
        objective='binary',
        random_state=42
    )
    
    model.fit(X, y)
    
    # 5. 导出 ONNX
    print("💾 [Train] 正在导出 ONNX...")
    
    # 定义输入张量形状: [Batch_Size, Feature_Count]
    # float 类型必须匹配
    initial_type = [('input', FloatTensorType([None, len(config.FEATURES)]))]
    
    # 转换
    onx = convert_lightgbm(
        model, 
        initial_types=initial_type,
        target_opset=12
    )
    
    save_path = os.path.join(config.MODEL_DIR, config.MODEL_NAME)
    with open(save_path, "wb") as f:
        f.write(onx.SerializeToString())
        
    print(f"✅ [Train] 模型已保存: {save_path}")

if __name__ == "__main__":
    train_model()