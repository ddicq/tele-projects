import asyncio
import html
import logging
import re

from aiogram import Bot, Dispatcher, F, Router
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
import texts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tele-license")

KIND_LABEL = {"channel": "Публичный канал", "chat": "Публичный чат", "bot": "Бот"}
PURPOSES = ["Новости", "Спорт", "Технологии и разработка", "Финансы и бизнес", "Образование",
            "Развлечения", "Игры", "Сервисы и VPN", "Сообщество"]
LANGS = ["Русский", "English", "Українська", "Қазақша", "Oʻzbekcha", "Español",
         "Deutsch", "Français", "Türkçe", "العربية"]


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


def main_menu() -> InlineKeyboardMarkup:
    return kb([
        [btn("Подать заявку", "menu:apply")],
        [btn("Мои заявки", "menu:my"), btn("Правила", "menu:rules")],
        [btn("Документы", "menu:docs"), btn("Сайт", url=config.SITE_URL)],
        [btn("Новости проекта", url=config.NEWS_CHANNEL)],
    ])


def back_home() -> InlineKeyboardMarkup:
    return kb([[btn("В главное меню", "menu:home")]])


def cancel_kb() -> InlineKeyboardMarkup:
    return kb([[btn("Отменить", "cancel")]])


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


# ---------- проверка ресурса ----------
_LINK_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/([A-Za-z][A-Za-z0-9_]{3,31})/?$|^@([A-Za-z][A-Za-z0-9_]{3,31})$",
    re.I,
)


def parse_username(text: str):
    t = text.strip()
    if "+" in t or "joinchat" in t.lower():
        return None, "Ссылки-приглашения относятся к приватным ресурсам. Лицензия выдаётся только публичным ресурсам. Отправьте ссылку вида https://t.me/username."
    m = _LINK_RE.match(t)
    if not m:
        return None, "Не удалось распознать ссылку. Отправьте ссылку вида https://t.me/username или @username."
    return m.group(1) or m.group(2), None


async def inspect_resource(bot: Bot, kind: str, username: str, user_id: int) -> dict:
    """Автоматические проверки через Bot API. owner: True / False / None (не удалось проверить)."""
    res = {"error": None, "username": username, "members": None, "owner": None}
    try:
        chat = await bot.get_chat(f"@{username}")
    except TelegramAPIError:
        if kind == "bot":
            return res  # у ботов проверка мягкая, дальше смотрит модератор
        res["error"] = "Ресурс не найден или является приватным. Проверьте ссылку: ресурс должен быть публичным."
        return res

    if chat.username:
        res["username"] = chat.username
    if kind == "channel" and chat.type != ChatType.CHANNEL:
        res["error"] = "По этой ссылке находится не канал. Выберите подходящий тип ресурса."
    elif kind == "chat" and chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        res["error"] = "По этой ссылке находится не чат. Выберите подходящий тип ресурса."
    elif kind == "bot" and chat.type != ChatType.PRIVATE:
        res["error"] = "По этой ссылке находится не бот."
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


# ---------- карточки ----------
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
        f"<b>Тип:</b> {KIND_LABEL[a['kind']]}\n"
        f"<b>Название:</b> {esc(a['title'])}\n"
        f"<b>Ссылка:</b> https://t.me/{esc(a['username'])}\n"
        f"<b>Назначение:</b> {esc(a['purpose'])}\n"
        f"<b>Страны:</b> {esc(a['countries'])}\n"
        f"<b>Языки:</b> {esc(a['languages'])}\n"
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
async def cmd_start(m: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    arg = command.args or ""
    if arg.startswith("v_") and arg[2:].isdigit():
        await show_verification(m, int(arg[2:]))
        return
    await m.answer(texts.WELCOME, reply_markup=main_menu())


@private.message(Command("cancel"))
async def cmd_cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Действие отменено.", reply_markup=main_menu())


@private.callback_query(F.data == "cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(cb, texts.WELCOME, main_menu())
    await cb.answer()


# ----- меню -----
@private.callback_query(F.data.startswith("menu:"))
async def cb_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    section = cb.data.split(":")[1]
    if section == "home":
        await show(cb, texts.WELCOME, main_menu())
    elif section == "rules":
        await show(cb, texts.RULES, back_home())
    elif section == "about":
        await show(cb, texts.ABOUT, back_home())
    elif section == "docs":
        await show(cb, texts.DOCS, kb([
            [btn("Условия использования", url=f"{config.SITE_URL}/terms")],
            [btn("Политика конфиденциальности", url=f"{config.SITE_URL}/privacy")],
            [btn("Правила реестра", url=f"{config.SITE_URL}/tele-license#rules")],
            [btn("В главное меню", "menu:home")],
        ]))
    elif section == "apply":
        await show(cb, texts.REQUIREMENTS + "\n\nНиже — правила, по которым ресурсы отклоняются. "
                   "Нажимая «Продолжить», вы подтверждаете, что ознакомились с ними.",
                   kb([[btn("Продолжить", "apply:go")], [btn("Читать правила", "menu:rules")],
                       [btn("В главное меню", "menu:home")]]))
    elif section == "my":
        await show_my(cb)
    await cb.answer()


async def show_my(cb: CallbackQuery):
    rows = await db.user_applications(cb.from_user.id)
    if not rows:
        await show(cb, "У вас пока нет заявок.", kb([[btn("Подать заявку", "menu:apply")], [btn("В главное меню", "menu:home")]]))
        return
    lines = ["<b>Ваши заявки</b>\n"]
    for r in rows:
        if r["status"] == "pending":
            st = "на рассмотрении"
        elif r["status"] == "rejected":
            st = f"отклонена. Причина: {esc(r['reject_reason'])}"
        elif r["reg_active"]:
            st = f"одобрена, лицензия {lic(r['reg_id'])}"
        else:
            st = f"лицензия {lic(r['reg_id'])} отозвана"
        lines.append(f"<b>№{r['id']}</b> · {esc(r['title'])}\n{st}\n")
    await show(cb, "\n".join(lines), back_home())


# ----- подача заявки -----
@private.callback_query(F.data == "apply:go")
async def apply_go(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(Form.kind)
    await show(cb, "<b>Тип ресурса</b>\n\nВыберите, что вы хотите внести в реестр. "
                   "Приватные каналы и чаты не принимаются.",
               kb([[btn("Публичный канал", "k:channel")], [btn("Публичный чат", "k:chat")],
                   [btn("Бот", "k:bot")], [btn("Отменить", "cancel")]]))
    await cb.answer()


@private.callback_query(Form.kind, F.data.startswith("k:"))
async def f_kind(cb: CallbackQuery, state: FSMContext):
    kind = cb.data.split(":")[1]
    if kind not in KIND_LABEL:
        return await cb.answer()
    await state.update_data(kind=kind)
    await state.set_state(Form.title)
    await show(cb, f"<b>Шаг 1 из 5. Название</b>\n\nВведите название ресурса так, как оно указано в Telegram.", cancel_kb())
    await cb.answer()


@private.message(Form.title, F.text)
async def f_title(m: Message, state: FSMContext):
    title = m.text.strip()
    if not 2 <= len(title) <= 64:
        return await m.answer("Название должно содержать от 2 до 64 символов.")
    await state.update_data(title=title)
    await state.set_state(Form.link)
    await m.answer("<b>Шаг 2 из 5. Ссылка</b>\n\nОтправьте публичную ссылку на ресурс: https://t.me/username или @username.",
                   reply_markup=cancel_kb())


@private.message(Form.link, F.text)
async def f_link(m: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    kind = data["kind"]
    username, err = parse_username(m.text)
    if err:
        return await m.answer(err)
    if kind == "bot" and not username.lower().endswith("bot"):
        return await m.answer("Имя пользователя бота должно оканчиваться на «bot».")
    if await db.username_taken(username):
        await state.clear()
        return await m.answer("Этот ресурс уже находится в реестре или на рассмотрении.", reply_markup=main_menu())

    info = await inspect_resource(bot, kind, username, m.from_user.id)
    if info["error"]:
        return await m.answer(info["error"])
    username = info["username"]

    if kind != "bot":
        if info["owner"] is False:
            await state.clear()
            return await m.answer("Вы не значитесь администратором этого ресурса. Заявку может подать только владелец или администратор.",
                                  reply_markup=main_menu())
        if info["members"] is not None and info["members"] < config.MIN_MEMBERS:
            await state.clear()
            return await m.answer(
                f"Ресурс не соответствует требованиям: {num(info['members'])} из {num(config.MIN_MEMBERS)} участников. "
                "Вы сможете подать заявку, когда аудитория достигнет минимума.", reply_markup=main_menu())
    await state.update_data(
        username=username, members=info["members"],
        owner_status="confirmed" if info["owner"] else "unverified",
    )
    if kind == "bot":
        await state.set_state(Form.users)
        return await m.answer("Укажите число ежемесячных пользователей бота так, как оно показано в его профиле. "
                              "Например: 12500.", reply_markup=cancel_kb())
    await ask_purpose(m, state)


@private.message(Form.users, F.text)
async def f_users(m: Message, state: FSMContext):
    digits = re.sub(r"[\s,._]", "", m.text)
    if not digits.isdigit():
        return await m.answer("Введите число цифрами, например 12500.")
    users = int(digits)
    if users < config.MIN_BOT_USERS:
        await state.clear()
        return await m.answer(f"Бот не соответствует требованиям: {num(users)} из {num(config.MIN_BOT_USERS)} пользователей.",
                              reply_markup=main_menu())
    await state.update_data(members=users)
    await ask_purpose(m, state)


async def ask_purpose(m: Message, state: FSMContext):
    await state.set_state(Form.purpose)
    rows = grid([btn(p, f"p:{i}") for i, p in enumerate(PURPOSES)])
    rows += [[btn("Другое", "p:other")], [btn("Отменить", "cancel")]]
    await m.answer("<b>Шаг 3 из 5. Назначение</b>\n\nВыберите тематику ресурса.", reply_markup=kb(rows))


@private.callback_query(Form.purpose, F.data.startswith("p:"))
async def f_purpose(cb: CallbackQuery, state: FSMContext):
    val = cb.data.split(":")[1]
    if val == "other":
        await state.set_state(Form.purpose_text)
        await show(cb, "Опишите назначение ресурса в нескольких словах (до 40 символов).", cancel_kb())
    else:
        await state.update_data(purpose=PURPOSES[int(val)])
        await ask_countries(cb.message, state, edit=True)
    await cb.answer()


@private.message(Form.purpose_text, F.text)
async def f_purpose_text(m: Message, state: FSMContext):
    text = m.text.strip()
    if not 2 <= len(text) <= 40:
        return await m.answer("Описание должно содержать от 2 до 40 символов.")
    await state.update_data(purpose=text)
    await ask_countries(m, state)


async def ask_countries(msg: Message, state: FSMContext, edit: bool = False):
    await state.set_state(Form.countries)
    text = "<b>Шаг 4 из 5. Страны</b>\n\nДля аудитории каких стран предназначен ресурс?"
    markup = kb([[btn("Для всех стран", "ct:all")], [btn("Указать страны", "ct:text")], [btn("Отменить", "cancel")]])
    if edit:
        await msg.edit_text(text, reply_markup=markup)
    else:
        await msg.answer(text, reply_markup=markup)


@private.callback_query(Form.countries, F.data.startswith("ct:"))
async def f_countries(cb: CallbackQuery, state: FSMContext):
    if cb.data == "ct:all":
        await state.update_data(countries="Все страны")
        await ask_languages(cb.message, state, edit=True)
    else:
        await state.set_state(Form.countries_text)
        await show(cb, "Перечислите страны через запятую, например: Россия, Казахстан, Беларусь.", cancel_kb())
    await cb.answer()


@private.message(Form.countries_text, F.text)
async def f_countries_text(m: Message, state: FSMContext):
    text = m.text.strip()
    if not 2 <= len(text) <= 120:
        return await m.answer("Список должен содержать от 2 до 120 символов.")
    await state.update_data(countries=text)
    await ask_languages(m, state)


def lang_keyboard(selected: list[str]) -> InlineKeyboardMarkup:
    rows = grid([btn(("✓ " if l in selected else "") + l, f"l:{i}") for i, l in enumerate(LANGS)])
    rows += [[btn("На всех языках", "l:all")], [btn("Продолжить", "l:done")], [btn("Отменить", "cancel")]]
    return kb(rows)


async def ask_languages(msg: Message, state: FSMContext, edit: bool = False):
    await state.set_state(Form.languages)
    await state.update_data(langs=[])
    text = "<b>Шаг 5 из 5. Языки</b>\n\nОтметьте языки, на которых ведётся ресурс, и нажмите «Продолжить»."
    if edit:
        await msg.edit_text(text, reply_markup=lang_keyboard([]))
    else:
        await msg.answer(text, reply_markup=lang_keyboard([]))


@private.callback_query(Form.languages, F.data.startswith("l:"))
async def f_languages(cb: CallbackQuery, state: FSMContext):
    val = cb.data.split(":")[1]
    data = await state.get_data()
    langs: list[str] = data.get("langs", [])
    if val == "all":
        await state.update_data(languages="Все языки")
        return await ask_confirm(cb, state)
    if val == "done":
        if not langs:
            return await cb.answer("Выберите хотя бы один язык", show_alert=True)
        await state.update_data(languages=", ".join(langs))
        return await ask_confirm(cb, state)
    lang = LANGS[int(val)]
    langs = [x for x in langs if x != lang] if lang in langs else langs + [lang]
    await state.update_data(langs=langs)
    await cb.message.edit_reply_markup(reply_markup=lang_keyboard(langs))
    await cb.answer()


async def ask_confirm(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Form.confirm)
    d = await state.get_data()
    text = (
        "<b>Проверьте данные заявки</b>\n\n"
        f"<b>Тип:</b> {KIND_LABEL[d['kind']]}\n"
        f"<b>Название:</b> {esc(d['title'])}\n"
        f"<b>Ссылка:</b> https://t.me/{esc(d['username'])}\n"
        f"<b>Назначение:</b> {esc(d['purpose'])}\n"
        f"<b>Страны:</b> {esc(d['countries'])}\n"
        f"<b>Языки:</b> {esc(d['languages'])}\n\n"
        "Отправляя заявку, вы подтверждаете, что являетесь владельцем или администратором ресурса, "
        "что указанные данные достоверны, а ресурс соответствует требованиям и правилам."
    )
    await show(cb, text, kb([[btn("Отправить на рассмотрение", "send:yes")], [btn("Отменить", "cancel")]]))
    await cb.answer()


@private.callback_query(Form.confirm, F.data == "send:yes")
async def f_send(cb: CallbackQuery, state: FSMContext, bot: Bot):
    d = await state.get_data()
    if await db.username_taken(d["username"]):
        await state.clear()
        await show(cb, "Этот ресурс уже находится в реестре или на рассмотрении.", back_home())
        return await cb.answer()
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
    await show(cb, f"<b>Заявка №{app['id']} отправлена</b>\n\nМодераторы рассмотрят её. "
                   "Результат придёт в этот чат. Статус можно посмотреть в разделе «Мои заявки».", back_home())
    await cb.answer()


# ----- проверка лицензии и жалобы -----
async def show_verification(m: Message, reg_id: int):
    reg = await db.get_registry(reg_id)
    if not reg:
        return await m.answer("Лицензия не найдена. Такого ресурса нет в реестре.", reply_markup=main_menu())
    if not reg["active"]:
        return await m.answer(
            "<b>Лицензия недействительна</b>\n\n"
            f"Ресурс «{esc(reg['title'])}» исключён из реестра безопасных ресурсов "
            f"{fdate(reg['revoked_at'])}.\n"
            f"Номер лицензии: {lic(reg['id'])}",
            reply_markup=kb([[btn("Реестр на сайте", url=f"{config.SITE_URL}/tele-license#registry")]]))
    await m.answer(
        "<b>Ресурс находится в реестре безопасных ресурсов</b>\n\n"
        f"<b>Название:</b> {esc(reg['title'])}\n"
        f"<b>Ссылка:</b> https://t.me/{esc(reg['username'])}\n"
        f"<b>Лицензия:</b> {lic(reg['id'])}\n"
        f"<b>Дата подтверждения:</b> {fdate(reg['approved_at'])}\n\n"
        "Считаете, что ресурс нарушает правила? Нажмите на кнопку жалобы, чтобы модераторы рассмотрели вашу проблему!",
        reply_markup=kb([[btn("Открыть в реестре на сайте", url=site_url(reg["id"]))],
                         [btn("Жалоба", f"cmp:{reg['id']}")]]))


@private.callback_query(F.data.startswith("cmp:"))
async def complaint_start(cb: CallbackQuery, state: FSMContext):
    reg_id = int(cb.data.split(":")[1])
    reg = await db.get_registry(reg_id)
    if not reg or not reg["active"]:
        return await cb.answer("Лицензия уже недействительна", show_alert=True)
    if await db.open_complaint_exists(reg_id, cb.from_user.id):
        return await cb.answer("Ваша жалоба на этот ресурс уже рассматривается", show_alert=True)
    await state.clear()
    await state.set_state(ComplaintForm.reason)
    await state.update_data(reg_id=reg_id)
    await cb.message.answer(
        f"<b>Жалоба на «{esc(reg['title'])}»</b>\n\nОпишите, какое правило нарушает ресурс (от 10 до 1000 символов). "
        "По возможности приложите ссылки на конкретные публикации.", reply_markup=cancel_kb())
    await cb.answer()


@private.message(ComplaintForm.reason, F.text)
async def complaint_reason(m: Message, state: FSMContext, bot: Bot):
    reason = m.text.strip()
    if not 10 <= len(reason) <= 1000:
        return await m.answer("Описание должно содержать от 10 до 1000 символов.")
    reg_id = (await state.get_data())["reg_id"]
    reg = await db.get_registry(reg_id)
    await state.clear()
    if not reg or not reg["active"]:
        return await m.answer("Лицензия уже недействительна.", reply_markup=main_menu())
    c = await db.create_complaint(reg_id, m.from_user.id, reason)
    try:
        sent = await bot.send_message(
            config.MOD_CHAT_ID, complaint_card(c, reg), message_thread_id=config.TOPIC_COMPLAINTS,
            reply_markup=complaint_keyboard(c["id"]))
        await db.set_complaint_msg(c["id"], sent.message_id)
    except TelegramAPIError as e:
        log.error("Не удалось отправить жалобу модераторам: %s", e)
    await m.answer(f"<b>Жалоба №{c['id']} отправлена</b>\n\nМодераторы рассмотрят её, ответ придёт в этот чат.",
                   reply_markup=main_menu())


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
    await notify(
        bot, app["user_id"],
        f"<b>Заявка №{app['id']} одобрена</b>\n\n"
        f"Ресурс «{esc(app['title'])}» внесён в реестр безопасных ресурсов.\n"
        f"<b>Номер лицензии:</b> {lic(reg['id'])}\n"
        f"<b>Ссылка подтверждения:</b> {link}\n\n"
        "Разместите ссылку подтверждения в описании ресурса. Перейдя по ней, пользователи увидят, "
        "что ресурс находится в реестре.",
        kb([[btn("Ссылка подтверждения", url=link)], [btn("Страница в реестре", url=site_url(reg["id"]))]]),
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
    await notify(
        bot, app["user_id"],
        f"<b>Заявка №{app['id']} отклонена</b>\n\n"
        f"Ресурс «{esc(app['title'])}» отклонён модератором.\n<b>Причина:</b> {esc(reason)}",
        main_menu(),
    )


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
    await notify(bot, c["user_id"],
                 f"<b>Жалоба №{c['id']} рассмотрена</b>\n\nРесурс «{esc(reg['title'])}»: модераторы приняли решение, "
                 "что нарушений не обнаружено.")
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
    text = (f"<b>Жалоба рассмотрена</b>\n\nНарушение подтверждено. Ресурс «{esc(reg['title'])}» "
            "исключён из реестра безопасных ресурсов, лицензия недействительна.")
    for uid in {c["user_id"], *(o["user_id"] for o in others)}:
        await notify(bot, uid, text)
    await notify(bot, reg["user_id"],
                 f"<b>Лицензия {lic(reg['id'])} отозвана</b>\n\nПо результатам рассмотрения жалобы ресурс «{esc(reg['title'])}» "
                 "исключён из реестра. Если вы считаете это ошибкой, свяжитесь с нами через канал проекта.",
                 kb([[btn("Новости проекта", url=config.NEWS_CHANNEL)]]))
    await cb.answer("Ресурс удалён из реестра")


# ---------- запасной обработчик в личке ----------
@private.message()
async def fallback(m: Message, state: FSMContext):
    if await state.get_state():
        return await m.answer("Используйте кнопки под предыдущим сообщением или отправьте /cancel.")
    await m.answer(texts.WELCOME, reply_markup=main_menu())


# =====================================================================
#                           HTTP API ДЛЯ САЙТА
# =====================================================================
def pub(r) -> dict:
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
    kind = kind if kind in KIND_LABEL else None
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
