## 操作流程 (SOP)

### Step 1: 数据冷启动 (Data Cold Start)
1.  打开终端，进入项目目录。
2.  运行录制脚本：
    ```bash
    python data_collector.py
    ```
3.  **动作**：保持该终端开启（或使用 `nohup` 后台运行）。
4.  **检查**：确认 `data/` 目录下生成了 CSV 文件，且文件大小在不断增加。
5.  **时长**：建议至少录制 **24 小时**，以覆盖完整的昼夜行情周期。

### Step 2: 首次模型训练 (First Training)
1.  当积累了足够数据（如 24 小时）后，打开新终端。
2.  运行训练脚本：
    ```bash
    python train_pipeline.py
    ```
3.  **观察输出**：
    *   `正样本比例`：如果接近 0% 或 100%，说明标签阈值设置有问题。合理的比例应在 **5% - 20%** 之间。
    *   `模型保存`：确认 `model/hft_model_latest.onnx` 文件已生成。

### Step 3: 循环迭代 (Iteration)
*   **数据录制**：`data_collector.py` 保持常驻运行，永不停止。
*   **模型更新**：每隔 1-3 天运行一次 `train_pipeline.py`，生成新的 ONNX 模型覆盖旧文件。


## 安装依赖

```
pip install numpy pandas xgboost scikit-learn onnx onnxruntime skl2onnx websockets asyncio
```