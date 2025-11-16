"""
加密货币价格实时监控系统 - 完整优化版
支持前N名币种价格实时获取，多货币显示，错误处理完善
"""
import time
import requests
from typing import List, Dict, Optional, Tuple
import sys
import json
from datetime import datetime


class CryptoPriceMonitor:
    """加密货币价格监控器"""

    # 类常量
    DEFAULT_REFRESH_INTERVAL = 30
    MAX_PER_PAGE = 250
    DEFAULT_TIMEOUT = 10
    DEFAULT_RETRY_COUNT = 3

    def __init__(self, base_currency: str = 'usd', timeout: int = None,
                 retry_count: int = None, refresh_interval: int = None):
        """
        初始化监控器

        Args:
            base_currency: 基准货币代码
            timeout: 请求超时时间(秒)
            retry_count: 重试次数
            refresh_interval: 刷新间隔(秒)
        """
        self.base_currency = base_currency.lower()
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.retry_count = retry_count or self.DEFAULT_RETRY_COUNT
        self.refresh_interval = refresh_interval or self.DEFAULT_REFRESH_INTERVAL

        # 创建会话
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json'
        })

        # 货币符号映射
        self.currency_symbols = {
            'usd': '$',
            'eur': '€',
            'gbp': '£',
            'jpy': '¥',
            'cny': 'CN¥',  # 使用CN¥区分日元和人民币
            'krw': '₩',
            'aud': 'A$',
            'cad': 'C$',
            'inr': '₹',
            'rub': '₽',
            'chf': 'CHF',
            'sgd': 'S$',
            'hkd': 'HK$'
        }

    def fetch_top_coins(self, count: int, page: int = 1) -> Optional[List[Dict]]:
        """
        获取前N名的加密货币数据

        Args:
            count: 要获取的币种数量
            page: 页码

        Returns:
            币种数据列表或None(失败时)
        """
        url = 'https://api.coingecko.com/api/v3/coins/markets'
        params = {
            'vs_currency': self.base_currency,
            'order': 'market_cap_desc',
            'per_page': min(count, self.MAX_PER_PAGE),
            'page': page,
            'sparkline': 'false',
            'price_change_percentage': '1h,24h,7d,30d'
        }

        for attempt in range(self.retry_count):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()

                if not data:
                    print("⚠️  未获取到数据，可能是API限制")
                    return None

                # 验证数据完整性
                validated_data = [coin for coin in data if self.validate_coin_data(coin)]
                if len(validated_data) < len(data):
                    print(f"⚠️  过滤了 {len(data) - len(validated_data)} 个无效数据项")

                return validated_data

            except requests.exceptions.Timeout:
                print(f"⏰  请求超时，第{attempt + 1}次重试...")
            except requests.exceptions.ConnectionError:
                print(f"🌐  网络连接错误，第{attempt + 1}次重试...")
            except requests.exceptions.HTTPError as e:
                if hasattr(e, 'response') and e.response.status_code == 429:
                    wait_time = 60
                    print(f"🚫  API频率限制，等待{wait_time}秒...")
                    time.sleep(wait_time)
                else:
                    status_code = e.response.status_code if hasattr(e, 'response') else 'Unknown'
                    print(f"❌  HTTP错误 {status_code}: {e}")
                    break
            except json.JSONDecodeError as e:
                print(f"❌  JSON解析错误: {e}")
                break
            except Exception as e:
                print(f"❌  意外错误: {e}")
                break

            if attempt < self.retry_count - 1:
                time.sleep(2 ** attempt)  # 指数退避策略

        return None

    def validate_coin_data(self, coin: Dict) -> bool:
        """
        验证币种数据完整性

        Args:
            coin: 币种数据字典

        Returns:
            数据是否有效
        """
        required_fields = ['id', 'symbol', 'name', 'current_price', 'market_cap_rank']
        return all(field in coin and coin[field] is not None for field in required_fields)

    def get_currency_symbol(self) -> str:
        """获取当前货币符号"""
        return self.currency_symbols.get(self.base_currency, self.base_currency.upper())

    def format_price(self, price: float) -> str:
        """
        格式化价格显示

        Args:
            price: 价格数值

        Returns:
            格式化后的价格字符串
        """
        symbol = self.get_currency_symbol()

        if price is None:
            return f"{symbol}N/A"
        elif price == 0:
            return f"{symbol}0"
        elif price >= 1000:
            return f"{symbol}{price:,.0f}"
        elif price >= 1:
            return f"{symbol}{price:,.2f}"
        elif price >= 0.01:
            return f"{symbol}{price:.4f}".rstrip('0').rstrip('.')
        elif price >= 0.0001:
            return f"{symbol}{price:.6f}".rstrip('0').rstrip('.')
        else:
            # 科学计数法显示极小数
            return f"{symbol}{price:.2e}"

    def format_percentage(self, percentage: float) -> str:
        """
        格式化百分比显示

        Args:
            percentage: 百分比数值

        Returns:
            格式化后的百分比字符串
        """
        if percentage is None:
            return "⚪ N/A"

        # 选择颜色和符号
        if percentage > 5:
            color_symbol = "🚀🟢"  # 大涨
        elif percentage > 2:
            color_symbol = "⬆️ 🟢"  # 上涨
        elif percentage > 0:
            color_symbol = "↗️ 🟢"  # 微涨
        elif percentage == 0:
            color_symbol = "➡️ ⚪"  # 平盘
        elif percentage > -2:
            color_symbol = "↘️ 🟠"  # 微跌
        elif percentage > -5:
            color_symbol = "⬇️ 🔴"  # 下跌
        else:
            color_symbol = "💥🔴"  # 大跌

        return f"{color_symbol} {percentage:+.2f}%"

    def format_large_number(self, number: float) -> str:
        """
        格式化大数字为K/M/B格式

        Args:
            number: 要格式化的数字

        Returns:
            格式化后的字符串
        """
        if number is None:
            return "N/A"

        if number >= 1e9:
            return f"{number/1e9:.1f}B"
        elif number >= 1e6:
            return f"{number/1e6:.1f}M"
        elif number >= 1e3:
            return f"{number/1e3:.1f}K"
        else:
            return f"{number:.0f}"

    def display_coins(self, coins: List[Dict], count: int):
        """
        显示加密货币数据

        Args:
            coins: 币种数据列表
            count: 显示的币种数量
        """
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        currency_symbol = self.get_currency_symbol()

        print(f'\n📊 [{ts}] Top {count} Cryptocurrencies (in {self.base_currency.upper()})')
        print("=" * 100)

        # 表头
        print(f"{'Rank':<4} {'Coin':<18} {'Symbol':<8} {'Price':<18} {'1h':<12} {'24h':<12} {'7d':<12} {'Market Cap':<12}")
        print("-" * 100)

        for coin in coins:
            rank = coin.get('market_cap_rank', 'N/A')
            name = coin.get('name', 'Unknown')[:16]
            symbol = coin.get('symbol', '').upper()[:6]
            price = self.format_price(coin.get('current_price'))
            market_cap = self.format_large_number(coin.get('market_cap'))

            # 获取价格变化百分比
            change_1h = coin.get('price_change_percentage_1h_in_currency')
            change_24h = coin.get('price_change_percentage_24h_in_currency')
            change_7d = coin.get('price_change_percentage_7d_in_currency')

            print(f"{rank:<4} {name:<18} {symbol:<8} {price:<18} "
                  f"{self.format_percentage(change_1h):<12} "
                  f"{self.format_percentage(change_24h):<12} "
                  f"{self.format_percentage(change_7d):<12} "
                  f"{market_cap:<12}")

        print("=" * 100)
        print(f"📈 Total displayed: {len(coins)} coins | 💰 Currency: {self.base_currency.upper()} ({currency_symbol})")
        print(f"🔄 Auto-refresh every {self.refresh_interval} seconds | ⏹️  Press Ctrl+C to stop")

    def get_api_status(self) -> bool:
        """检查API状态"""
        try:
            resp = self.session.get('https://api.coingecko.com/api/v3/ping', timeout=5)
            return resp.status_code == 200
        except:
            return False

    def run_monitor(self, top_count: int):
        """
        运行监控循环

        Args:
            top_count: 监控的前N名币种数量
        """
        print("🚀 Cryptocurrency Price Monitor Started!")
        print(f"📋 Monitoring top {top_count} coins in {self.base_currency.upper()}")
        print(f"⏰ Refresh interval: {self.refresh_interval} seconds")

        # 检查API状态
        if not self.get_api_status():
            print("❌ CoinGecko API 不可用，请检查网络连接")
            return

        print("✅ API连接正常")
        print("⏹️  Press Ctrl+C to stop\n")

        consecutive_errors = 0
        max_consecutive_errors = 5

        try:
            while True:
                coins = self.fetch_top_coins(top_count)

                if coins:
                    self.display_coins(coins, top_count)
                    consecutive_errors = 0  # 重置错误计数
                else:
                    consecutive_errors += 1
                    print(f"❌ 数据获取失败 ({consecutive_errors}/{max_consecutive_errors})")

                    if consecutive_errors >= max_consecutive_errors:
                        print("🚨 连续失败次数过多，程序退出")
                        break

                # 显示下次刷新时间
                next_refresh = time.time() + self.refresh_interval
                next_time = time.strftime('%H:%M:%S', time.localtime(next_refresh))
                print(f"\n🕒 Next update at: {next_time}")

                # 倒计时显示
                for i in range(self.refresh_interval, 0, -1):
                    print(f"\r🔄 Refreshing in {i:2d} seconds...", end="", flush=True)
                    time.sleep(1)
                print("\r" + " " * 30 + "\r", end="", flush=True)

        except KeyboardInterrupt:
            print("\n\n👋 Monitor stopped. Thank you for using!")
        except Exception as e:
            print(f"\n💥 Unexpected error: {e}")
            sys.exit(1)


def main():
    """主函数"""
    # 配置参数
    CONFIG = {
        'TOP_COUNT': 20,           # 要显示的前N名
        'REFRESH_INTERVAL': 5,    # 刷新间隔(秒)
        'BASE_CURRENCY': 'usd',    # 基准货币: usd, eur, jpy, cny等
        'TIMEOUT': 15,             # 请求超时时间
        'RETRY_COUNT': 3           # 重试次数
    }

    # 创建监控器实例
    monitor = CryptoPriceMonitor(
        base_currency=CONFIG['BASE_CURRENCY'],
        timeout=CONFIG['TIMEOUT'],
        retry_count=CONFIG['RETRY_COUNT'],
        refresh_interval=CONFIG['REFRESH_INTERVAL']
    )

    # 运行监控
    monitor.run_monitor(CONFIG['TOP_COUNT'])


if __name__ == '__main__':
    main()