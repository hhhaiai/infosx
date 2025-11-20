# feature_engine.py
import numpy as np
import pandas as pd
import config

class FeatureEngine:
    @staticmethod
    def _safe_div(a, b):
        return np.divide(a, b, out=np.zeros_like(a), where=b!=0)

    # -------------------------------------------------------
    # 场景 A: 离线训练
    # -------------------------------------------------------
    @staticmethod
    def calculate_train_features(df):
        mid_price = (df['ap0'] + df['bp0']) / 2
        
        # 2. Spread
        df['spread'] = df['ap0'] - df['bp0']
        
        # 3. Order Book Imbalance
        df['imbalance_l1'] = FeatureEngine._safe_div(
            (df['bs0'] - df['as0']), (df['bs0'] + df['as0'])
        )
        total_bid = df[['bs0','bs1','bs2','bs3','bs4']].sum(axis=1)
        total_ask = df[['as0','as1','as2','as3','as4']].sum(axis=1)
        df['imbalance_l5'] = FeatureEngine._safe_div((total_bid - total_ask), (total_bid + total_ask))

        # 4. 技术指标
        delta = mid_price.diff()
        up = delta.clip(lower=0)
        down = -1 * delta.clip(upper=0)
        ma_up = up.rolling(window=14).mean()
        ma_down = down.rolling(window=14).mean()
        rsi = 100 - (100 / (1 + FeatureEngine._safe_div(ma_up, ma_down)))
        df['rsi_14'] = rsi.fillna(50)

        df['volatility'] = mid_price.rolling(window=20).std().fillna(0)

        # 5. Trade Flow
        # [修改点 3] 对量取对数，但保留方向 (log1p 是 log(x+1) 防止报错)
        # 注意：因为 trade_flow 有正负，所以先取绝对值log，再乘回符号
        df['trade_flow'] = np.log1p(df['lt_sz']) * df['lt_side']
        
        # 6. 原始量 [修改点 4] 取对数
        df['ask_sz_0'] = np.log1p(df['as0'])
        df['bid_sz_0'] = np.log1p(df['bs0'])

        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        df.fillna(0, inplace=True)
        
        return df[config.FEATURES]

    # -------------------------------------------------------
    # 场景 B: 在线推理
    # -------------------------------------------------------
    @staticmethod
    def calculate_realtime_features(snapshot, history_prices):
        try:
            ap0 = float(snapshot['asks'][0][0])
            as0 = float(snapshot['asks'][0][1])
            bp0 = float(snapshot['bids'][0][0])
            bs0 = float(snapshot['bids'][0][1])
            
            # 1. Spread
            spread = ap0 - bp0
            
            # 2. Imbalance
            imbalance_l1 = (bs0 - as0) / (bs0 + as0) if (bs0 + as0) > 0 else 0.0
            
            sum_as = sum([float(x[1]) for x in snapshot['asks']])
            sum_bs = sum([float(x[1]) for x in snapshot['bids']])
            imbalance_l5 = (sum_bs - sum_as) / (sum_bs + sum_as) if (sum_bs + sum_as) > 0 else 0.0
            
            # 3. RSI / Volatility
            rsi = 50.0
            volatility = 0.0
            if len(history_prices) >= 20:
                prices = np.array(history_prices, dtype=np.float64)
                volatility = np.std(prices[-20:])
                deltas = np.diff(prices[-15:])
                gains = deltas[deltas > 0].sum()
                losses = -deltas[deltas < 0].sum()
                if losses == 0:
                    rsi = 100.0 if gains > 0 else 50.0
                else:
                    rs = gains / losses
                    rsi = 100 - (100 / (1 + rs))
            
            # 4. Trade Flow & Volumes [修改点 5] 实时计算也要取对数，保持一致
            lt_sz = float(snapshot.get('lt_sz', 0))
            lt_side = float(snapshot.get('lt_side', 0))
            
            trade_flow = np.log1p(lt_sz) * lt_side # Log处理
            
            ask_sz_log = np.log1p(as0) # Log处理
            bid_sz_log = np.log1p(bs0) # Log处理

            # 组装
            features = np.array([[
                spread, imbalance_l1, imbalance_l5, 
                ask_sz_log, bid_sz_log, rsi, volatility, trade_flow
            ]], dtype=np.float32)
            
            if np.isnan(features).any(): return None
            return features
            
        except Exception as e:
            return None