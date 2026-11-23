"""Серверная часть админ-панели сайта.

Код доступа проверяется ТОЛЬКО здесь (переменная окружения ADMIN_CODE), а не в браузере.
После входа выдаётся временный токен; все остальные запросы требуют заголовок Authorization: Bearer <токен>.
"""
import asyncio
import hmac
import html
import json
import logging
import secrets
import time

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiohttp import web

import config
import db
from i18n import tr

log = logging.getLogger("tele-license.admin")

# ---------- сессии и защита от перебора ----------
_tokens: dict[str, float] = {}
_fails_ip: dict[str, list[float]] = {}
_fails_all: list[float] = []
WINDOW_IP, MAX_IP = 15 * 60, 5      # не больше 5 неверных кодов с одного адреса за 15 минут
WINDOW_ALL, MAX_ALL = 60 * 60, 40   # и не больше 40 неверных кодов в час в сумме


def _client_ip(request: web.Request) -> str:
    xff = request.headers.get("X-Forwarded-For", "")
    return (xff.split(",")[0].strip() if xff else request.remote) or "?"


def _prune(now: float) -> None:
    for ip in list(_fails_ip):
        _fails_ip[ip] = [t for t in _fails_ip[ip] if now - t < WINDOW_IP]
        if not _fails_ip[ip]:
            del _fails_ip[ip]
    _fails_all[:] = [t for t in _fails_all if now - t < WINDOW_ALL]
    for tok in [t for t, exp in _tokens.items() if exp < now]:
        del _tokens[tok]


def _json(data, status: int = 200) -> web.Response:
    return web.json_response(data, status=status)


def _err(message: str, status: int = 400) -> web.Response:
    return _json({"error": message}, status)


async def _body(request: web.Request) -> dict:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def lic(n: int) -> str:
    return f"TL-{n:05d}"


async def login(request: web.Request) -> web.Response:
    if not config.ADMIN_CODE:
        return _err("Админ-панель не настроена: не задана переменная ADMIN_CODE", 503)
    now = time.time()
    _prune(now)
    ip = _client_ip(request)
    if len(_fails_ip.get(ip, [])) >= MAX_IP or len(_fails_all) >= MAX_ALL:
        return _err("Слишком много попыток. Повторите позже.", 429)
    code = str((await _body(request)).get("code", ""))
    if not hmac.compare_digest(code.encode(), config.ADMIN_CODE.encode()):
        _fails_ip.setdefault(ip, []).append(now)
        _fails_all.append(now)
        log.warning("Неверный код админ-панели с %s", ip)
        await asyncio.sleep(1)  # замедляем перебор
        return _err("Неверный код", 401)
    token = secrets.token_urlsafe(32)
    _tokens[token] = now + config.ADMIN_SESSION_HOURS * 3600
    log.info("Вход в админ-панель с %s", ip)
    return _json({"token": token, "ttl": config.ADMIN_SESSION_HOURS * 3600})


def require(handler):
    async def wrapper(request: web.Request) -> web.Response:
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        exp = _tokens.get(token)
        if not exp or exp < time.time():
            return _err("Требуется вход", 401)
        request["token"] = token
        return await handler(request)
    return wrapper


async def logout(request: web.Request) -> web.Response:
    _tokens.pop(request["token"], None)
    return _json({"ok": True})


# ---------- пользователи ----------
async def user_info(request: web.Request) -> web.Response:
    uid = _int(request.query.get("id"))
    if not uid:
        return _err("Укажите числовой Telegram ID")
    d = await db.admin_user_info(uid)
    u = d["user"]
    return _json({
        "id": uid, "known": u is not None, "lang": u["lang"] if u else None, "banned": bool(u and u["banned"]),
        "spent": d["spent"], "apps": d["apps"],
        "resources": [{
            "num": r["id"], "id": lic(r["id"]), "title": r["title"], "link": f"https://t.me/{r['username']}",
            "kind": r["kind"], "active": r["active"], "special": r["id"] in config.AUCTION_LOTS,
        } for r in d["resources"]],
        "numbers": [{"id": lic(n["number"]), "price": n["final_amount"], "assigned": n["assigned"]} for n in d["numbers"]],
        "leading": [{"id": lic(n["number"]), "price": n["top_amount"]} for n in d["leading"]],
    })


async def send_message(request: web.Request) -> web.Response:
    data = await _body(request)
    uid, text = _int(data.get("user_id")), str(data.get("text") or "").strip()
    if not uid or not text:
        return _err("Нужны ID и текст сообщения")
    if len(text) > 4096:
        return _err("Сообщение длиннее 4096 символов")
    try:
        await request.app["bot"].send_message(uid, text)
    except TelegramForbiddenError:
        return _err("Пользователь заблокировал бота")
    except TelegramAPIError as e:
        return _err(f"Не отправлено: {e.message}")
    return _json({"ok": True})


async def ban(request: web.Request) -> web.Response:
    uid = _int((await _body(request)).get("user_id"))
    if not uid:
        return _err("Нужен ID")
    res = await db.ban_user(uid)
    return _json({"ok": True, "released": [lic(n) for n in res["released"]]})


async def unban(request: web.Request) -> web.Response:
    uid = _int((await _body(request)).get("user_id"))
    if not uid:
        return _err("Нужен ID")
    return _json({"ok": True, "was_banned": await db.unban_user(uid)})


_RENUMBER_ERRORS = {
    "not_found": "Ресурс с таким номером не найден",
    "same": "Новый номер совпадает с текущим",
    "bad_number": "Номер должен быть от 1 до 999999",
    "taken": "Этот номер уже занят другим ресурсом",
    "reserved": "Этот номер зарезервирован за аукционом",
    "used_before": "Этот номер раньше использовался и закреплён за старой ссылкой",
}


async def renumber(request: web.Request) -> web.Response:
    data = await _body(request)
    old, new = _int(data.get("number")), _int(data.get("new_number"))
    if not old or not new:
        return _err("Нужны текущий и новый номер")
    res = await db.renumber_resource(old, new)
    if res["status"] != "ok":
        return _err(_RENUMBER_ERRORS.get(res["status"], "Не удалось сменить номер"))
    bot: Bot = request.app["bot"]
    lang = await db.get_lang(res["user_id"]) or "ru"
    link = f"https://t.me/{(await bot.me()).username}?start=v_{new}"
    try:
        await bot.send_message(res["user_id"], tr(lang, "n_renumber", title=html.escape(res["title"]),
                                                   old=lic(old), new=lic(new), link=link))
    except TelegramAPIError as e:
        log.warning("Не удалось уведомить владельца о смене номера: %s", e)
    return _json({"ok": True, "id": lic(new)})


# ---------- рассылка ----------
ACTIONS = {"apply": "menu:apply", "auction": "au:list", "numbers": "mn:list", "rules": "menu:rules", "menu": "menu:home"}
MAX_MEDIA = 50 * 1024 * 1024
JOBS: dict[str, dict] = {}


def build_markup(buttons) -> InlineKeyboardMarkup | None:
    rows = []
    for b in (buttons or [])[:10]:
        text = str(b.get("text") or "").strip()[:64]
        if not text:
            continue
        url = str(b.get("url") or "").strip()
        if url:
            if not url.startswith(("https://", "http://", "tg://")):
                raise ValueError(f"Неверная ссылка у кнопки «{text}»")
            rows.append([InlineKeyboardButton(text=text, url=url)])
        elif b.get("action") in ACTIONS:
            rows.append([InlineKeyboardButton(text=text, callback_data=ACTIONS[b["action"]])])
        else:
            raise ValueError(f"У кнопки «{text}» нет ссылки или действия")
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def _send(bot: Bot, uid: int, text: str, markup, kind: str | None, media):
    """Отправляет одно сообщение. Возвращает file_id загруженного медиа (для повторного использования)."""
    if not kind:
        await bot.send_message(uid, text, reply_markup=markup)
        return None
    caption = text if text and len(text) <= 1000 else None
    media_markup = markup if (caption or not text) else None
    if kind == "photo":
        msg = await bot.send_photo(uid, media, caption=caption, reply_markup=media_markup)
        file_id = msg.photo[-1].file_id
    else:
        msg = await bot.send_video(uid, media, caption=caption, reply_markup=media_markup, supports_streaming=True)
        file_id = msg.video.file_id
    if text and not caption:  # слишком длинный текст — отдельным сообщением
        await bot.send_message(uid, text, reply_markup=markup)
    return file_id


_FATAL_MARKERS = ("parse entities", "can't parse", "entity", "emoji", "wrong file", "document_invalid", "button", "too long")


async def _run_job(bot: Bot, job: dict, ids: list[int], text: str, markup, kind, media, filename) -> None:
    ref = BufferedInputFile(media, filename=filename) if media else None
    job.update(state="running", total=len(ids))
    for uid in ids:
        for attempt in range(2):
            try:
                file_id = await _send(bot, uid, text, markup, kind, ref)
                if file_id:
                    ref = file_id  # дальше шлём по file_id, без повторной загрузки
                job["sent"] += 1
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                continue
            except TelegramForbiddenError:
                job["blocked"] += 1
            except TelegramBadRequest as e:
                job["failed"] += 1
                if job["sent"] == 0 and any(m in str(e).lower() for m in _FATAL_MARKERS):
                    job.update(state="aborted", error=f"Рассылка остановлена: {e.message}")
                    return
            except TelegramAPIError:
                job["failed"] += 1
            break
        await asyncio.sleep(0.05)  # ~20 сообщений в секунду, в пределах лимитов Telegram
    job["state"] = "done"


async def broadcast(request: web.Request) -> web.Response:
    bot: Bot = request.app["bot"]
    payload, media, ctype, filename = None, None, "", "file"
    try:
        reader = await request.multipart()
        async for part in reader:
            if part.name == "payload":
                payload = json.loads(await part.text())
            elif part.name == "media" and part.filename:
                filename, ctype = part.filename, part.headers.get("Content-Type", "")
                buf = bytearray()
                while True:
                    chunk = await part.read_chunk(1 << 20)
                    if not chunk:
                        break
                    buf += chunk
                    if len(buf) > MAX_MEDIA:
                        return _err("Файл больше 50 МБ", 413)
                media = bytes(buf)
    except Exception:
        return _err("Не удалось прочитать форму")
    if not isinstance(payload, dict):
        return _err("Пустой запрос")

    text = str(payload.get("text") or "").strip()
    if not text and not media:
        return _err("Нужен текст или медиафайл")
    if len(text) > 4096:
        return _err("Текст длиннее 4096 символов")
    kind = None
    if media:
        kind = "photo" if ctype.startswith("image/") else "video" if ctype.startswith("video/") else None
        if not kind:
            return _err("Поддерживаются только фото и видео")
    try:
        markup = build_markup(payload.get("buttons"))
    except ValueError as e:
        return _err(str(e))

    audience = payload.get("audience", "all")
    if audience == "test":
        tid = _int(payload.get("test_id"))
        if not tid:
            return _err("Укажите ID для теста")
        try:
            await _send(bot, tid, text, markup, kind, BufferedInputFile(media, filename=filename) if media else None)
        except TelegramAPIError as e:
            return _err(f"Не отправлено: {e.message}")
        return _json({"ok": True, "test": True})

    if any(j["state"] == "running" for j in JOBS.values()):
        return _err("Предыдущая рассылка ещё идёт", 409)
    ids = await db.broadcast_audience(audience if audience in ("ru", "en") else None)
    if not ids:
        return _err("В этой аудитории нет пользователей")
    job_id = secrets.token_hex(6)
    job = {"state": "running", "total": len(ids), "sent": 0, "failed": 0, "blocked": 0, "error": None}
    JOBS[job_id] = job
    job["task"] = asyncio.create_task(_run_job(bot, job, ids, text, markup, kind, media, filename))
    for old in list(JOBS)[:-5]:  # храним последние 5 рассылок
        JOBS.pop(old, None)
    return _json({"job": job_id, "total": len(ids)})


async def broadcast_status(request: web.Request) -> web.Response:
    job = JOBS.get(request.match_info["job"])
    if not job:
        return _err("Рассылка не найдена", 404)
    return _json({k: v for k, v in job.items() if k != "task"})


def setup(app: web.Application, bot: Bot) -> None:
    app["bot"] = bot
    r = app.router
    r.add_post("/api/admin/login", login)
    r.add_post("/api/admin/logout", require(logout))
    r.add_get("/api/admin/user", require(user_info))
    r.add_post("/api/admin/message", require(send_message))
    r.add_post("/api/admin/ban", require(ban))
    r.add_post("/api/admin/unban", require(unban))
    r.add_post("/api/admin/renumber", require(renumber))
    r.add_post("/api/admin/broadcast", require(broadcast))
    r.add_get("/api/admin/broadcast/{job}", require(broadcast_status))
