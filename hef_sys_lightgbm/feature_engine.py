# feature_engine.py
import numpy as np
import pandas as pd
import config

class FeatureEngine:
    @staticmethod
    def _safe_div(a, b):
        """安全除法，处理分母为0的情况"""
        return np.divide(a, b, out=np.zeros_like(a), where=b!=0)

    # -------------------------------------------------------
    # 场景 A: 离线训练 (输入 Pandas DataFrame)
    # -------------------------------------------------------
    @staticmethod
    def calculate_train_features(df):
        # 1. 基础中间价
        mid_price = (df['ap0'] + df['bp0']) / 2
        
        # 2. Spread
        df['spread'] = df['ap0'] - df['bp0']
        
        # 3. Order Book Imbalance
        # L1
        df['imbalance_l1'] = FeatureEngine._safe_div(
            (df['bs0'] - df['as0']), (df['bs0'] + df['as0'])
        )
        # L5 (聚合前5档)
        total_bid = df[['bs0','bs1','bs2','bs3','bs4']].sum(axis=1)
        total_ask = df[['as0','as1','as2','as3','as4']].sum(axis=1)
        df['imbalance_l5'] = FeatureEngine._safe_div((total_bid - total_ask), (total_bid + total_ask))

        # 4. 技术指标
        # RSI (Window=14)
        delta = mid_price.diff()
        up = delta.clip(lower=0)
        down = -1 * delta.clip(upper=0)
        ma_up = up.rolling(window=14).mean()
        ma_down = down.rolling(window=14).mean()
        rsi = 100 - (100 / (1 + FeatureEngine._safe_div(ma_up, ma_down)))
        df['rsi_14'] = rsi.fillna(50)

        # Volatility (Window=20)
        df['volatility'] = mid_price.rolling(window=20).std().fillna(0)

        # 5. Trade Flow
        df['trade_flow'] = df['lt_sz'] * df['lt_side']
        
        # 6. 原始量
        df['ask_sz_0'] = df['as0']
        df['bid_sz_0'] = df['bs0']

        # 清洗异常值
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        df.fillna(0, inplace=True)
        
        return df[config.FEATURES]

    # -------------------------------------------------------
    # 场景 B: 在线推理 (输入 Snapshot 字典 + 历史价格列表)
    # -------------------------------------------------------
    @staticmethod
    def calculate_realtime_features(snapshot, history_prices):
        try:
            # 解包数据 (snapshot 来自 WebSocket)
            # 确保价格和数量是 float 类型
            ap0 = float(snapshot['asks'][0][0])
            as0 = float(snapshot['asks'][0][1])
            bp0 = float(snapshot['bids'][0][0])
            bs0 = float(snapshot['bids'][0][1])
            
            # 1. Spread
            spread = ap0 - bp0
            
            # 2. Imbalance L1
            imbalance_l1 = (bs0 - as0) / (bs0 + as0) if (bs0 + as0) > 0 else 0.0
            
            # 3. Imbalance L5
            sum_as = sum([float(x[1]) for x in snapshot['asks']])
            sum_bs = sum([float(x[1]) for x in snapshot['bids']])
            imbalance_l5 = (sum_bs - sum_as) / (sum_bs + sum_as) if (sum_bs + sum_as) > 0 else 0.0
            
            # 4. 历史序列指标 (RSI, Volatility)
            # 需要 history_prices 至少有一定长度，否则返回默认值
            rsi = 50.0
            volatility = 0.0
            
            if len(history_prices) >= 20:
                prices = np.array(history_prices, dtype=np.float64)
                
                # Volatility
                volatility = np.std(prices[-20:])
                
                # RSI (简化计算: 最近14个点的涨跌)
                deltas = np.diff(prices[-15:]) # 取最后15个点算14个差值
                gains = deltas[deltas > 0].sum()
                losses = -deltas[deltas < 0].sum()
                if losses == 0:
                    rsi = 100.0 if gains > 0 else 50.0
                else:
                    rs = gains / losses
                    rsi = 100 - (100 / (1 + rs))
            
            # 5. Trade Flow
            # 注意：如果刚才没有成交，lt_sz 可能为 0
            trade_flow = float(snapshot.get('lt_px', 0)) * float(snapshot.get('lt_side', 0)) # 这里用 px*side 近似或直接用 size*side
            # 更正：config里用的是 lt_sz * side
            trade_flow = float(snapshot.get('lt_sz', 0)) * float(snapshot.get('lt_side', 0))
            
            # 组装向量 (1, N)
            features = np.array([[
                spread, imbalance_l1, imbalance_l5, 
                as0, bs0, rsi, volatility, trade_flow
            ]], dtype=np.float32)
            
            # 最终安全检查
            if np.isnan(features).any():
                return None
                
            return features
            
        except Exception as e:
            # 生产环境可记录日志
            return None