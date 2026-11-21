import asyncio
import html
import logging
import re

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiohttp import web

import config
import db
from i18n import LANG_NAMES, PURPOSE_KEYS, disp_countries, disp_languages, disp_purpose, tr

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tele-license")

KIND_KEYS = ("channel", "chat", "bot")


# ---------- утилиты ----------
def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def lic(n: int) -> str:
    return f"TL-{n:05d}"


def fdate(dt) -> str:
    return dt.strftime("%d.%m.%Y")


def num(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def btn(text: str, cb: str | None = None, url: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb, url=url)


def kb(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def grid(buttons, cols=2):
    return [buttons[i:i + cols] for i in range(0, len(buttons), cols)]


def main_menu(lang: str) -> InlineKeyboardMarkup:
    return kb([
        [btn(tr(lang, "b_apply"), "menu:apply")],
        [btn(tr(lang, "b_my"), "menu:my"), btn(tr(lang, "b_rules"), "menu:rules")],
        [btn(tr(lang, "b_docs"), "menu:docs"), btn(tr(lang, "b_site"), url=config.SITE_URL)],
        [btn(tr(lang, "b_news"), url=config.NEWS_CHANNEL)],
        [btn(tr(lang, "b_lang"), "menu:lang")],
    ])


def back_home(lang: str) -> InlineKeyboardMarkup:
    return kb([[btn(tr(lang, "b_home"), "menu:home")]])


def cancel_kb(lang: str) -> InlineKeyboardMarkup:
    return kb([[btn(tr(lang, "b_cancel"), "cancel")]])


def lang_picker() -> InlineKeyboardMarkup:
    return kb([[btn("Русский", "lang:ru"), btn("English", "lang:en")]])


def full_name_tag(u) -> str:
    return u.full_name + (f" (@{u.username})" if u.username else "")


async def show(cb: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except TelegramAPIError:
        await cb.message.answer(text, reply_markup=markup)


async def is_mod(bot: Bot, user_id: int) -> bool:
    if user_id in config.ADMIN_IDS:
        return True
    try:
        m = await bot.get_chat_member(config.MOD_CHAT_ID, user_id)
        return m.status in ("creator", "administrator")
    except TelegramAPIError:
        return False


async def verify_url(bot: Bot, reg_id: int) -> str:
    return f"https://t.me/{(await bot.me()).username}?start=v_{reg_id}"


def site_url(reg_id: int) -> str:
    return f"{config.SITE_URL}/registry/{lic(reg_id)}"


# ---------- язык пользователя ----------
_lang_cache: dict[int, str] = {}


def guess_lang(code: str | None) -> str:
    return "ru" if (code or "").lower()[:2] in ("ru", "be", "kk") else "en"


async def stored_lang(user_id: int) -> str | None:
    if user_id in _lang_cache:
        return _lang_cache[user_id]
    lang = await db.get_lang(user_id)
    if lang:
        _lang_cache[user_id] = lang
    return lang


async def set_user_lang(user_id: int, lang: str) -> None:
    _lang_cache[user_id] = lang
    await db.set_lang(user_id, lang)


async def ulang(user_id: int) -> str:
    """Язык для уведомлений пользователю, который сейчас не в диалоге."""
    return await stored_lang(user_id) or "ru"


class LangMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        data["lang"] = (await stored_lang(user.id) or guess_lang(user.language_code)) if user else "ru"
        return await handler(event, data)


# ---------- проверка ресурса ----------
_LINK_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/([A-Za-z][A-Za-z0-9_]{3,31})/?$|^@([A-Za-z][A-Za-z0-9_]{3,31})$",
    re.I,
)


def parse_username(text: str):
    """Возвращает (username, ключ_ошибки)."""
    t = text.strip()
    if "+" in t or "joinchat" in t.lower():
        return None, "link_private"
    m = _LINK_RE.match(t)
    if not m:
        return None, "link_format"
    return m.group(1) or m.group(2), None


async def inspect_resource(bot: Bot, kind: str, username: str, user_id: int) -> dict:
    """Автоматические проверки через Bot API. error — ключ перевода. owner: True / False / None."""
    res = {"error": None, "username": username, "members": None, "owner": None}
    try:
        chat = await bot.get_chat(f"@{username}")
    except TelegramAPIError:
        if kind == "bot":
            return res  # у ботов проверка мягкая, дальше смотрит модератор
        res["error"] = "not_found"
        return res

    if chat.username:
        res["username"] = chat.username
    if kind == "channel" and chat.type != ChatType.CHANNEL:
        res["error"] = "not_channel"
    elif kind == "chat" and chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        res["error"] = "not_chat"
    elif kind == "bot" and chat.type != ChatType.PRIVATE:
        res["error"] = "not_bot"
    if res["error"] or kind == "bot":
        return res

    try:
        res["members"] = await bot.get_chat_member_count(chat.id)
    except TelegramAPIError:
        res["members"] = None
    try:
        admins = await bot.get_chat_administrators(chat.id)
        res["owner"] = user_id in {a.user.id for a in admins}
    except TelegramAPIError:
        res["owner"] = None
    return res


# ---------- карточки для модераторов (всегда на русском) ----------
def app_card(a) -> str:
    owner = ("подтверждено автоматически" if a["owner_status"] == "confirmed"
             else "⚠️ не подтверждено автоматически — уточните у заявителя")
    if a["kind"] == "bot":
        count_label = "Пользователей (со слов заявителя)"
        checks = "• бот работает и отвечает\n• в профиле указано соответствующее число пользователей"
    else:
        count_label = "Участников (по данным Telegram)"
        checks = "• ресурс существует более 1 месяца\n• опубликовано не менее 20 сообщений"
    return (
        f"<b>Заявка №{a['id']}</b>\n\n"
        f"<b>Тип:</b> {tr('ru', 'kind_' + a['kind'])}\n"
        f"<b>Название:</b> {esc(a['title'])}\n"
        f"<b>Ссылка:</b> https://t.me/{esc(a['username'])}\n"
        f"<b>Назначение:</b> {esc(disp_purpose(a['purpose'], 'ru'))}\n"
        f"<b>Страны:</b> {esc(disp_countries(a['countries'], 'ru'))}\n"
        f"<b>Языки:</b> {esc(disp_languages(a['languages'], 'ru'))}\n"
        f"<b>{count_label}:</b> {num(a['members']) if a['members'] is not None else 'не определено'}\n"
        f"<b>Администратор ресурса:</b> {owner}\n"
        f"<b>Заявитель:</b> <a href=\"tg://user?id={a['user_id']}\">{esc(a['user_tag'] or a['user_id'])}</a> · <code>{a['user_id']}</code>\n\n"
        f"<b>Проверьте вручную:</b>\n{checks}\n• отсутствие запрещённого контента и меток SCAM/FAKE"
    )


def complaint_card(c, reg) -> str:
    return (
        f"<b>Жалоба №{c['id']}</b>\n\n"
        f"<b>Ресурс:</b> {esc(reg['title'])}\n"
        f"<b>Ссылка:</b> https://t.me/{esc(reg['username'])}\n"
        f"<b>Лицензия:</b> {lic(reg['id'])}\n\n"
        f"<b>Причина жалобы:</b>\n{esc(c['reason'])}\n\n"
        f"<b>Автор жалобы:</b> <a href=\"tg://user?id={c['user_id']}\">{c['user_id']}</a>"
    )


def app_keyboard(app_id: int) -> InlineKeyboardMarkup:
    return kb([[btn("Принять", f"ma:{app_id}"), btn("Отклонить", f"mr:{app_id}")]])


def complaint_keyboard(cid: int) -> InlineKeyboardMarkup:
    return kb([[btn("Ресурс в порядке", f"cok:{cid}")], [btn("Ресурс не в порядке", f"cbad:{cid}")]])


async def notify(bot: Bot, user_id: int, text: str, markup=None) -> None:
    try:
        await bot.send_message(user_id, text, reply_markup=markup)
    except TelegramAPIError as e:
        log.warning("Не удалось уведомить %s: %s", user_id, e)


# =====================================================================
#                         ПОЛЬЗОВАТЕЛИ (личка)
# =====================================================================
private = Router()
private.message.filter(F.chat.type == ChatType.PRIVATE)
private.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)
private.message.middleware(LangMiddleware())
private.callback_query.middleware(LangMiddleware())


class Form(StatesGroup):
    kind = State()
    title = State()
    link = State()
    users = State()
    purpose = State()
    purpose_text = State()
    countries = State()
    countries_text = State()
    languages = State()
    confirm = State()


class ComplaintForm(StatesGroup):
    reason = State()


@private.message(CommandStart())
async def cmd_start(m: Message, command: CommandObject, state: FSMContext, lang: str):
    await state.clear()
    arg = command.args or ""
    if arg.startswith("v_") and arg[2:].isdigit():
        await show_verification(m, int(arg[2:]), lang)
        return
    if await stored_lang(m.from_user.id) is None:
        await m.answer(tr("ru", "pick_lang"), reply_markup=lang_picker())
        return
    await m.answer(tr(lang, "welcome"), reply_markup=main_menu(lang))


@private.message(Command("language"))
async def cmd_language(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(tr("ru", "pick_lang"), reply_markup=lang_picker())


@private.message(Command("cancel"))
async def cmd_cancel(m: Message, state: FSMContext, lang: str):
    await state.clear()
    await m.answer(tr(lang, "cancelled"), reply_markup=main_menu(lang))


@private.callback_query(F.data.startswith("lang:"))
async def cb_lang(cb: CallbackQuery, state: FSMContext):
    new = cb.data.split(":")[1]
    if new not in ("ru", "en"):
        return await cb.answer()
    await set_user_lang(cb.from_user.id, new)
    await state.clear()
    await show(cb, tr(new, "welcome"), main_menu(new))
    await cb.answer()


@private.callback_query(F.data == "cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext, lang: str):
    await state.clear()
    await show(cb, tr(lang, "welcome"), main_menu(lang))
    await cb.answer()


# ----- меню -----
@private.callback_query(F.data.startswith("menu:"))
async def cb_menu(cb: CallbackQuery, state: FSMContext, lang: str):
    await state.clear()
    section = cb.data.split(":")[1]
    if section == "home":
        await show(cb, tr(lang, "welcome"), main_menu(lang))
    elif section == "lang":
        await show(cb, tr("ru", "pick_lang"), lang_picker())
    elif section == "rules":
        await show(cb, tr(lang, "rules"), back_home(lang))
    elif section == "about":
        await show(cb, tr(lang, "about"), back_home(lang))
    elif section == "docs":
        await show(cb, tr(lang, "docs"), kb([
            [btn(tr(lang, "b_terms"), url=f"{config.SITE_URL}/terms")],
            [btn(tr(lang, "b_privacy"), url=f"{config.SITE_URL}/privacy")],
            [btn(tr(lang, "b_reg_rules"), url=f"{config.SITE_URL}/tele-license#rules")],
            [btn(tr(lang, "b_home"), "menu:home")],
        ]))
    elif section == "apply":
        await show(cb, tr(lang, "requirements") + "\n\n" + tr(lang, "apply_note"),
                   kb([[btn(tr(lang, "b_continue"), "apply:go")], [btn(tr(lang, "b_read_rules"), "menu:rules")],
                       [btn(tr(lang, "b_home"), "menu:home")]]))
    elif section == "my":
        await show_my(cb, lang)
    await cb.answer()


async def show_my(cb: CallbackQuery, lang: str):
    rows = await db.user_applications(cb.from_user.id)
    if not rows:
        await show(cb, tr(lang, "no_apps"), kb([[btn(tr(lang, "b_apply"), "menu:apply")], [btn(tr(lang, "b_home"), "menu:home")]]))
        return
    lines = [tr(lang, "my_header")]
    for r in rows:
        if r["status"] == "pending":
            st = tr(lang, "st_pending")
        elif r["status"] == "rejected":
            st = tr(lang, "st_rejected", reason=esc(r["reject_reason"]))
        elif r["reg_active"]:
            st = tr(lang, "st_approved", lic=lic(r["reg_id"]))
        else:
            st = tr(lang, "st_revoked", lic=lic(r["reg_id"]))
        lines.append(f"<b>#{r['id']}</b> · {esc(r['title'])}\n{st}\n")
    await show(cb, "\n".join(lines), back_home(lang))


# ----- подача заявки -----
@private.callback_query(F.data == "apply:go")
async def apply_go(cb: CallbackQuery, state: FSMContext, lang: str):
    await state.clear()
    await state.set_state(Form.kind)
    await show(cb, tr(lang, "kind_title"),
               kb([[btn(tr(lang, "kind_channel"), "k:channel")], [btn(tr(lang, "kind_chat"), "k:chat")],
                   [btn(tr(lang, "kind_bot"), "k:bot")], [btn(tr(lang, "b_cancel"), "cancel")]]))
    await cb.answer()


@private.callback_query(Form.kind, F.data.startswith("k:"))
async def f_kind(cb: CallbackQuery, state: FSMContext, lang: str):
    kind = cb.data.split(":")[1]
    if kind not in KIND_KEYS:
        return await cb.answer()
    await state.update_data(kind=kind)
    await state.set_state(Form.title)
    await show(cb, tr(lang, "step1"), cancel_kb(lang))
    await cb.answer()


@private.message(Form.title, F.text)
async def f_title(m: Message, state: FSMContext, lang: str):
    title = m.text.strip()
    if not 2 <= len(title) <= 64:
        return await m.answer(tr(lang, "title_len"))
    await state.update_data(title=title)
    await state.set_state(Form.link)
    await m.answer(tr(lang, "step2"), reply_markup=cancel_kb(lang))


@private.message(Form.link, F.text)
async def f_link(m: Message, state: FSMContext, bot: Bot, lang: str):
    data = await state.get_data()
    kind = data["kind"]
    username, err = parse_username(m.text)
    if err:
        return await m.answer(tr(lang, err))
    if kind == "bot" and not username.lower().endswith("bot"):
        return await m.answer(tr(lang, "bot_suffix"))
    if await db.username_taken(username):
        await state.clear()
        return await m.answer(tr(lang, "taken"), reply_markup=main_menu(lang))

    info = await inspect_resource(bot, kind, username, m.from_user.id)
    if info["error"]:
        return await m.answer(tr(lang, info["error"]))
    username = info["username"]

    if kind != "bot":
        if info["owner"] is False:
            await state.clear()
            return await m.answer(tr(lang, "not_admin"), reply_markup=main_menu(lang))
        if info["members"] is not None and info["members"] < config.MIN_MEMBERS:
            await state.clear()
            return await m.answer(tr(lang, "members_low", n=num(info["members"]), min=num(config.MIN_MEMBERS)),
                                  reply_markup=main_menu(lang))
    await state.update_data(
        username=username, members=info["members"],
        owner_status="confirmed" if info["owner"] else "unverified",
    )
    if kind == "bot":
        await state.set_state(Form.users)
        return await m.answer(tr(lang, "users_prompt"), reply_markup=cancel_kb(lang))
    await ask_purpose(m, state, lang)


@private.message(Form.users, F.text)
async def f_users(m: Message, state: FSMContext, lang: str):
    digits = re.sub(r"[\s,._]", "", m.text)
    if not digits.isdigit():
        return await m.answer(tr(lang, "users_nan"))
    users = int(digits)
    if users < config.MIN_BOT_USERS:
        await state.clear()
        return await m.answer(tr(lang, "users_low", n=num(users), min=num(config.MIN_BOT_USERS)),
                              reply_markup=main_menu(lang))
    await state.update_data(members=users)
    await ask_purpose(m, state, lang)


async def ask_purpose(m: Message, state: FSMContext, lang: str):
    await state.set_state(Form.purpose)
    rows = grid([btn(tr(lang, "p_" + k), f"p:{i}") for i, k in enumerate(PURPOSE_KEYS)])
    rows += [[btn(tr(lang, "b_other"), "p:other")], [btn(tr(lang, "b_cancel"), "cancel")]]
    await m.answer(tr(lang, "step3"), reply_markup=kb(rows))


@private.callback_query(Form.purpose, F.data.startswith("p:"))
async def f_purpose(cb: CallbackQuery, state: FSMContext, lang: str):
    val = cb.data.split(":")[1]
    if val == "other":
        await state.set_state(Form.purpose_text)
        await show(cb, tr(lang, "purpose_other"), cancel_kb(lang))
    else:
        await state.update_data(purpose=PURPOSE_KEYS[int(val)])
        await ask_countries(cb.message, state, lang, edit=True)
    await cb.answer()


@private.message(Form.purpose_text, F.text)
async def f_purpose_text(m: Message, state: FSMContext, lang: str):
    text = m.text.strip()
    if not 2 <= len(text) <= 40:
        return await m.answer(tr(lang, "purpose_len"))
    await state.update_data(purpose=text)
    await ask_countries(m, state, lang)


async def ask_countries(msg: Message, state: FSMContext, lang: str, edit: bool = False):
    await state.set_state(Form.countries)
    text = tr(lang, "step4")
    markup = kb([[btn(tr(lang, "b_all_countries"), "ct:all")], [btn(tr(lang, "b_pick_countries"), "ct:text")],
                 [btn(tr(lang, "b_cancel"), "cancel")]])
    if edit:
        await msg.edit_text(text, reply_markup=markup)
    else:
        await msg.answer(text, reply_markup=markup)


@private.callback_query(Form.countries, F.data.startswith("ct:"))
async def f_countries(cb: CallbackQuery, state: FSMContext, lang: str):
    if cb.data == "ct:all":
        await state.update_data(countries="all")
        await ask_languages(cb.message, state, lang, edit=True)
    else:
        await state.set_state(Form.countries_text)
        await show(cb, tr(lang, "countries_prompt"), cancel_kb(lang))
    await cb.answer()


@private.message(Form.countries_text, F.text)
async def f_countries_text(m: Message, state: FSMContext, lang: str):
    text = m.text.strip()
    if not 2 <= len(text) <= 120:
        return await m.answer(tr(lang, "countries_len"))
    await state.update_data(countries=text)
    await ask_languages(m, state, lang)


def lang_keyboard(selected: list[str], lang: str) -> InlineKeyboardMarkup:
    rows = grid([btn(("✓ " if l in selected else "") + l, f"l:{i}") for i, l in enumerate(LANG_NAMES)])
    rows += [[btn(tr(lang, "b_all_langs"), "l:all")], [btn(tr(lang, "b_continue"), "l:done")],
             [btn(tr(lang, "b_cancel"), "cancel")]]
    return kb(rows)


async def ask_languages(msg: Message, state: FSMContext, lang: str, edit: bool = False):
    await state.set_state(Form.languages)
    await state.update_data(langs=[])
    text = tr(lang, "step5")
    if edit:
        await msg.edit_text(text, reply_markup=lang_keyboard([], lang))
    else:
        await msg.answer(text, reply_markup=lang_keyboard([], lang))


@private.callback_query(Form.languages, F.data.startswith("l:"))
async def f_languages(cb: CallbackQuery, state: FSMContext, lang: str):
    val = cb.data.split(":")[1]
    data = await state.get_data()
    langs: list[str] = data.get("langs", [])
    if val == "all":
        await state.update_data(languages="all")
        return await ask_confirm(cb, state, lang)
    if val == "done":
        if not langs:
            return await cb.answer(tr(lang, "pick_one_lang"), show_alert=True)
        await state.update_data(languages=", ".join(langs))
        return await ask_confirm(cb, state, lang)
    name = LANG_NAMES[int(val)]
    langs = [x for x in langs if x != name] if name in langs else langs + [name]
    await state.update_data(langs=langs)
    await cb.message.edit_reply_markup(reply_markup=lang_keyboard(langs, lang))
    await cb.answer()


async def ask_confirm(cb: CallbackQuery, state: FSMContext, lang: str):
    await state.set_state(Form.confirm)
    d = await state.get_data()
    text = tr(lang, "confirm", kind=tr(lang, "kind_" + d["kind"]), title=esc(d["title"]), username=esc(d["username"]),
              purpose=esc(disp_purpose(d["purpose"], lang)), countries=esc(disp_countries(d["countries"], lang)),
              languages=esc(disp_languages(d["languages"], lang)))
    await show(cb, text, kb([[btn(tr(lang, "b_send"), "send:yes")], [btn(tr(lang, "b_cancel"), "cancel")]]))
    await cb.answer()


@private.callback_query(Form.confirm, F.data == "send:yes")
async def f_send(cb: CallbackQuery, state: FSMContext, bot: Bot, lang: str):
    d = await state.get_data()
    if await db.username_taken(d["username"]):
        await state.clear()
        await show(cb, tr(lang, "taken"), back_home(lang))
        return await cb.answer()
    await set_user_lang(cb.from_user.id, lang)  # запоминаем язык для уведомлений
    app = await db.create_application(
        cb.from_user.id, full_name_tag(cb.from_user), d["kind"], d["title"], d["username"],
        d["purpose"], d["countries"], d["languages"], d.get("members"), d.get("owner_status", "unverified"),
    )
    await state.clear()
    try:
        sent = await bot.send_message(
            config.MOD_CHAT_ID, app_card(app), message_thread_id=config.TOPIC_APPLICATIONS,
            reply_markup=app_keyboard(app["id"]),
        )
        await db.set_mod_msg(app["id"], sent.message_id)
    except TelegramAPIError as e:
        log.error("Не удалось отправить заявку модераторам: %s", e)
    await show(cb, tr(lang, "sent", id=app["id"]), back_home(lang))
    await cb.answer()


# ----- проверка лицензии и жалобы -----
async def show_verification(m: Message, reg_id: int, lang: str):
    reg = await db.get_registry(reg_id)
    if not reg:
        return await m.answer(tr(lang, "v_none"), reply_markup=main_menu(lang))
    if not reg["active"]:
        return await m.answer(
            tr(lang, "v_revoked", title=esc(reg["title"]), date=fdate(reg["revoked_at"]), lic=lic(reg["id"])),
            reply_markup=kb([[btn(tr(lang, "b_registry_site"), url=f"{config.SITE_URL}/tele-license#registry")]]))
    await m.answer(
        tr(lang, "v_ok", title=esc(reg["title"]), username=esc(reg["username"]), lic=lic(reg["id"]),
           date=fdate(reg["approved_at"])),
        reply_markup=kb([[btn(tr(lang, "b_open_reg"), url=site_url(reg["id"]))],
                         [btn(tr(lang, "b_complaint"), f"cmp:{reg['id']}")]]))


@private.callback_query(F.data.startswith("cmp:"))
async def complaint_start(cb: CallbackQuery, state: FSMContext, lang: str):
    reg_id = int(cb.data.split(":")[1])
    reg = await db.get_registry(reg_id)
    if not reg or not reg["active"]:
        return await cb.answer(tr(lang, "c_revoked_alert"), show_alert=True)
    if await db.open_complaint_exists(reg_id, cb.from_user.id):
        return await cb.answer(tr(lang, "c_exists_alert"), show_alert=True)
    await state.clear()
    await state.set_state(ComplaintForm.reason)
    await state.update_data(reg_id=reg_id)
    await cb.message.answer(tr(lang, "c_prompt", title=esc(reg["title"])), reply_markup=cancel_kb(lang))
    await cb.answer()


@private.message(ComplaintForm.reason, F.text)
async def complaint_reason(m: Message, state: FSMContext, bot: Bot, lang: str):
    reason = m.text.strip()
    if not 10 <= len(reason) <= 1000:
        return await m.answer(tr(lang, "c_len"))
    reg_id = (await state.get_data())["reg_id"]
    reg = await db.get_registry(reg_id)
    await state.clear()
    if not reg or not reg["active"]:
        return await m.answer(tr(lang, "c_revoked"), reply_markup=main_menu(lang))
    await set_user_lang(m.from_user.id, lang)
    c = await db.create_complaint(reg_id, m.from_user.id, reason)
    try:
        sent = await bot.send_message(
            config.MOD_CHAT_ID, complaint_card(c, reg), message_thread_id=config.TOPIC_COMPLAINTS,
            reply_markup=complaint_keyboard(c["id"]))
        await db.set_complaint_msg(c["id"], sent.message_id)
    except TelegramAPIError as e:
        log.error("Не удалось отправить жалобу модераторам: %s", e)
    await m.answer(tr(lang, "c_sent", id=c["id"]), reply_markup=main_menu(lang))


# =====================================================================
#                              МОДЕРАТОРЫ
# =====================================================================
mod = Router()
mod.message.filter(F.chat.id == config.MOD_CHAT_ID)
mod.callback_query.filter(F.message.chat.id == config.MOD_CHAT_ID)


async def require_mod(cb: CallbackQuery, bot: Bot) -> bool:
    if await is_mod(bot, cb.from_user.id):
        return True
    await cb.answer("Недостаточно прав", show_alert=True)
    return False


@mod.callback_query(F.data.startswith("ma:"))
async def app_accept(cb: CallbackQuery, bot: Bot):
    if not await require_mod(cb, bot):
        return
    app_id = int(cb.data.split(":")[1])
    reg = await db.approve_application(app_id, cb.from_user.id)
    if not reg:
        return await cb.answer("Заявка уже обработана", show_alert=True)
    app = await db.get_application(app_id)
    await cb.message.edit_text(app_card(app) + f"\n\n<b>Принято.</b> Модератор: {esc(cb.from_user.full_name)}\nЛицензия: {lic(reg['id'])}",
                               reply_markup=None)
    link = await verify_url(bot, reg["id"])
    l = await ulang(app["user_id"])
    await notify(
        bot, app["user_id"],
        tr(l, "n_approved", id=app["id"], title=esc(app["title"]), lic=lic(reg["id"]), link=link),
        kb([[btn(tr(l, "b_verify"), url=link)], [btn(tr(l, "b_reg_page"), url=site_url(reg["id"]))]]),
    )
    await cb.answer("Заявка принята")


@mod.callback_query(F.data.startswith("mr:"))
async def app_reject(cb: CallbackQuery, bot: Bot):
    if not await require_mod(cb, bot):
        return
    app_id = int(cb.data.split(":")[1])
    app = await db.get_application(app_id)
    if not app or app["status"] != "pending":
        return await cb.answer("Заявка уже обработана", show_alert=True)
    prompt = await bot.send_message(
        config.MOD_CHAT_ID,
        f"{esc(cb.from_user.full_name)}, ответьте на это сообщение причиной отклонения заявки №{app_id}. "
        "Причина будет отправлена заявителю.",
        message_thread_id=cb.message.message_thread_id,
        reply_markup=ForceReply(selective=True),
    )
    await db.add_pending(config.MOD_CHAT_ID, prompt.message_id, "reject", app_id, cb.from_user.id)
    await cb.answer("Напишите причину ответом на сообщение бота")


@mod.message(F.reply_to_message, F.text)
async def mod_reply(m: Message, bot: Bot):
    pend = await db.get_pending(m.chat.id, m.reply_to_message.message_id)
    if not pend or pend["action"] != "reject" or m.from_user.id != pend["mod_id"]:
        return
    reason = m.text.strip()
    if not 3 <= len(reason) <= 500:
        return await m.reply("Причина должна содержать от 3 до 500 символов.")
    app = await db.reject_application(pend["target_id"], reason, m.from_user.id)
    await db.del_pending(m.chat.id, m.reply_to_message.message_id)
    if not app:
        return await m.reply("Заявка уже обработана.")
    if app["mod_msg_id"]:
        try:
            await bot.edit_message_text(
                app_card(app) + f"\n\n<b>Отклонено.</b> Модератор: {esc(m.from_user.full_name)}\n<b>Причина:</b> {esc(reason)}",
                chat_id=config.MOD_CHAT_ID, message_id=app["mod_msg_id"], reply_markup=None)
        except TelegramAPIError as e:
            log.warning("Не удалось обновить карточку заявки: %s", e)
    for mid in (m.reply_to_message.message_id, m.message_id):
        try:
            await bot.delete_message(m.chat.id, mid)
        except TelegramAPIError:
            pass
    l = await ulang(app["user_id"])
    await notify(bot, app["user_id"],
                 tr(l, "n_rejected", id=app["id"], title=esc(app["title"]), reason=esc(reason)), main_menu(l))


@mod.callback_query(F.data.startswith("cok:"))
async def complaint_ok(cb: CallbackQuery, bot: Bot):
    if not await require_mod(cb, bot):
        return
    c = await db.resolve_complaint(int(cb.data.split(":")[1]), "dismissed", cb.from_user.id)
    if not c:
        return await cb.answer("Жалоба уже обработана", show_alert=True)
    reg = await db.get_registry(c["registry_id"])
    await cb.message.edit_text(complaint_card(c, reg) + f"\n\n<b>Решение: ресурс в порядке.</b> Модератор: {esc(cb.from_user.full_name)}",
                               reply_markup=None)
    l = await ulang(c["user_id"])
    await notify(bot, c["user_id"], tr(l, "n_c_dismissed", id=c["id"], title=esc(reg["title"])))
    await cb.answer("Жалоба закрыта")


@mod.callback_query(F.data.startswith("cbad:"))
async def complaint_bad(cb: CallbackQuery, bot: Bot):
    if not await require_mod(cb, bot):
        return
    c = await db.resolve_complaint(int(cb.data.split(":")[1]), "upheld", cb.from_user.id)
    if not c:
        return await cb.answer("Жалоба уже обработана", show_alert=True)
    reg = await db.get_registry(c["registry_id"])
    await db.revoke_registry(reg["id"], f"Жалоба №{c['id']}")
    others = await db.close_open_complaints(reg["id"], "upheld", cb.from_user.id)
    await cb.message.edit_text(
        complaint_card(c, reg) + f"\n\n<b>Решение: ресурс не в порядке.</b> Лицензия {lic(reg['id'])} отозвана. "
                                 f"Модератор: {esc(cb.from_user.full_name)}",
        reply_markup=None)
    for uid in {c["user_id"], *(o["user_id"] for o in others)}:
        l = await ulang(uid)
        await notify(bot, uid, tr(l, "n_c_upheld", title=esc(reg["title"])))
    l = await ulang(reg["user_id"])
    await notify(bot, reg["user_id"], tr(l, "n_revoked_owner", lic=lic(reg["id"]), title=esc(reg["title"])),
                 kb([[btn(tr(l, "b_news"), url=config.NEWS_CHANNEL)]]))
    await cb.answer("Ресурс удалён из реестра")


# ---------- запасной обработчик в личке ----------
@private.message()
async def fallback(m: Message, state: FSMContext, lang: str):
    if await state.get_state():
        return await m.answer(tr(lang, "use_buttons"))
    if await stored_lang(m.from_user.id) is None:
        return await m.answer(tr("ru", "pick_lang"), reply_markup=lang_picker())
    await m.answer(tr(lang, "welcome"), reply_markup=main_menu(lang))


# =====================================================================
#                           HTTP API ДЛЯ САЙТА
# =====================================================================
def pub(r) -> dict:
    # purpose / countries / languages отдаются как есть: ключи (news, all, ...) или произвольный текст.
    # Перевод ключей выполняет сайт.
    return {
        "id": lic(r["id"]), "num": r["id"], "kind": r["kind"], "title": r["title"],
        "link": f"https://t.me/{r['username']}", "purpose": r["purpose"],
        "countries": r["countries"], "languages": r["languages"],
        "approved_at": r["approved_at"].isoformat(), "active": r["active"],
        "revoked_at": r["revoked_at"].isoformat() if r["revoked_at"] else None,
    }


@web.middleware
async def cors(request: web.Request, handler):
    resp = web.Response() if request.method == "OPTIONS" else await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Cache-Control"] = "public, max-age=30"
    return resp


async def api_list(request: web.Request) -> web.Response:
    q = (request.query.get("q") or "").strip()[:64] or None
    kind = request.query.get("kind")
    kind = kind if kind in KIND_KEYS else None
    try:
        limit = min(max(int(request.query.get("limit", 20)), 1), 100)
        offset = max(int(request.query.get("offset", 0)), 0)
    except ValueError:
        return web.json_response({"error": "bad_request"}, status=400)
    rows, total = await db.list_registry(q, kind, limit, offset)
    return web.json_response({"items": [pub(r) for r in rows], "total": total})


async def api_item(request: web.Request) -> web.Response:
    raw = request.match_info["ident"].upper().replace("TL-", "")
    if not raw.isdigit():
        return web.json_response({"error": "not_found"}, status=404)
    r = await db.get_registry(int(raw))
    if not r:
        return web.json_response({"error": "not_found"}, status=404)
    return web.json_response(pub(r))


async def health(_: web.Request) -> web.Response:
    return web.Response(text="ok")


# =====================================================================
async def main():
    await db.init()
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(mod)
    dp.include_router(private)

    app = web.Application(middlewares=[cors])
    app.router.add_get("/health", health)
    app.router.add_get("/api/registry", api_list)
    app.router.add_get("/api/registry/{ident}", api_item)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", config.PORT).start()
    log.info("HTTP API запущен на порту %s", config.PORT)

    me = await bot.me()
    log.info("Бот запущен: @%s", me.username)
    await bot.delete_webhook(drop_pending_updates=False)
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
