"""
前多少名的币价实时获取方案
"""
import time
import requests

def fetch_top(page,symbol_vs='usd'):
    url = 'https://api.coingecko.com/api/v3/coins/markets'
    params = {
        'vs_currency': symbol_vs,
        'order': 'market_cap_desc',
        'per_page': page,
        'page': 1,
        'sparkline': 'false'
    }
    resp = requests.get(url, params=params, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    # 返回一个列表，每项包含 id、symbol、current_price 等字段
    return data

def main():
    try:
        lens = 10
        while True:
            topn = fetch_top(lens)
            ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            print(f'[{ts}] 前{lens}虚拟币最新价格：')
            for coin in topn:
                print(f"  {coin['market_cap_rank']}. {coin['name']} ({coin['symbol'].upper()}): {coin['current_price']} USD")
            print('-' * 60)
            time.sleep(1)  # 等待 1 秒
    except KeyboardInterrupt:
        print('已停止抓取。')

if __name__ == '__main__':
    main()
