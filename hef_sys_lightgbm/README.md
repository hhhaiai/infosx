## 为什么选择 LightGBM? (Key Differences)

相比 XGBoost，本方案选择 LightGBM 的主要优势在于：

1.  **Leaf-wise 生长策略**：LGBM 采用带有深度限制的 Leaf-wise 算法，而非 XGBoost 的 Level-wise。这意味着在同样的拆分次数下，LGBM 往往能降低更多的 Loss，拟合精度更高，但也更容易过拟合（因此限制 `num_leaves` 很重要）。
2.  **训练速度更快**：对于本地机器（如 MacBook Pro），LGBM 的直方图算法对缓存更友好，处理数百万行 Tick 数据的速度通常比 XGBoost 快 2-10 倍。
3.  **类别特征处理**：虽然本项目目前主要使用数值特征，但 LGBM 原生支持 Categorical Feature（无需 One-hot 编码），未来若引入“交易所代码”、“时间段 ID”等特征，LGBM 会更有优势。


## 操作流程 (SOP)

### Step 1: 数据录制
```bash
# 启动后请保持运行至少 24 小时
python data_collector.py
```

### Step 2: 训练与生成模型
```bash
# 当有了足够数据后运行
python train_pipeline.py
```
*   **验证点**：观察控制台输出的 `[LightGBM] [Info]` 日志，确认 Loss 在下降。
*   **产出物**：检查 `model/hft_model_lgbm.onnx` 是否生成。

### Step 3: 推理验证 (Next Phase)
在下一阶段编写 `inference.py` 时，加载 ONNX 模型的代码与 XGBoost 版本通用，因为它们遵循相同的 ONNX 标准：

```python
# 推理代码预览 (通用)
import onnxruntime as ort
session = ort.InferenceSession("model/hft_model_lgbm.onnx")
# inputs = ... (来自 FeatureEngine)
# preds = session.run(None, {'input': inputs})
```

## 安装依赖

```
pip install numpy pandas lightgbm scikit-learn onnx onnxruntime onnxmltools websockets asyncio
```