import os


def _int(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name, "").strip()
    return int(value) if value else default


BOT_TOKEN = os.environ["BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
MOD_CHAT_ID = int(os.environ["MOD_CHAT_ID"])
TOPIC_APPLICATIONS = _int("TOPIC_APPLICATIONS", 1)
TOPIC_COMPLAINTS = int(os.environ["TOPIC_COMPLAINTS"])
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x}

SITE_URL = os.getenv("SITE_URL", "https://teleprojects.vercel.app").rstrip("/")
NEWS_CHANNEL = "https://t.me/TeleProjects_tg"
PORT = int(os.getenv("PORT", "10000"))

MIN_MEMBERS = 5000      # каналы и чаты
MIN_BOT_USERS = 10000   # боты

# ---------- Аукцион номеров лицензий (оплата в Telegram Stars) ----------
AUCTION_DAYS = 10     # длительность аукциона после первой ставки
BID_STEP = 15         # минимальный шаг перебива, звёзд
MAX_BID = 10000       # максимальная ставка за один счёт, звёзд
AUCTION_LOTS = {      # номер лицензии -> стартовая цена в звёздах
    67: 180, 42: 100, 52: 100, 1488: 200, 228: 100, 777: 400, 666: 666,
    11111: 500, 22222: 500, 33333: 500, 44444: 500, 55555: 500,
    66666: 700, 77777: 900, 88888: 800, 99999: 1000,
}
