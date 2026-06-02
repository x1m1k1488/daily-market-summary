#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ежедневная утренняя рыночная сводка -> Telegram.

Собирает:
  - дату
  - погоду (Одесса, Open-Meteo)
  - курсы валют (официальный API НБУ): USD/UAH, EUR/UAH
  - крипту (CoinGecko): BTC, ETH, USDT
  - форекс EUR/USD (Frankfurter / ECB)
  - события дня, способные двинуть рынок (бесплатный календарь ForexFactory)

Формирует "среднюю" сводку с живым анализом и отправляет в Telegram-группу.

Встроенный форматтер работает полностью бесплатно, без внешних ключей.
Если задан ANTHROPIC_API_KEY — текст сводки пишет Claude (необязательно, платно).

Переменные окружения (секреты GitHub Actions):
  TELEGRAM_BOT_TOKEN   (обязательно)
  TELEGRAM_CHAT_ID     (обязательно, для групп — отрицательное число)
  ANTHROPIC_API_KEY    (опционально, платно)
  CLAUDE_MODEL         (опционально, по умолчанию claude-sonnet-4-6)
"""

import os
import sys
import json
import html
import datetime as dt
from urllib import request, parse
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Kyiv")          # Одесса = Киевское время
SEND_HOUR = 8                          # слать в 08:00 локального времени
ODESSA_LAT, ODESSA_LON = 46.4825, 30.7233

RU_MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]
RU_WEEKDAYS = ["понедельник", "вторник", "среда", "четверг",
               "пятница", "суббота", "воскресенье"]

WMO = {
    0: "ясно", 1: "преим. ясно", 2: "переменная облачность", 3: "пасмурно",
    45: "туман", 48: "изморозь", 51: "лёгкая морось", 53: "морось",
    55: "сильная морось", 56: "ледяная морось", 57: "ледяная морось",
    61: "небольшой дождь", 63: "дождь", 65: "сильный дождь",
    66: "ледяной дождь", 67: "ледяной дождь", 71: "небольшой снег",
    73: "снег", 75: "сильный снег", 77: "снежная крупа",
    80: "кратковременный дождь", 81: "ливень", 82: "сильный ливень",
    85: "снегопад", 86: "сильный снегопад", 95: "гроза",
    96: "гроза с градом", 99: "сильная гроза с градом",
}

FLAGS = {"USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵",
         "CNY": "🇨🇳", "CHF": "🇨🇭", "CAD": "🇨🇦", "AUD": "🇦🇺",
         "NZD": "🇳🇿", "UAH": "🇺🇦", "ALL": "🌐"}


def http_get(url, headers=None, timeout=25):
    req = request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0 (daily-summary-bot)"})
    with request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def get_json(url, headers=None, timeout=25):
    return json.loads(http_get(url, headers=headers, timeout=timeout))


# ---------- источники данных ----------

def fetch_weather():
    try:
        url = ("https://api.open-meteo.com/v1/forecast"
               f"?latitude={ODESSA_LAT}&longitude={ODESSA_LON}"
               "&daily=temperature_2m_max,temperature_2m_min,"
               "precipitation_probability_max,weathercode,wind_speed_10m_max"
               "&timezone=Europe%2FKyiv&forecast_days=1")
        d = get_json(url)["daily"]
        code = int(d["weathercode"][0])
        tmax = round(d["temperature_2m_max"][0])
        tmin = round(d["temperature_2m_min"][0])
        pp = d["precipitation_probability_max"][0]
        wind = round(d["wind_speed_10m_max"][0])
        desc = WMO.get(code, "переменная облачность")
        rain = f", вероятность осадков {pp}%" if pp and pp >= 30 else ""
        return f"{desc}, {tmin}…{tmax} °C{rain}. Ветер до {wind} км/ч."
    except Exception as e:
        return f"нет данных ({e})"


def _nbu_for_date(date):
    ds = date.strftime("%Y%m%d")
    url = f"https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?date={ds}&json"
    data = get_json(url)
    return {row["cc"]: row["rate"] for row in data}


def fetch_nbu():
    try:
        today = dt.datetime.now(TZ).date()
        cur = _nbu_for_date(today)
        prev = {}
        for back in range(1, 6):
            try:
                prev = _nbu_for_date(today - dt.timedelta(days=back))
                if prev:
                    break
            except Exception:
                continue
        out = {}
        for cc in ("USD", "EUR"):
            if cc in cur:
                r = cur[cc]
                delta = ""
                if cc in prev:
                    d = r - prev[cc]
                    sign = "+" if d >= 0 else "−"
                    delta = f" ({sign}{abs(d):.2f})"
                out[cc] = f"{r:.2f}{delta}".replace(".", ",")
        return out
    except Exception as e:
        return {"error": str(e)}


def fetch_crypto():
    try:
        url = ("https://api.coingecko.com/api/v3/simple/price"
               "?ids=bitcoin,ethereum,tether&vs_currencies=usd"
               "&include_24hr_change=true")
        d = get_json(url)
        out = {}
        names = {"bitcoin": "BTC", "ethereum": "ETH", "tether": "USDT"}
        for k, label in names.items():
            if k in d:
                p = d[k]["usd"]
                ch = d[k].get("usd_24h_change", 0.0)
                sign = "+" if ch >= 0 else "−"
                if p >= 100:
                    ps = f"${p:,.0f}".replace(",", " ")
                else:
                    ps = f"${p:,.2f}"
                out[label] = {"text": f"{ps} ({sign}{abs(ch):.1f}%)", "chg": ch}
        return out
    except Exception as e:
        return {"error": str(e)}


def fetch_eurusd():
    try:
        latest = get_json("https://api.frankfurter.app/latest?from=EUR&to=USD")
        rate = latest["rates"]["USD"]
        date = latest["date"]
        prev_day = (dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()
        delta = ""
        try:
            prev = get_json(f"https://api.frankfurter.app/{prev_day}?from=EUR&to=USD")
            pr = prev["rates"]["USD"]
            d = rate - pr
            pct = d / pr * 100
            sign = "+" if d >= 0 else "−"
            delta = f" ({sign}{abs(pct):.2f}%)"
        except Exception:
            pass
        return f"{rate:.4f}{delta}".replace(".", ",")
    except Exception as e:
        return f"нет данных ({e})"


def fetch_events(limit=8):
    """Календарь ForexFactory (бесплатный зеркальный JSON). Только сегодня, High/Medium."""
    try:
        data = get_json("https://nfs.faireconomy.media/ff_calendar_thisweek.json")
        today = dt.datetime.now(TZ).date()
        events = []
        for e in data:
            impact = (e.get("impact") or "").lower()
            if impact not in ("high", "medium"):
                continue
            try:
                when = dt.datetime.fromisoformat(e["date"]).astimezone(TZ)
            except Exception:
                continue
            if when.date() != today:
                continue
            events.append({
                "time": when.strftime("%H:%M"),
                "country": e.get("country", ""),
                "title": e.get("title", ""),
                "impact": impact,
                "forecast": e.get("forecast", ""),
                "previous": e.get("previous", ""),
            })
        events.sort(key=lambda x: (0 if x["impact"] == "high" else 1, x["time"]))
        return events[:limit]
    except Exception as e:
        return [{"error": str(e)}]


# ---------- интерпретация (живой анализ, бесплатно) ----------

def _crypto_mood(chg):
    if chg is None:
        return ""
    if chg >= 3:
        return "уверенный рост"
    if chg >= 1:
        return "умеренный плюс"
    if chg > -1:
        return "почти без изменений"
    if chg > -3:
        return "лёгкое снижение"
    return "заметная распродажа"


EVENT_RULES = [
    (("cpi", "inflation", "price index", "ppi"),
     "инфляция — влияет на ожидания по ставкам ЦБ"),
    (("non-farm", "nonfarm", "payroll", "nfp", "employment", "unemployment",
      "jobless", "claims"),
     "рынок труда — сильные данные обычно укрепляют доллар"),
    (("pmi", "ism"), "деловая активность, опережающий индикатор экономики"),
    (("gdp",), "темпы роста экономики"),
    (("interest rate", "rate decision", "rate statement", "fomc", "fed funds",
      "ecb", "boe", "monetary policy", "rate"),
     "решение/риторика по ставке — обычно высокая волатильность"),
    (("retail sales",), "потребительский спрос"),
    (("trade balance", "current account"), "внешняя торговля"),
    (("confidence", "sentiment"), "настроения в экономике"),
    (("speaks", "speech", "testimony", "press conference"),
     "риторика чиновников — возможны резкие движения"),
]


def _interpret_event(title, impact):
    t = (title or "").lower()
    meaning = "макростатистика"
    for keys, desc in EVENT_RULES:
        if any(k in t for k in keys):
            meaning = desc
            break
    vol = "сильное движение возможно" if impact == "high" else "локальная реакция"
    return meaning, vol


# ---------- форматирование ----------

def build_message(data):
    now = dt.datetime.now(TZ)
    wd = RU_WEEKDAYS[now.weekday()]
    date_str = f"{wd}, {now.day} {RU_MONTHS[now.month]} {now.year}"

    L = []
    L.append(f"<b>📅 Утренняя сводка — {date_str}</b>")
    L.append("")
    L.append(f"<b>Погода (Одесса):</b> {data['weather']}")
    L.append("")

    nbu = data["nbu"]
    L.append("<b>Курс валют (НБУ):</b>")
    if "error" in nbu:
        L.append(f"нет данных ({nbu['error']})")
    else:
        if "USD" in nbu:
            L.append(f"• USD/UAH — {nbu['USD']}")
        if "EUR" in nbu:
            L.append(f"• EUR/UAH — {nbu['EUR']}")
    L.append("")

    cr = data["crypto"]
    L.append("<b>Крипторынок:</b>")
    if "error" in cr:
        L.append(f"нет данных ({cr['error']})")
    else:
        for label in ("BTC", "ETH", "USDT"):
            if label in cr:
                item = cr[label]
                if isinstance(item, dict):
                    mood = _crypto_mood(item.get("chg"))
                    note = f" — {mood}" if mood and label != "USDT" else ""
                    L.append(f"• {label} — {item['text']}{note}")
                else:
                    L.append(f"• {label} — {item}")
    L.append("")

    eurusd = data["eurusd"]
    fx_note = ""
    if "−" in eurusd:
        fx_note = " — евро слабеет к доллару"
    elif "+" in eurusd:
        fx_note = " — евро укрепляется к доллару"
    L.append(f"<b>Форекс:</b> EUR/USD — {eurusd}{fx_note}")
    L.append("")

    ev = data["events"]
    L.append("<b>Главные события дня (могут двинуть рынок):</b>")
    calendar_ok = not (ev and "error" in ev[0])
    if ev and "error" in ev[0]:
        L.append(f"календарь недоступен ({ev[0]['error']})")
    elif not ev:
        L.append("значимых событий высокой важности не запланировано.")
    else:
        for e in ev:
            flag = FLAGS.get(e["country"], "•")
            star = "‼️" if e["impact"] == "high" else "▫️"
            extra = []
            if e.get("forecast"):
                extra.append(f"прогноз {e['forecast']}")
            if e.get("previous"):
                extra.append(f"пред. {e['previous']}")
            tail = f" — {', '.join(extra)}" if extra else ""
            title = html.escape(e["title"])
            meaning, vol = _interpret_event(e["title"], e["impact"])
            L.append(f"{star} {e['time']} {flag} {title}{tail}")
            L.append(f"   ↳ <i>{meaning}; {vol}.</i>")
    L.append("")

    if calendar_ok:
        highs = sum(1 for e in ev if e.get("impact") == "high")
        if highs >= 3:
            verdict = ("ожидается высокая волатильность — день насыщен важными "
                       "релизами, возможны резкие движения по доллару, евро и крипте.")
        elif highs >= 1:
            verdict = ("волатильность умеренная — есть отдельные значимые события, "
                       "следите за реакцией на их выход.")
        else:
            verdict = ("день относительно спокойный по календарю — резких движений "
                       "на макроданных не ожидается.")
        L.append(f"<b>Вывод по волатильности:</b> {verdict}")
        L.append("")

    L.append('<b>Источники:</b> '
             '<a href="https://www.investing.com/economic-calendar">Investing.com</a> · '
             '<a href="https://ru.tradingview.com/">TradingView</a> · '
             '<a href="https://www.forexfactory.com/calendar">ForexFactory</a> · '
             '<a href="https://bank.gov.ua/ua/markets/exchangerates">НБУ</a>')

    return "\n".join(L)


def build_message_with_claude(data):
    """Опционально: пишет сводку через Claude, если задан ANTHROPIC_API_KEY."""
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        return None
    try:
        now = dt.datetime.now(TZ)
        model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6").strip()
        payload = {
            "model": model,
            "max_tokens": 1600,
            "messages": [{
                "role": "user",
                "content": (
                    "Ты — опытный рыночный аналитик, ведущий утренний трейдерский брифинг. "
                    "Составь живую, но деловую утреннюю сводку на русском для Telegram "
                    "(HTML-теги <b> и <a href>, без markdown). Объём — средний.\n\n"
                    "Стиль:\n"
                    "- Не пересказывай цифры сухо — добавляй интерпретацию. По крипте и форексу "
                    "поясняй, что говорит динамика (настроение, давление продавцов/покупателей, "
                    "ключевые уровни в общих чертах).\n"
                    "- По каждому событию дня объясни простыми словами, ЧТО оно значит и КАК может "
                    "двинуть рынок (выше/ниже прогноза → реакция доллара, евро, крипты, золота) и "
                    "насколько вырастет волатильность.\n"
                    "- В конце — краткий вывод: какой ожидается день по волатильности и за чем "
                    "следить в первую очередь.\n"
                    "- НЕ выдумывай числа: только данные ниже; если данных нет — так и напиши. "
                    "Не давай прямых торговых советов ('покупай/продавай').\n\n"
                    f"Дата: {now.strftime('%A, %d.%m.%Y')}.\n\n"
                    f"Данные (JSON):\n{json.dumps(data, ensure_ascii=False, indent=2)}\n\n"
                    "Структура: заголовок с датой и эмодзи; Погода (Одесса); Курс валют (НБУ); "
                    "Крипторынок; Форекс EUR/USD; Главные события дня (с временем и ссылками); "
                    "короткий вывод по волатильности; строка Источники со ссылками на "
                    "Investing.com, TradingView, ForexFactory, НБУ."
                )
            }],
        }
        req = request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read().decode("utf-8"))
        return "".join(b.get("text", "") for b in resp.get("content", [])).strip() or None
    except Exception as e:
        print(f"[warn] Claude недоступен, использую встроенный форматтер: {e}", file=sys.stderr)
        return None


# ---------- отправка ----------

def send_telegram(text):
    # .strip() убирает случайные пробелы/переносы строки, попавшие в секрет
    token = os.environ["TELEGRAM_BOT_TOKEN"].strip()
    chat_id = os.environ["TELEGRAM_CHAT_ID"].strip()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = request.Request(url, data=payload, method="POST")
    with request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read().decode("utf-8"))
    if not resp.get("ok"):
        raise RuntimeError(f"Telegram error: {resp}")
    return resp


def main():
    # Защита от перехода на зимнее/летнее время: workflow запускается в 05:00 и
    # 06:00 UTC, отправляем только если в Киеве сейчас 08:xx.
    if os.environ.get("ENFORCE_SEND_HOUR", "1") == "1":
        cur_hour = dt.datetime.now(TZ).hour
        if cur_hour != SEND_HOUR and "--force" not in sys.argv:
            print(f"[skip] Сейчас {cur_hour}:00 по Киеву, отправка только в {SEND_HOUR}:00.")
            return

    data = {
        "weather": fetch_weather(),
        "nbu": fetch_nbu(),
        "crypto": fetch_crypto(),
        "eurusd": fetch_eurusd(),
        "events": fetch_events(),
    }

    text = build_message_with_claude(data) or build_message(data)

    if "--dry-run" in sys.argv:
        print(text)
        return

    send_telegram(text)
    print("[ok] Сводка отправлена в Telegram.")


if __name__ == "__main__":
    main()
