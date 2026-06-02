# Ежедневная рыночная сводка в Telegram

Бесплатный бот, который каждое утро в **08:00 по Киеву** присылает в вашу Telegram-группу:
дату, погоду (Одесса), курсы валют НБУ (USD/UAH, EUR/UAH), крипту (BTC, ETH, USDT),
EUR/USD и главные события дня, способные двинуть рынок (с источниками).

Работает в облаке через **GitHub Actions** — компьютер включать не нужно.

---

## Что нужно (один раз, ~10 минут)

1. **Аккаунт GitHub** — бесплатный, [github.com](https://github.com).
2. **Бот Telegram** — у вас уже есть токен от @BotFather.
3. **Chat ID группы** — добавьте бота в группу, затем добавьте туда же
   **@getmyid_bot** (или @username_to_id_bot) — он пришлёт `Chat ID`
   (у групп он отрицательный, например `-1001234567890`). Потом этого помощника можно удалить.
   ⚠️ Убедитесь, что ваш бот добавлен в группу и имеет право писать сообщения.

---

## Установка

### 1. Создайте репозиторий
- На GitHub: **New repository** → имя любое (например `daily-market-summary`) →
  можно **Private** → Create.
- Загрузите в него файлы из этой папки (кнопка **Add file → Upload files**,
  перетащите всё, включая папку `.github`). Либо через git:
  ```bash
  git init
  git add .
  git commit -m "daily market summary"
  git branch -M main
  git remote add origin https://github.com/ВАШ_ЛОГИН/daily-market-summary.git
  git push -u origin main
  ```

### 2. Добавьте секреты
Репозиторий → **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**. Создайте:

| Имя | Значение |
|-----|----------|
| `TELEGRAM_BOT_TOKEN` | токен бота от @BotFather |
| `TELEGRAM_CHAT_ID` | chat id группы (отрицательное число) |
| `ANTHROPIC_API_KEY` | *(необязательно)* ключ Anthropic — тогда текст сводки пишет Claude, более «живой» анализ |

### 3. Включите Actions
Вкладка **Actions** → если попросит — нажмите *«I understand my workflows, enable them»*.

### 4. Тестовый запуск (прямо сейчас)
**Actions** → слева **Daily market summary to Telegram** → **Run workflow** →
оставьте `force = true` → **Run workflow**.
Через ~30 секунд сводка должна прийти в группу. Если не пришла — см. «Проблемы» ниже.

Дальше всё работает само: каждый день в 08:00 по Киеву.

---

## Настройки

- **Время отправки:** меняется в `send_summary.py` → `SEND_HOUR = 8`.
  Часовой пояс — `TZ = ZoneInfo("Europe/Kyiv")`. Cron в `.github/workflows/daily-summary.yml`
  настроен на 05:00 и 06:00 UTC (покрывает летнее и зимнее время); скрипт сам шлёт только в 8:00 по Киеву.
- **Город погоды:** координаты `ODESSA_LAT/ODESSA_LON` в скрипте.
- **Объём/формат:** функция `build_message()` — порядок блоков, активы, эмодзи.

---

## Источники данных (всё бесплатно, без ключей)

- Погода — Open-Meteo
- Курсы — официальный API НБУ (bank.gov.ua)
- Крипта — CoinGecko
- EUR/USD — Frankfurter (данные ЕЦБ)
- События дня — бесплатный календарь ForexFactory (nfs.faireconomy.media)

---

## Проблемы

- **Не пришло сообщение при тесте** → откройте запуск в **Actions** и посмотрите лог шага
  *Run summary*. Частые причины: бот не добавлен в группу; неверный `TELEGRAM_CHAT_ID`
  (должен быть с минусом для групп); у бота нет права писать.
- **`chat not found`** → бот не состоит в группе или неверный chat id.
- **`Forbidden: bot was blocked` / `not enough rights`** → дайте боту право отправлять сообщения в группе.
- **Расписание иногда опаздывает на 5–15 минут** — это нормально для бесплатного GitHub Actions.

---

## Безопасность

Токен и ключи хранятся **только в Secrets** GitHub и не видны в коде.
Никогда не вставляйте токен прямо в файлы. Если токен утёк — отзовите его в @BotFather (`/revoke`)
и обновите секрет `TELEGRAM_BOT_TOKEN`.
