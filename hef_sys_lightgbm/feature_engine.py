# feature_engine.py
import numpy as np
import pandas as pd
import config

class FeatureEngine:
    @staticmethod
    def _safe_div(a, b):
        return np.divide(a, b, out=np.zeros_like(a), where=b!=0)

    # --- 离线训练 ---
    @staticmethod
    def calculate_train_features(df):
        mid_price = (df['ap0'] + df['bp0']) / 2
        
        # 1. Spread
        df['spread'] = df['ap0'] - df['bp0']
        
        # 2. Imbalance
        df['imbalance_l1'] = FeatureEngine._safe_div(
            (df['bs0'] - df['as0']), (df['bs0'] + df['as0'])
        )
        total_bid = df[['bs0','bs1','bs2','bs3','bs4']].sum(axis=1)
        total_ask = df[['as0','as1','as2','as3','as4']].sum(axis=1)
        df['imbalance_l5'] = FeatureEngine._safe_div((total_bid - total_ask), (total_bid + total_ask))

        # 3. RSI & Volatility
        delta = mid_price.diff()
        up = delta.clip(lower=0)
        down = -1 * delta.clip(upper=0)
        rsi = 100 - (100 / (1 + FeatureEngine._safe_div(up.rolling(14).mean(), down.rolling(14).mean())))
        df['rsi_14'] = rsi.fillna(50)
        df['volatility'] = mid_price.rolling(20).std().fillna(0)

        # 4. Trade Flow
        df['trade_flow'] = df['lt_sz'] * df['lt_side']
        
        # 5. Raw Size
        df['ask_sz_0'] = df['as0']
        df['bid_sz_0'] = df['bs0']

        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        df.fillna(0, inplace=True)
        
        return df[config.FEATURES]

    # --- 在线推理 ---
    @staticmethod
    def calculate_realtime_features(snapshot, history_prices):
        try:
            ap0, as0 = snapshot['asks'][0]
            bp0, bs0 = snapshot['bids'][0]
            
            spread = ap0 - bp0
            imbalance_l1 = (bs0 - as0) / (bs0 + as0) if (bs0 + as0) > 0 else 0
            
            sum_as = sum([x[1] for x in snapshot['asks']])
            sum_bs = sum([x[1] for x in snapshot['bids']])
            imbalance_l5 = (sum_bs - sum_as) / (sum_bs + sum_as) if (sum_bs + sum_as) > 0 else 0
            
            rsi = 50.0
            volatility = 0.0
            
            if len(history_prices) >= 20:
                prices = np.array(history_prices[-20:], dtype=np.float32)
                volatility = np.std(prices)
                deltas = np.diff(prices[-15:])
                gains = deltas[deltas > 0].sum()
                losses = -deltas[deltas < 0].sum()
                if losses == 0:
                    rsi = 100.0 if gains > 0 else 50.0
                else:
                    rsi = 100 - (100 / (1 + gains / losses))
            
            trade_flow = snapshot.get('lt_sz', 0) * snapshot.get('lt_side', 0)
            
            # 必须是 2D 数组 (1, N_Features)
            features = np.array([[
                spread, imbalance_l1, imbalance_l5, 
                as0, bs0, rsi, volatility, trade_flow
            ]], dtype=np.float32)
            
            if np.isnan(features).any(): return None
            return features
            
        except Exception:
            return None