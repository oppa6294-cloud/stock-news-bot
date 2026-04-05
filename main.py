import os
import time
import requests
import schedule
from datetime import datetime, date, timedelta

# ================================================================
# ✅ 설정 - Railway 환경변수에 입력하세요
# ================================================================
TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
NAVER_CLIENT_ID     = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")
FINNHUB_API_KEY     = os.environ.get("FINNHUB_API_KEY", "")

# ================================================================
# 📋 보유 종목 설정
# ================================================================
KOREAN_STOCKS = [
    "하이텍팜",
    "씨에스윈드",
    "OCI홀딩스",
    "HL만도",
    "펩트론",
    "삼양바이오팜",
    "NAVER",
    "대명에너지",
    "서진시스템",
    "아스플로",
    "세아홀딩스",
    "토비스",
]

US_STOCKS = [
    "AAPL",   # Apple
    "TSLA",   # Tesla
    "NVDA",   # Nvidia
]

# 중복 뉴스 방지
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
        "disable_web_page_preview": True,
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
    today    = date.today().strftime("%Y-%m-%d")
    week_ago = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
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
# 뉴스 수집 & 요약 전송 (10분마다 실행)
# ----------------------------------------------------------------
def check_and_send_news():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n[{now}] 뉴스 확인 시작...")

    # 종목별 뉴스 모으기
    collected = {}   # { 종목명: [ {title, link} ] }

    # 한국 주식 뉴스 수집
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

            if stock not in collected:
                collected[stock] = []
            collected[stock].append({"title": title, "link": link})
            print(f"  ✅ 수집: [{stock}] {title[:30]}...")

    # 미국 주식 뉴스 수집
    for symbol in US_STOCKS:
        items = get_finnhub_news(symbol)
        for item in items:
            news_id = str(item.get("id", ""))
            if not news_id or news_id in sent_news_ids:
                continue
            sent_news_ids.add(news_id)

            title = item.get("headline", "")
            link  = item.get("url", "")

            if symbol not in collected:
                collected[symbol] = []
            collected[symbol].append({"title": title, "link": link})
            print(f"  ✅ 수집: [{symbol}] {title[:30]}...")

    # 새 뉴스가 없으면 전송 안 함
    if not collected:
        print("  → 새로운 뉴스 없음")
        return

    # 메시지 만들기
    message = f"📊 <b>[10분 뉴스 요약]</b>  {now}\n"
    message += "━" * 20 + "\n\n"

    for stock, news_list in collected.items():
        # 한국/미국 구분 이모지
        flag = "🇺🇸" if stock in US_STOCKS else "🇰🇷"
        message += f"{flag} <b>{stock}</b>\n"
        for news in news_list:
            message += f"• <a href=\"{news['link']}\">{news['title']}</a>\n"
        message += "\n"

    # 메시지가 너무 길면 분할 전송 (텔레그램 4096자 제한)
    total = sum(len(v) for v in collected.values())
    if len(message) <= 4096:
        send_telegram(message)
    else:
        # 종목별로 나눠서 전송
        header = f"📊 <b>[10분 뉴스 요약]</b>  {now}\n" + "━" * 20 + "\n\n"
        chunk = header
        for stock, news_list in collected.items():
            flag = "🇺🇸" if stock in US_STOCKS else "🇰🇷"
            part = f"{flag} <b>{stock}</b>\n"
            for news in news_list:
                part += f"• <a href=\"{news['link']}\">{news['title']}</a>\n"
            part += "\n"
            if len(chunk) + len(part) > 4096:
                send_telegram(chunk)
                time.sleep(1)
                chunk = part
            else:
                chunk += part
        if chunk:
            send_telegram(chunk)

    print(f"  → 총 {total}개 뉴스 전송 완료")


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

    # 이후 10분마다 자동 실행
    schedule.every(10).minutes.do(check_and_send_news)

    while True:
        schedule.run_pending()
        time.sleep(60)
