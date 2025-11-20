# train_pipeline.py
import pandas as pd
import numpy as np
import lightgbm as lgb  # 核心变化
import os
import glob
from onnxmltools import convert_lightgbm
from onnxconverter_common.data_types import FloatTensorType
import config
from feature_engine import FeatureEngine

def load_recent_data(days=3):
    """加载最近 N 天的数据"""
    files = sorted(glob.glob(os.path.join(config.DATA_DIR, "*.csv")))
    if not files:
        raise FileNotFoundError("未找到数据文件，请先运行 data_collector.py")
    
    recent_files = files[-days:]
    print(f"📚 [Train] 加载文件: {[os.path.basename(f) for f in recent_files]}")
    
    df_list = []
    for f in recent_files:
        try:
            df_list.append(pd.read_csv(f))
        except Exception as e:
            print(f"⚠️ 跳过损坏文件 {f}: {e}")
            
    return pd.concat(df_list, ignore_index=True)

def train_model():
    # 1. 加载数据
    df = load_recent_data(days=3)
    print(f"📊 [Train] 原始数据行数: {len(df)}")
    
    # 2. 特征计算
    X = FeatureEngine.calculate_train_features(df)
    
    # 3. 打标签
    mid_price = (df['ap0'] + df['bp0']) / 2
    future_return = mid_price.shift(-config.PREDICT_HORIZON) / mid_price - 1
    
    y = np.zeros(len(df))
    y[future_return > config.LABEL_THRESHOLD] = 1
    
    valid_idx = ~np.isnan(future_return)
    X = X[valid_idx]
    y = y[valid_idx]
    
    print(f"🎯 [Train] 正样本(买入机会)比例: {np.mean(y==1):.2%}")
    
    # 4. 训练 LightGBM
    print("🚀 [Train] 开始训练 LightGBM...")
    
    # LGBM 参数配置 (注重速度与泛化)
    model = lgb.LGBMClassifier(
        n_estimators=100,
        learning_rate=0.1,
        num_leaves=31,        # LGBM 核心参数，控制复杂度
        max_depth=-1,         # -1 表示不限制深度，由 num_leaves 控制
        n_jobs=-1,            # 使用所有 CPU 核心
        objective='binary',
        importance_type='split'
    )
    
    model.fit(
        X, y,
        eval_set=[(X, y)],     # 简单自测，实际应用应划分验证集
        eval_metric='logloss',
        callbacks=[
            lgb.log_evaluation(period=20) # 每20轮打印一次日志
        ]
    )
    
    # 5. 导出 ONNX
    print("💾 [Train] 正在导出 ONNX...")
    
    # 定义输入张量的类型和形状: [Batch_Size, Feature_Count]
    initial_type = [('input', FloatTensorType([None, len(config.FEATURES)]))]
    
    # 使用 onnxmltools 转换
    onx = convert_lightgbm(
        model, 
        initial_types=initial_type,
        target_opset=12
    )
    
    save_path = os.path.join(config.MODEL_DIR, "hft_model_lgbm.onnx")
    with open(save_path, "wb") as f:
        f.write(onx.SerializeToString())
        
    print(f"✅ [Train] 模型已保存: {save_path}")

if __name__ == "__main__":
    train_model()