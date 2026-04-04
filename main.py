import os
import time
import requests
import schedule
from datetime import datetime, date, timedelta

# ================================================================
# ✅ 설정 - 아래 값들을 Railway 환경변수에 입력하세요
# ================================================================
TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")   # BotFather에서 받은 토큰
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")  # 채널 ID (예: @mychannel)
NAVER_CLIENT_ID     = os.environ.get("NAVER_CLIENT_ID", "")       # 네이버 API Client ID
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")   # 네이버 API Client Secret
FINNHUB_API_KEY     = os.environ.get("FINNHUB_API_KEY", "")       # Finnhub API Key

# ================================================================
# 📋 보유 종목 설정 - 본인 종목으로 수정하세요
# ================================================================
KOREAN_STOCKS = [
    "삼성전자",
    "SK하이닉스",
    "하이텍팜",
    "씨에스윈드",
    "OCI홀딩스",
    "HL만도",
    "펩트론",
    "삼양바이오팜",
    "NAVER",
    "대명에너지",
]

US_STOCKS = [
    "AAPL",   # Apple
    "TSLA",   # Tesla
    "NVDA",   # Nvidia
]

# ================================================================
# 중복 뉴스 방지 (이미 보낸 뉴스는 다시 보내지 않음)
# ================================================================
sent_news_ids = set()


# ----------------------------------------------------------------
# 텔레그램 메시지 전송
# ----------------------------------------------------------------
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code != 200:
            print(f"  ⚠️ 텔레그램 오류: {r.text}")
    except Exception as e:
        print(f"  ⚠️ 텔레그램 전송 실패: {e}")


# ----------------------------------------------------------------
# 네이버 뉴스 검색 (한국 주식)
# ----------------------------------------------------------------
def get_naver_news(keyword):
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {
        "query": f"{keyword} 주식",
        "display": 5,
        "sort": "date",
    }
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        return r.json().get("items", [])
    except Exception as e:
        print(f"  ⚠️ 네이버 API 오류 ({keyword}): {e}")
        return []


# ----------------------------------------------------------------
# Finnhub 뉴스 검색 (미국 주식)
# ----------------------------------------------------------------
def get_finnhub_news(symbol):
    today     = date.today().strftime("%Y-%m-%d")
    week_ago  = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
    url = "https://finnhub.io/api/v1/company-news"
    params = {
        "symbol": symbol,
        "from": week_ago,
        "to": today,
        "token": FINNHUB_API_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        return data[:5] if isinstance(data, list) else []
    except Exception as e:
        print(f"  ⚠️ Finnhub API 오류 ({symbol}): {e}")
        return []


# ----------------------------------------------------------------
# 뉴스 확인 & 전송 메인 함수 (30분마다 실행)
# ----------------------------------------------------------------
def check_and_send_news():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{now}] 뉴스 확인 시작...")

    # 한국 주식 뉴스
    for stock in KOREAN_STOCKS:
        items = get_naver_news(stock)
        for item in items:
            news_id = item.get("link", "")
            if not news_id or news_id in sent_news_ids:
                continue
            sent_news_ids.add(news_id)

            title = (item.get("title", "")
                     .replace("<b>", "").replace("</b>", "")
                     .replace("&amp;", "&").replace("&quot;", '"'))
            link  = item.get("originallink") or item.get("link", "")

            message = (
                f"🇰🇷 <b>[{stock}]</b>\n"
                f"📰 {title}\n"
                f"🔗 {link}"
            )
            send_telegram(message)
            print(f"  ✅ 전송: [{stock}] {title[:30]}...")
            time.sleep(1)

    # 미국 주식 뉴스
    for symbol in US_STOCKS:
        items = get_finnhub_news(symbol)
        for item in items:
            news_id = str(item.get("id", ""))
            if not news_id or news_id in sent_news_ids:
                continue
            sent_news_ids.add(news_id)

            headline = item.get("headline", "")
            link     = item.get("url", "")

            message = (
                f"🇺🇸 <b>[{symbol}]</b>\n"
                f"📰 {headline}\n"
                f"🔗 {link}"
            )
            send_telegram(message)
            print(f"  ✅ 전송: [{symbol}] {headline[:30]}...")
            time.sleep(1)

    print("  → 확인 완료")


# ----------------------------------------------------------------
# 실행 시작
# ----------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 40)
    print("📈 주식 뉴스 봇 시작!")
    print(f"  한국 종목: {', '.join(KOREAN_STOCKS)}")
    print(f"  미국 종목: {', '.join(US_STOCKS)}")
    print("=" * 40)

    # 시작하자마자 즉시 1회 실행
    check_and_send_news()

    # 이후 30분마다 자동 실행
    schedule.every(30).minutes.do(check_and_send_news)

    while True:
        schedule.run_pending()
        time.sleep(60)
