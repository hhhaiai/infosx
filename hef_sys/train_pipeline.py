# train_pipeline.py
import pandas as pd
import numpy as np
import xgboost as xgb
import os
import glob
from skl2onnx import to_onnx, update_registered_converter
from skl2onnx.common.shape_calculator import calculate_linear_classifier_output_shapes
from onnxmltools.convert.xgboost.operator_converters.xgboost import convert_xgboost
import config
from feature_engine import FeatureEngine

# 注册 ONNX 转换器
update_registered_converter(
    xgb.XGBClassifier, 'XGBoostXGBClassifier',
    calculate_linear_classifier_output_shapes, convert_xgboost, 
    options={'nocl': [True, False], 'zipmap': [False]}
)

def load_recent_data(days=3):
    """
    加载最近 N 天的 CSV 数据文件。
    
    Args:
        days (int): 回溯的天数，默认为 3。
        
    Returns:
        pd.DataFrame: 合并后的 Pandas DataFrame，包含所有加载的数据。
        
    Raises:
        FileNotFoundError: 如果没有找到任何数据文件。
    """
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
    """
    模型训练主流程。
    
    步骤:
    1. 加载最近的历史数据。
    2. 计算特征 (Feature Engineering)。
    3. 生成标签 (Labeling) - 基于未来收益率。
    4. 训练 XGBoost 分类模型。
    5. 将训练好的模型导出为 ONNX 格式，以便于高性能推理。
    """
    # 1. 加载数据
    df = load_recent_data(days=3)
    print(f"📊 [Train] 原始数据行数: {len(df)}")
    
    # 2. 特征计算
    X = FeatureEngine.calculate_train_features(df)
    
    # 3. 打标签 (Labeling)
    mid_price = (df['ap0'] + df['bp0']) / 2
    # 计算未来收益率
    future_return = mid_price.shift(-config.PREDICT_HORIZON) / mid_price - 1
    
    # 三分类标签: 1(Buy), 0(Hold/Sell) 
    # 注：当前简化为二分类，只预测买点
    y = np.zeros(len(df))
    y[future_return > config.LABEL_THRESHOLD] = 1
    
    # 清洗标签为空的行
    valid_idx = ~np.isnan(future_return)
    X = X[valid_idx]
    y = y[valid_idx]
    
    print(f"🎯 [Train] 正样本(买入机会)比例: {np.mean(y==1):.2%}")
    
    # 4. 训练 XGBoost
    print("🚀 [Train] 开始训练 (使用 hist 模式)...")
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        tree_method='hist',  # CPU 高速模式
        n_jobs=-1,
        objective='binary:logistic'
    )
    model.fit(X, y)
    
    # 5. 导出 ONNX
    print("💾 [Train] 正在导出 ONNX...")
    onx = to_onnx(
        model, 
        X[:1].astype(np.float32), 
        target_opset=12
    )
    
    save_path = os.path.join(config.MODEL_DIR, "hft_model_latest.onnx")
    with open(save_path, "wb") as f:
        f.write(onx.SerializeToString())
        
    print(f"✅ [Train] 模型已保存: {save_path}")

if __name__ == "__main__":
    train_model()