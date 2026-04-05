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
DART_API_KEY        = os.environ.get("DART_API_KEY", "")

# ================================================================
# 📋 보유 종목 (주식 뉴스)
# ================================================================
KOREAN_STOCKS = [
    "하이텍팜", "씨에스윈드", "OCI홀딩스", "HL만도",
    "펩트론", "삼양바이오팜", "NAVER", "대명에너지",
    "서진시스템", "아스플로", "세아홀딩스", "토비스",
]
US_STOCKS = ["AAPL", "TSLA", "NVDA"]

# ================================================================
# DART 감시 공시 유형
# ================================================================
TARGET_REPORTS = [
    "주요사항보고서(전환사채권발행결정)",
    "전환사채권발행결정",
    "주요사항보고서(유상증자결정)",
    "유상증자결정",
    "주요사항보고서(자기전환사채만기전취득결정)",
    "증여결정",
    "주요사항보고서(타법인주식및출자증권양수결정)",
    "주요사항보고서(무상증자결정)",
    "무상증자결정",
]

sent_news_ids = set()
sent_dart_ids = set()


# ----------------------------------------------------------------
# 공통: 텔레그램 전송
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


# ================================================================
# 주식 뉴스 (10분마다)
# ================================================================

def get_naver_news(keyword):
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": f"{keyword} 주식", "display": 5, "sort": "date"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        return r.json().get("items", [])
    except Exception as e:
        print(f"  ⚠️ 네이버 API 오류 ({keyword}): {e}")
        return []

def get_finnhub_news(symbol):
    today    = date.today().strftime("%Y-%m-%d")
    week_ago = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
    url = "https://finnhub.io/api/v1/company-news"
    params = {"symbol": symbol, "from": week_ago, "to": today, "token": FINNHUB_API_KEY}
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        return data[:5] if isinstance(data, list) else []
    except Exception as e:
        print(f"  ⚠️ Finnhub API 오류 ({symbol}): {e}")
        return []

def check_and_send_news():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n[{now}] 뉴스 확인 시작...")
    collected = {}

    for stock in KOREAN_STOCKS:
        for item in get_naver_news(stock):
            news_id = item.get("link", "")
            if not news_id or news_id in sent_news_ids:
                continue
            sent_news_ids.add(news_id)
            title = (item.get("title", "")
                     .replace("<b>", "").replace("</b>", "")
                     .replace("&amp;", "&").replace("&quot;", '"'))
            link = item.get("originallink") or item.get("link", "")
            if stock not in collected:
                collected[stock] = []
            collected[stock].append({"title": title, "link": link})

    for symbol in US_STOCKS:
        for item in get_finnhub_news(symbol):
            news_id = str(item.get("id", ""))
            if not news_id or news_id in sent_news_ids:
                continue
            sent_news_ids.add(news_id)
            if symbol not in collected:
                collected[symbol] = []
            collected[symbol].append({
                "title": item.get("headline", ""),
                "link":  item.get("url", ""),
            })

    if not collected:
        print("  → 새로운 뉴스 없음")
        return

    message = f"📊 <b>[10분 뉴스 요약]</b>  {now}\n" + "━" * 20 + "\n\n"
    for stock, news_list in collected.items():
        flag = "🇺🇸" if stock in US_STOCKS else "🇰🇷"
        message += f"{flag} <b>{stock}</b>\n"
        for news in news_list:
            message += f"• <a href=\"{news['link']}\">{news['title']}</a>\n"
        message += "\n"

    total = sum(len(v) for v in collected.values())
    if len(message) <= 4096:
        send_telegram(message)
    else:
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


# ================================================================
# DART 공시 모니터링 (10분마다)
# ================================================================

def add_months(d, n):
    """월 더하기 (timedelta는 월 단위 미지원)"""
    month = d.month - 1 + n
    year  = d.year + month // 12
    month = month % 12 + 1
    return d.replace(year=year, month=month, day=1)

def parse_dart_date(s):
    """DART 날짜 문자열 → date 객체"""
    if not s or s.strip() in ("-", ""):
        return None
    for fmt in ["%Y년 %m월 %d일", "%Y-%m-%d", "%Y%m%d", "%Y.%m.%d"]:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except:
            continue
    return None

def fmt_date(s):
    """날짜 문자열을 YYYY-MM-DD 형식으로 통일"""
    d = parse_dart_date(s)
    return d.strftime("%Y-%m-%d") if d else (s or "-")

def fmt_amount(s):
    """숫자 → 억 단위 포맷"""
    try:
        n = int(str(s).replace(",", "").replace(" ", "").replace("원", ""))
        if n >= 100000000:
            return f"{n // 100000000}억"
        elif n >= 10000:
            return f"{n // 10000}만"
        return f"{n:,}"
    except:
        return str(s)

def get_stock_info(stock_code):
    """네이버 금융에서 현재가 / 등락률 / 시가총액 조회"""
    if not stock_code or not stock_code.strip():
        return "-", "-", "-"
    try:
        url = f"https://m.stock.naver.com/api/stock/{stock_code.strip()}/basic"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        d = r.json()
        price      = d.get("closePrice", "-")
        change_rt  = d.get("fluctuationsRatio", "-")
        mcap_raw   = d.get("marketValue", 0)
        mcap = f"{int(str(mcap_raw).replace(',','')) // 100000000}억" if mcap_raw else "-"
        return price, change_rt, mcap
    except Exception as e:
        print(f"  주가 조회 오류 ({stock_code}): {e}")
        return "-", "-", "-"

def rate_str(change_rt):
    """등락률 문자열 포맷"""
    try:
        v = float(str(change_rt).replace("%", "").replace("+", ""))
        return f"+{change_rt}%" if v > 0 else f"{change_rt}%"
    except:
        return f"{change_rt}%"

def get_dart_list():
    """오늘 DART 공시 목록 (대상 유형만)"""
    url = "https://opendart.fss.or.kr/api/list.json"
    today = date.today().strftime("%Y%m%d")
    params = {
        "crtfc_key": DART_API_KEY,
        "bgn_de":    today,
        "end_de":    today,
        "page_count": 100,
        "sort":       "date",
        "sort_mth":   "desc",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if data.get("status") == "000":
            return [x for x in data.get("list", [])
                    if x.get("report_nm", "") in TARGET_REPORTS]
        print(f"  DART 상태: {data.get('status')} - {data.get('message')}")
    except Exception as e:
        print(f"  DART 목록 오류: {e}")
    return []

def get_cb_detail(corp_code):
    """전환사채 상세 정보"""
    url = "https://opendart.fss.or.kr/api/cblnd.json"
    today    = date.today().strftime("%Y%m%d")
    bgn_de   = (date.today() - timedelta(days=14)).strftime("%Y%m%d")
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bgn_de":    bgn_de,
        "end_de":    today,
        "page_count": 10,
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if data.get("status") == "000":
            items = data.get("list", [])
            return items[0] if items else {}
    except Exception as e:
        print(f"  CB 상세 오류: {e}")
    return {}

def build_cb_msg(corp_name, stock_code, report_nm, rcept_dt,
                 price, change_rt, mcap, rcept_no, det):
    """전환사채 공시 메시지"""
    dt = f"{rcept_dt[:4]}.{rcept_dt[4:6]}.{rcept_dt[6:8]}"

    bd_fta      = fmt_amount(det.get("bd_fta", "-"))
    otkp_mths   = det.get("otkp_mths", "-")
    iss_price   = det.get("nstk_issue_price", "-")
    cvt_prce    = det.get("nstk_cvt_prce", "-")
    bd_inrt     = det.get("bd_inrt", "-")
    bd_rint     = det.get("bd_rint", "-")
    bd_pymd     = fmt_date(det.get("bd_pymd", "-"))
    sale_bgd    = fmt_date(det.get("nstk_sale_bgd", "-"))
    sale_edd    = fmt_date(det.get("nstk_sale_edd", "-"))

    msg  = f"📌 {corp_name}"
    if mcap != "-":
        msg += f"(시가총액: {mcap})"
    if stock_code and stock_code.strip():
        msg += f" #A{stock_code.strip()}"
    msg += "\n"
    msg += f"📁 {report_nm}\n"
    msg += f"{dt} (현재가 : {price}원, {rate_str(change_rt)})\n"
    msg += f"발행금액 : {bd_fta}\n"
    msg += f"발행방법 : {otkp_mths}\n"
    msg += f"전환가액 : {iss_price}원(현재가 : {price}원)\n"
    msg += f"최저조정 : {cvt_prce}원\n"
    msg += f"표면이율 : {bd_inrt}%\n"
    if bd_rint not in ("-", "", None):
        msg += f"만기이율 : {bd_rint}%\n"
    msg += f"납입일자 : {bd_pymd}\n"
    msg += f"청구시작 : {sale_bgd}\n"
    msg += f"청구종료 : {sale_edd}\n"
    msg += f"공시링크: https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}\n"
    if stock_code and stock_code.strip():
        msg += f"회사정보: https://finance.naver.com/item/main.nhn?code={stock_code.strip()}"
    return msg

def build_general_msg(corp_name, stock_code, report_nm, rcept_dt,
                      price, change_rt, mcap, rcept_no):
    """일반 공시 메시지"""
    dt = f"{rcept_dt[:4]}.{rcept_dt[4:6]}.{rcept_dt[6:8]}"
    msg  = f"📌 {corp_name}"
    if mcap != "-":
        msg += f"(시가총액: {mcap})"
    if stock_code and stock_code.strip():
        msg += f" #A{stock_code.strip()}"
    msg += "\n"
    msg += f"📁 {report_nm}\n"
    msg += f"{dt} (현재가 : {price}원, {rate_str(change_rt)})\n"
    msg += f"공시링크: https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}\n"
    if stock_code and stock_code.strip():
        msg += f"회사정보: https://finance.naver.com/item/main.nhn?code={stock_code.strip()}"
    return msg

def check_dart():
    """DART 공시 확인 및 개별 전송 (10분마다)"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] DART 공시 확인...")
    items = get_dart_list()
    if not items:
        print("  → 새 공시 없음")
        return

    for item in items:
        rcept_no  = item.get("rcept_no", "")
        if not rcept_no or rcept_no in sent_dart_ids:
            continue
        sent_dart_ids.add(rcept_no)

        corp_name  = item.get("corp_name", "")
        stock_code = item.get("stock_code", "")
        report_nm  = item.get("report_nm", "")
        corp_code  = item.get("corp_code", "")
        rcept_dt   = item.get("rcept_dt", "")

        price, change_rt, mcap = get_stock_info(stock_code)

        if "전환사채" in report_nm:
            det = get_cb_detail(corp_code)
            msg = build_cb_msg(corp_name, stock_code, report_nm, rcept_dt,
                               price, change_rt, mcap, rcept_no, det)
        else:
            msg = build_general_msg(corp_name, stock_code, report_nm, rcept_dt,
                                    price, change_rt, mcap, rcept_no)

        send_telegram(msg)
        print(f"  ✅ DART 전송: [{corp_name}] {report_nm}")
        time.sleep(2)


# ================================================================
# CB 월별 요약 (매주 토요일 10:00)
# ================================================================

def send_cb_monthly_summary():
    """청구시작일이 다음달/다다음달인 CB를 월별로 묶어 전송"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 월별 CB 요약 전송...")

    today       = date.today()
    next_month  = add_months(today, 1)
    month_after = add_months(today, 2)

    # 최근 90일 전환사채 공시 조회
    url = "https://opendart.fss.or.kr/api/cblnd.json"
    params = {
        "crtfc_key": DART_API_KEY,
        "bgn_de":    (today - timedelta(days=90)).strftime("%Y%m%d"),
        "end_de":    today.strftime("%Y%m%d"),
        "page_count": 100,
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        all_items = data.get("list", []) if data.get("status") == "000" else []
    except Exception as e:
        print(f"  CB 목록 오류: {e}")
        all_items = []

    # 청구시작일 기준으로 분류 (경과 종목 제외)
    buckets = {next_month: [], month_after: []}

    for item in all_items:
        sale_bgd = parse_dart_date(item.get("nstk_sale_bgd", ""))
        if not sale_bgd or sale_bgd < today:
            continue
        key = sale_bgd.replace(day=1)
        if key in buckets:
            buckets[key].append(item)

    def build_summary(title, items):
        msg = f"📅 <b>{title}</b>\n" + "━" * 20 + "\n\n"
        for item in items:
            corp_name  = item.get("corp_name", "")
            stock_code = item.get("stock_code", "")
            bd_fta     = fmt_amount(item.get("bd_fta", "-"))
            otkp_mths  = item.get("otkp_mths", "-")
            iss_price  = item.get("nstk_issue_price", "-")
            cvt_prce   = item.get("nstk_cvt_prce", "-")
            sale_bgd   = fmt_date(item.get("nstk_sale_bgd", "-"))
            sale_edd   = fmt_date(item.get("nstk_sale_edd", "-"))
            rcept_no   = item.get("rcept_no", "")

            price, change_rt, mcap = get_stock_info(stock_code)

            msg += f"📌 <b>{corp_name}</b>"
            if stock_code and stock_code.strip():
                msg += f" #A{stock_code.strip()}"
            msg += "\n"
            if mcap != "-":
                msg += f"시가총액: {mcap}\n"
            msg += f"발행금액: {bd_fta}\n"
            msg += f"발행방법: {otkp_mths}\n"
            msg += f"전환가액: {iss_price}원 (현재가: {price}원, {rate_str(change_rt)})\n"
            msg += f"최저조정: {cvt_prce}원\n"
            msg += f"청구시작: {sale_bgd}\n"
            msg += f"청구종료: {sale_edd}\n"
            if rcept_no:
                msg += f"공시링크: https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}\n"
            if stock_code and stock_code.strip():
                msg += f"회사정보: https://finance.naver.com/item/main.nhn?code={stock_code.strip()}\n"
            msg += "\n"
            time.sleep(0.5)
        return msg

    sent = False
    for month_key, items in buckets.items():
        if items:
            title = f"[{month_key.strftime('%Y년 %m월')} 전환청구 예정 CB 목록]"
            msg = build_summary(title, items)
            if len(msg) <= 4096:
                send_telegram(msg)
            else:
                # 너무 길면 분할
                chunk = f"📅 <b>{title}</b>\n" + "━" * 20 + "\n\n"
                for item in items:
                    part = build_summary("", [item])[len("━" * 20) + 2:]
                    if len(chunk) + len(part) > 4096:
                        send_telegram(chunk)
                        time.sleep(1)
                        chunk = part
                    else:
                        chunk += part
                if chunk:
                    send_telegram(chunk)
            sent = True
            time.sleep(2)

    if not sent:
        print("  → 해당 월 CB 없음")
    else:
        print(f"  → 다음달 {len(buckets[next_month])}개 / 다다음달 {len(buckets[month_after])}개 전송 완료")


# ================================================================
# 실행 시작
# ================================================================
if __name__ == "__main__":
    print("=" * 40)
    print("📈 주식 뉴스 + DART 공시 봇 시작!")
    print(f"  한국 종목: {', '.join(KOREAN_STOCKS)}")
    print(f"  미국 종목: {', '.join(US_STOCKS)}")
    print(f"  DART 감시: {len(TARGET_REPORTS)}개 공시 유형")
    print("=" * 40)

    # 시작 즉시 1회 실행
    check_and_send_news()
    check_dart()

    # 10분마다 뉴스 + DART 공시 확인
    schedule.every(10).minutes.do(check_and_send_news)
    schedule.every(10).minutes.do(check_dart)

    # 매주 토요일 오전 10:00 CB 월별 요약 전송
    schedule.every().saturday.at("10:00").do(send_cb_monthly_summary)

    while True:
        schedule.run_pending()
        time.sleep(60)
