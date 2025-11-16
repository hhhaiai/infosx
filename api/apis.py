"""
pip install requests pandas matplotlib

"""
import requests
import time
import json
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import pandas as pd
from io import StringIO


class CoinGeckoAPI:
    """CoinGecko API 封装类"""

    BASE_URL = "https://api.coingecko.com/api/v3"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        })

    def get_top_coins(self, limit: int = 50, currency: str = 'usd') -> List[Dict]:
        """
        获取热门虚拟币排行、价格及简要走势

        Args:
            limit: 返回的币种数量
            currency: 计价货币

        Returns:
            币种信息列表
        """
        url = f"{self.BASE_URL}/coins/markets"
        params = {
            'vs_currency': currency,
            'order': 'market_cap_desc',
            'per_page': limit,
            'page': 1,
            'sparkline': 'true',  # 包含简要走势数据
            'price_change_percentage': '1h,24h,7d,30d'
        }

        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"CoinGecko API 错误: {e}")
            return []

    def get_coin_history(self, coin_id: str, days: str = 'max', currency: str = 'usd') -> Optional[Dict]:
        """
        获取币种历史价格数据

        Args:
            coin_id: 币种ID (如: 'bitcoin')
            days: 数据天数 ('1', '7', '30', '90', '365', 'max')
            currency: 计价货币

        Returns:
            历史价格数据
        """
        url = f"{self.BASE_URL}/coins/{coin_id}/market_chart"
        params = {
            'vs_currency': currency,
            'days': days,
            'interval': 'daily' if days != '1' else 'hourly'
        }

        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            # 格式化历史数据
            history_data = {
                'prices': data.get('prices', []),
                'market_caps': data.get('market_caps', []),
                'total_volumes': data.get('total_volumes', [])
            }

            return history_data
        except Exception as e:
            print(f"CoinGecko 历史数据获取错误: {e}")
            return None

    def get_coin_detail(self, coin_id: str) -> Optional[Dict]:
        """获取币种详细信息"""
        url = f"{self.BASE_URL}/coins/{coin_id}"
        params = {
            'localization': 'false',
            'tickers': 'false',
            'market_data': 'true',
            'community_data': 'false',
            'developer_data': 'false',
            'sparkline': 'false'
        }

        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"CoinGecko 详情获取错误: {e}")
            return None

    def search_coins(self, query: str) -> List[Dict]:
        """搜索币种"""
        url = f"{self.BASE_URL}/search"
        params = {'query': query}

        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get('coins', [])
        except Exception as e:
            print(f"CoinGecko 搜索错误: {e}")
            return []


class CoinMarketCapAPI:
    """CoinMarketCap API 封装类"""

    BASE_URL = "https://pro-api.coinmarketcap.com/v1"

    def __init__(self, api_key: str = None):
        """
        初始化 CoinMarketCap API

        Args:
            api_key: API密钥 (免费版可从官网获取)
        """
        self.api_key = api_key or 'your-api-key-here'  # 需要从官网申请免费API密钥
        self.session = requests.Session()
        self.session.headers.update({
            'X-CMC_PRO_API_KEY': self.api_key,
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def get_top_coins(self, limit: int = 50, currency: str = 'USD') -> List[Dict]:
        """
        获取热门虚拟币排行及价格

        Args:
            limit: 返回的币种数量
            currency: 计价货币

        Returns:
            币种信息列表
        """
        url = f"{self.BASE_URL}/cryptocurrency/listings/latest"
        params = {
            'start': 1,
            'limit': limit,
            'convert': currency,
            'sort': 'market_cap',
            'sort_dir': 'desc'
        }

        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get('data', [])
        except Exception as e:
            print(f"CoinMarketCap API 错误: {e}")
            if response.status_code == 401:
                print("请检查 API 密钥是否正确")
            return []

    def get_coin_history(self, coin_id: int, time_start: str = None,
                        time_end: str = None, count: int = 365,
                        interval: str = 'daily') -> Optional[Dict]:
        """
        获取币种历史价格数据

        Args:
            coin_id: 币种ID
            time_start: 开始时间 (格式: YYYY-MM-DD)
            time_end: 结束时间 (格式: YYYY-MM-DD)
            count: 数据点数
            interval: 时间间隔 ('daily', 'hourly', 'weekly', 'monthly')

        Returns:
            历史价格数据
        """
        # 设置默认时间范围（最近一年）
        if not time_end:
            time_end = datetime.now().strftime('%Y-%m-%d')
        if not time_start:
            start_date = datetime.now() - timedelta(days=count)
            time_start = start_date.strftime('%Y-%m-%d')

        url = f"{self.BASE_URL}/cryptocurrency/quotes/historical"
        params = {
            'id': coin_id,
            'time_start': time_start,
            'time_end': time_end,
            'count': count,
            'interval': interval,
            'convert': 'USD'
        }

        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"CoinMarketCap 历史数据获取错误: {e}")
            return None

    def get_coin_metadata(self, coin_id: int) -> Optional[Dict]:
        """获取币种元数据"""
        url = f"{self.BASE_URL}/cryptocurrency/info"
        params = {'id': coin_id}

        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get('data', {}).get(str(coin_id))
        except Exception as e:
            print(f"CoinMarketCap 元数据获取错误: {e}")
            return None


class CryptoDataAnalyzer:
    """加密货币数据分析器"""

    def __init__(self):
        self.gecko_api = CoinGeckoAPI()
        self.cmc_api = CoinMarketCapAPI()  # 需要设置有效的API密钥

    def display_top_coins_comparison(self, limit: int = 20):
        """比较两个API的Top币种数据"""
        print("🔍 比较 CoinGecko 和 CoinMarketCap 数据")
        print("=" * 100)

        # 获取两个API的数据
        gecko_data = self.gecko_api.get_top_coins(limit)
        cmc_data = self.cmc_api.get_top_coins(limit)

        print(f"{'Rank':<4} {'Coin':<20} {'Gecko Price':<15} {'CMC Price':<15} {'24h Change':<12}")
        print("-" * 100)

        for i, (gecko_coin, cmc_coin) in enumerate(zip(gecko_data, cmc_data)):
            rank = i + 1
            name = gecko_coin.get('name', 'Unknown')[:18]

            # CoinGecko 数据
            gecko_price = gecko_coin.get('current_price', 0)
            gecko_change = gecko_coin.get('price_change_percentage_24h', 0)

            # CoinMarketCap 数据
            cmc_price = cmc_coin.get('quote', {}).get('USD', {}).get('price', 0)
            cmc_change = cmc_coin.get('quote', {}).get('USD', {}).get('percent_change_24h', 0)

            print(f"{rank:<4} {name:<20} ${gecko_price:<14.2f} ${cmc_price:<14.2f} "
                  f"{gecko_change:+.2f}%/{cmc_change:+.2f}%")

    def analyze_coin_history(self, coin_id: str, coin_name: str, days: str = '365'):
        """分析币种历史走势"""
        print(f"\n📈 分析 {coin_name} 的历史走势 ({days}天)")

        # 获取历史数据
        history = self.gecko_api.get_coin_history(coin_id, days)

        if not history or 'prices' not in history:
            print("无法获取历史数据")
            return

        prices = history['prices']

        if not prices:
            print("没有可用的价格数据")
            return

        # 转换为DataFrame
        df = pd.DataFrame(prices, columns=['timestamp', 'price'])
        df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('date', inplace=True)

        # 计算统计信息
        start_price = df['price'].iloc[0]
        end_price = df['price'].iloc[-1]
        max_price = df['price'].max()
        min_price = df['price'].min()
        total_change = ((end_price - start_price) / start_price) * 100

        print(f"📊 {coin_name} 历史数据统计:")
        print(f"   开始价格: ${start_price:.2f}")
        print(f"   结束价格: ${end_price:.2f}")
        print(f"   最高价格: ${max_price:.2f}")
        print(f"   最低价格: ${min_price:.2f}")
        print(f"   总变化: {total_change:+.2f}%")
        print(f"   数据点数: {len(df)}")

        # 绘制价格走势图
        plt.figure(figsize=(12, 6))
        plt.plot(df.index, df['price'], linewidth=1)
        plt.title(f'{coin_name} Price History ({days} days)')
        plt.xlabel('Date')
        plt.ylabel('Price (USD)')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()

        return df

    def get_trending_coins(self) -> List[Dict]:
        """获取 trending 币种"""
        url = "https://api.coingecko.com/api/v3/search/trending"

        try:
            response = self.gecko_api.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get('coins', [])
        except Exception as e:
            print(f"获取 trending 币种错误: {e}")
            return []


def main():
    """主函数示例"""
    analyzer = CryptoDataAnalyzer()

    while True:
        print("\n" + "="*50)
        print("💰 加密货币数据分析工具")
        print("="*50)
        print("1. 显示热门币种排行")
        print("2. 分析币种历史走势")
        print("3. 显示 Trending 币种")
        print("4. 比较两个API数据")
        print("5. 退出")

        choice = input("\n请选择功能 (1-5): ").strip()

        if choice == '1':
            # 显示热门币种
            coins = analyzer.gecko_api.get_top_coins(20)
            print(f"\n🏆 热门加密货币排行 (前20)")
            print("="*80)
            print(f"{'Rank':<4} {'Coin':<20} {'Symbol':<8} {'Price (USD)':<12} {'24h Change':<12} {'7d Change':<12}")
            print("-"*80)

            for i, coin in enumerate(coins):
                rank = coin.get('market_cap_rank', i+1)
                name = coin.get('name', 'Unknown')[:18]
                symbol = coin.get('symbol', '').upper()
                price = coin.get('current_price', 0)
                change_24h = coin.get('price_change_percentage_24h', 0)
                change_7d = coin.get('price_change_percentage_7d', 0)

                print(f"{rank:<4} {name:<20} {symbol:<8} ${price:<11.2f} "
                      f"{change_24h:+.2f}%{'':<6} {change_7d:+.2f}%")

        elif choice == '2':
            # 分析历史走势
            coin_name = input("请输入币种名称 (如: bitcoin, ethereum): ").strip().lower()
            days = input("请输入天数 (1, 7, 30, 90, 365, max) [默认365]: ").strip() or '365'

            # 搜索币种
            search_results = analyzer.gecko_api.search_coins(coin_name)
            if search_results:
                coin = search_results[0]  # 取第一个结果
                coin_id = coin['id']
                display_name = coin['name']

                print(f"🔍 找到币种: {display_name} (ID: {coin_id})")
                analyzer.analyze_coin_history(coin_id, display_name, days)
            else:
                print("❌ 未找到该币种")

        elif choice == '3':
            # 显示 trending 币种
            trending = analyzer.get_trending_coins()
            print(f"\n🔥 当前 Trending 币种")
            print("="*60)

            for i, item in enumerate(trending[:10]):
                coin = item['item']
                name = coin['name']
                symbol = coin['symbol'].upper()
                market_cap_rank = coin.get('market_cap_rank', 'N/A')

                print(f"{i+1:>2}. {name:<20} {symbol:<8} (Rank: {market_cap_rank})")

        elif choice == '4':
            # 比较两个API
            analyzer.display_top_coins_comparison(10)

        elif choice == '5':
            print("👋 感谢使用！")
            break

        else:
            print("❌ 无效选择，请重新输入")

        input("\n按回车键继续...")


if __name__ == "__main__":
    main()