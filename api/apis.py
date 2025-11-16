import requests
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime
import matplotlib.pyplot as plt
import time
import random


class CryptoDataFetcher:
    """加密货币数据获取器 - 修复版"""
    
    BASE_URL = "https://api.coingecko.com/api/v3"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9'
        })
        self.request_count = 0
        self.last_request_time = 0

    def _rate_limit(self):
        """速率限制，避免API限制"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        # 免费API限制：10-30次/分钟，我们保守一点
        if time_since_last < 2:  # 至少2秒间隔
            time.sleep(2 - time_since_last)
        
        self.last_request_time = time.time()
        self.request_count += 1
        
        # 每10次请求后等待更长时间
        if self.request_count % 10 == 0:
            time.sleep(5)

    def get_top_coins(self, limit: int = 50, currency: str = 'usd') -> List[Dict]:
        """
        获取主流Top N币种信息
        """
        self._rate_limit()
        
        url = f"{self.BASE_URL}/coins/markets"
        params = {
            'vs_currency': currency,
            'order': 'market_cap_desc',
            'per_page': limit,
            'page': 1,
            'sparkline': 'false',
            'price_change_percentage': '1h,24h,7d,30d,200d,1y'
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 429:
                print("⚠️  API速率限制，等待60秒后重试...")
                time.sleep(60)
                return self.get_top_coins(limit, currency)
                
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"❌ API请求错误: {e}")
            return []
        except Exception as e:
            print(f"❌ 未知错误: {e}")
            return []

    def get_coin_history(self, coin_id: str, days: str = '365', currency: str = 'usd') -> Optional[pd.DataFrame]:
        """
        获取币种历史价格数据 - 修复版本
        
        注意：免费API有天数限制，建议使用365天以内
        """
        self._rate_limit()
        
        # 免费API限制：不能直接获取所有历史数据，最大支持365天
        if days == 'max':
            days = '365'
            print("⚠️  免费API限制：最多获取365天数据")
        
        url = f"{self.BASE_URL}/coins/{coin_id}/market_chart"
        params = {
            'vs_currency': currency,
            'days': days,
            'interval': 'daily'
        }
        
        try:
            response = self.session.get(url, params=params, timeout=15)
            
            if response.status_code == 429:
                print("⚠️  API速率限制，等待60秒后重试...")
                time.sleep(60)
                return self.get_coin_history(coin_id, days, currency)
                
            response.raise_for_status()
            data = response.json()
            
            # 转换为DataFrame
            prices = data.get('prices', [])
            if not prices:
                print("❌ 没有获取到价格数据")
                return None
                
            df = pd.DataFrame(prices, columns=['timestamp', 'price'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('datetime', inplace=True)
            df.drop('timestamp', axis=1, inplace=True)
            
            print(f"✅ 成功获取 {len(df)} 条历史价格数据")
            return df
            
        except requests.exceptions.RequestException as e:
            print(f"❌ 历史数据获取错误: {e}")
            if hasattr(e, 'response') and e.response.status_code == 404:
                print("❌ 币种ID不存在，请检查币种名称")
            return None
        except Exception as e:
            print(f"❌ 未知错误: {e}")
            return None

    def search_coin(self, query: str) -> Optional[Dict]:
        """搜索币种信息"""
        self._rate_limit()
        
        url = f"{self.BASE_URL}/search"
        params = {'query': query}
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 429:
                print("⚠️  API速率限制，等待60秒后重试...")
                time.sleep(60)
                return self.search_coin(query)
                
            response.raise_for_status()
            data = response.json()
            coins = data.get('coins', [])
            
            if coins:
                print(f"✅ 找到币种: {coins[0]['name']} (ID: {coins[0]['id']})")
                return coins[0]
            else:
                print("❌ 未找到匹配的币种")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 搜索错误: {e}")
            return None


class CryptoAnalyzer:
    """加密货币分析器 - 修复版"""
    
    def __init__(self):
        self.fetcher = CryptoDataFetcher()

    def display_top_coins(self, limit: int = 20, currency: str = 'usd'):
        """显示Top N币种信息"""
        print(f"\n🔄 正在获取Top {limit}加密货币数据...")
        coins = self.fetcher.get_top_coins(limit, currency)
        
        if not coins:
            print("❌ 无法获取数据，请检查网络连接或稍后重试")
            return
        
        print(f"\n🏆 加密货币Top {limit} ({currency.upper()})")
        print("=" * 120)
        print(f"{'排名':<4} {'名称':<20} {'代码':<8} {'当前价格':<12} {'1小时':<8} {'24小时':<8} {'7天':<8} {'30天':<8}")
        print("-" * 120)
        
        for coin in coins:
            rank = coin.get('market_cap_rank', 'N/A')
            name = coin.get('name', '')[:18]
            symbol = coin.get('symbol', '').upper()
            price = coin.get('current_price', 0)
            
            # 价格变化百分比
            change_1h = coin.get('price_change_percentage_1h_in_currency', 0) or 0
            change_24h = coin.get('price_change_percentage_24h_in_currency', 0) or 0
            change_7d = coin.get('price_change_percentage_7d_in_currency', 0) or 0
            change_30d = coin.get('price_change_percentage_30d_in_currency', 0) or 0
            
            print(f"{rank:<4} {name:<20} {symbol:<8} {price:>10.2f} {change_1h:>+7.1f}% {change_24h:>+7.1f}% "
                  f"{change_7d:>+7.1f}% {change_30d:>+7.1f}%")

    def analyze_coin_history(self, coin_query: str, currency: str = 'usd', days: str = '365'):
        """分析币种历史走势"""
        print(f"\n🔍 正在搜索币种: {coin_query}")
        
        # 搜索币种
        coin_info = self.fetcher.search_coin(coin_query)
        if not coin_info:
            return None
        
        coin_id = coin_info['id']
        coin_name = coin_info['name']
        
        print(f"\n📈 正在获取 {coin_name} 的历史价格数据 ({days}天)...")
        
        # 获取历史数据
        df = self.fetcher.get_coin_history(coin_id, days, currency)
        
        if df is None or df.empty:
            return None
        
        # 显示数据统计
        self._display_history_stats(df, coin_name, currency)
        
        # 显示数据预览
        self._display_data_preview(df, currency)
        
        # 绘制价格走势
        self._plot_price_history(df, coin_name, currency)
        
        return df

    def _display_history_stats(self, df: pd.DataFrame, coin_name: str, currency: str):
        """显示历史数据统计"""
        print(f"\n📊 {coin_name} 历史数据统计:")
        print("-" * 50)
        
        start_price = df['price'].iloc[0]
        end_price = df['price'].iloc[-1]
        max_price = df['price'].max()
        min_price = df['price'].min()
        total_change = ((end_price - start_price) / start_price) * 100
        
        print(f"时间范围: {df.index[0].strftime('%Y-%m-%d')} 至 {df.index[-1].strftime('%Y-%m-%d')}")
        print(f"数据点数: {len(df):,}")
        print(f"起始价格: {start_price:.2f} {currency.upper()}")
        print(f"当前价格: {end_price:.2f} {currency.upper()}")
        print(f"历史最高: {max_price:.2f} {currency.upper()}")
        print(f"历史最低: {min_price:.2f} {currency.upper()}")
        print(f"累计涨跌: {total_change:+.2f}%")

    def _display_data_preview(self, df: pd.DataFrame, currency: str):
        """显示数据预览"""
        print(f"\n📋 数据预览:")
        print("-" * 40)
        
        # 显示前5条
        print("最早的数据:")
        for i in range(min(5, len(df))):
            date = df.index[i].strftime('%Y-%m-%d')
            price = df['price'].iloc[i]
            print(f"  {date}: {price:.2f} {currency.upper()}")
        
        # 显示后5条  
        print("\n最新的数据:")
        for i in range(max(0, len(df)-5), len(df)):
            date = df.index[i].strftime('%Y-%m-%d')
            price = df['price'].iloc[i]
            print(f"  {date}: {price:.2f} {currency.upper()}")

    def _plot_price_history(self, df: pd.DataFrame, coin_name: str, currency: str):
        """绘制价格历史图表"""
        try:
            plt.figure(figsize=(12, 6))
            plt.plot(df.index, df['price'], linewidth=1, color='#007acc')
            plt.title(f'{coin_name} 价格历史走势', fontsize=14, fontweight='bold')
            plt.xlabel('日期')
            plt.ylabel(f'价格 ({currency.upper()})')
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.show()
        except Exception as e:
            print(f"❌ 图表绘制失败: {e}")


def main():
    """主函数"""
    analyzer = CryptoAnalyzer()
    
    while True:
        print("\n" + "="*50)
        print("💰 加密货币数据分析工具")
        print("="*50)
        print("1. 显示Top N币种排行")
        print("2. 分析币种历史走势")
        print("3. 退出")
        
        choice = input("\n请选择功能 (1-3): ").strip()
        
        if choice == '1':
            try:
                limit = int(input("显示前多少名? (默认20): ") or "20")
                currency = input("计价货币? (usd/cny, 默认usd): ").lower() or "usd"
                analyzer.display_top_coins(limit, currency)
            except ValueError:
                print("❌ 输入无效，使用默认值")
                analyzer.display_top_coins()
                
        elif choice == '2':
            coin_name = input("请输入币种名称或代码 (如: bitcoin/btc): ").strip()
            if coin_name:
                currency = input("计价货币? (usd/cny, 默认usd): ").lower() or "usd"
                days = input("数据天数? (7/30/90/365, 默认365): ").strip() or "365"
                analyzer.analyze_coin_history(coin_name, currency, days)
            else:
                print("❌ 请输入有效的币种名称")
                
        elif choice == '3':
            print("👋 感谢使用！")
            break
            
        else:
            print("❌ 无效选择")
        
        input("\n按回车键继续...")


if __name__ == "__main__":
    main()