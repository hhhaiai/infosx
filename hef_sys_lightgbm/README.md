

## 标准操作流程 (SOP)

### 步骤 1：数据冷启动 (Cold Start)
**目标**：获取用于第一次训练的原始数据。
1.  运行 `python data_collector.py`
2.  **动作**：让其在后台运行至少 **1-2 小时**（建议 24 小时以覆盖昼夜波动）。
3.  **检查**：`data/` 目录下是否生成 CSV 文件，且大小在增长。

### 步骤 2：模型训练 (Train)
**目标**：生成 ONNX 模型。
1.  确保已有数据文件。
2.  运行 `python train_pipeline.py`
3.  **检查**：
    *   控制台输出 `✅ [Train] 模型已保存`。
    *   `model/` 目录下生成 `hft_lgbm_v1.onnx`。

### 步骤 3：实战模拟 (Inference)
**目标**：验证模型是否能跑通，以及预测概率是否合理。
1.  运行 `python run_inference.py`
2.  **观察**：
    *   脚本会先显示 `⏳ 初始化中...`。
    *   随后开始输出 `💤 观望中...` 或 `🚀 信号触发`。
    *   如果 `概率` 始终是 0.5 或变化极小，说明特征可能未归一化或数据太少，需回到步骤 1 积累更多数据。


## 安装依赖

```
pip install numpy pandas lightgbm scikit-learn onnx onnxruntime onnxmltools websockets asyncio
```