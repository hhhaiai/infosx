# feature_engine.py
import numpy as np
import pandas as pd
import config

class FeatureEngine:
    @staticmethod
    def _safe_div(a, b):
        """
        安全除法，防止除以零。
        
        Args:
            a: 分子 (numpy array 或 scalar)
            b: 分母 (numpy array 或 scalar)
            
        Returns:
            除法结果，如果分母为0则返回0。
        """
        return np.divide(a, b, out=np.zeros_like(a), where=b!=0)

    # -------------------------------------------------------
    # 离线训练逻辑 (输入: Pandas DataFrame)
    # -------------------------------------------------------
    @staticmethod
    def calculate_train_features(df):
        """
        离线训练特征计算逻辑。
        接收包含原始市场数据的 DataFrame，计算用于模型训练的技术指标和特征。
        
        Args:
            df: 包含原始 CSV 数据的 Pandas DataFrame。
                必须包含字段: ap0, bp0, as0, bs0, ... as4, bs4, lt_sz, lt_side

                字段说明:
                | 字段名 | 含义 | 说明 |
                | :--- | :--- | :--- |
                | ts_loc | 本地时间戳 | 机器接收到数据时的系统时间 (Unix Timestamp) |
                | ts_exch | 交易所时间戳 | 交易所撮合引擎生成数据的时间 (Unix Timestamp, 毫秒) |
                | ap0 ~ ap4 | 卖方价格 (Ask Price) | ap0 是卖一价 (最优卖出价)，ap4 是卖五价 |
                | as0 ~ as4 | 卖方数量 (Ask Size) | 对应卖一到卖五挂单的数量 |
                | bp0 ~ bp4 | 买方价格 (Bid Price) | bp0 是买一价 (最优买入价)，bp4 是买五价 |
                | bs0 ~ bs4 | 买方数量 (Bid Size) | 对应买一到买五挂单的数量 |
                | lt_px | 最新成交价 | 最近一笔成交的价格 (Last Trade Price) |
                | lt_sz | 最新成交量 | 最近一笔成交的数量 (Last Trade Size) |
                | lt_side | 最新成交方向 | 1: 主动买入 (Taker Buy), -1: 主动卖出 (Taker Sell) |
        
        Returns:
            pd.DataFrame: 只包含 config.FEATURES 中定义的特征列的 DataFrame。
        """
        # 1. 基础价格
        mid_price = (df['ap0'] + df['bp0']) / 2
        
        # 2. Spread (价差)
        df['spread'] = df['ap0'] - df['bp0']
        
        # 3. Imbalance (订单流失衡)
        # L1 Imbalance
        df['imbalance_l1'] = FeatureEngine._safe_div(
            (df['bs0'] - df['as0']), (df['bs0'] + df['as0'])
        )
        # L5 Imbalance (简化累加)
        total_bid_sz = df['bs0'] + df['bs1'] + df['bs2'] + df['bs3'] + df['bs4']
        total_ask_sz = df['as0'] + df['as1'] + df['as2'] + df['as3'] + df['as4']
        df['imbalance_l5'] = FeatureEngine._safe_div(
            (total_bid_sz - total_ask_sz), (total_bid_sz + total_ask_sz)
        )

        # 4. RSI (基于中间价，Window=14)
        delta = mid_price.diff()
        up = delta.clip(lower=0)
        down = -1 * delta.clip(upper=0)
        ma_up = up.rolling(window=14).mean()
        ma_down = down.rolling(window=14).mean()
        rsi = 100 - (100 / (1 + FeatureEngine._safe_div(ma_up, ma_down)))
        df['rsi_14'] = rsi.fillna(50)

        # 5. Volatility (波动率，Window=20)
        df['volatility'] = mid_price.rolling(window=20).std().fillna(0)

        # 6. Trade Flow (成交流)
        df['trade_flow'] = df['lt_sz'] * df['lt_side']
        
        # 映射原始量
        df['ask_sz_0'] = df['as0']
        df['bid_sz_0'] = df['bs0']

        # 清洗：去除 NaN 和 Inf，防止模型报错
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        df.fillna(0, inplace=True)
        
        return df[config.FEATURES]

    # -------------------------------------------------------
    # 在线实盘逻辑 (输入: 字典/Numpy) -> 未来迁移 C++ 参考基准
    # -------------------------------------------------------
    @staticmethod
    def calculate_realtime_features(snapshot, history_prices):
        """
        在线实盘特征计算逻辑。
        用于在实盘交易中实时计算特征，逻辑需与离线训练保持严格一致。
        
        Args:
            snapshot (dict): 当前最新的 tick 数据快照。
                             结构示例: {'asks': [[px, sz], ...], 'bids': [[px, sz], ...], 'lt_sz': ..., 'lt_side': ...}
            history_prices (list): 最近 N 个 tick 的中间价列表，用于计算时序指标 (如 RSI, Volatility)。
            
        Returns:
            np.array: 形状为 (1, n_features) 的 numpy 数组，包含计算好的特征向量。
                      如果计算失败或数据不足，返回 None。
        """
        try:
            # 提取基础变量
            ap0, as0 = snapshot['asks'][0]
            bp0, bs0 = snapshot['bids'][0]
            
            # 1. Spread
            spread = ap0 - bp0
            
            # 2. Imbalance L1
            imbalance_l1 = (bs0 - as0) / (bs0 + as0) if (bs0 + as0) > 0 else 0
            
            # 3. Imbalance L5
            sum_as = sum([x[1] for x in snapshot['asks']])
            sum_bs = sum([x[1] for x in snapshot['bids']])
            imbalance_l5 = (sum_bs - sum_as) / (sum_bs + sum_as) if (sum_bs + sum_as) > 0 else 0
            
            # 4. 历史序列指标 (RSI, Volatility)
            rsi = 50.0
            volatility = 0.0
            
            if len(history_prices) >= 20:
                prices = np.array(history_prices[-20:], dtype=np.float32)
                
                # Volatility
                volatility = np.std(prices)
                
                # RSI (简化版: 最近14个点的涨跌幅累加)
                deltas = np.diff(prices[-15:])
                gains = deltas[deltas > 0].sum()
                losses = -deltas[deltas < 0].sum()
                if losses == 0:
                    rsi = 100.0 if gains > 0 else 50.0
                else:
                    rs = gains / losses
                    rsi = 100 - (100 / (1 + rs))
            
            # 5. Trade Flow
            trade_flow = snapshot.get('lt_sz', 0) * snapshot.get('lt_side', 0)
            
            # 组装向量 (必须与 config.FEATURES 顺序一致)
            features = np.array([[
                spread, imbalance_l1, imbalance_l5, 
                as0, bs0, rsi, volatility, trade_flow
            ]], dtype=np.float32)
            
            if np.isnan(features).any(): return None
                
            return features
            
        except Exception as e:
            return None