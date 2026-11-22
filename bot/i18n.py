"""Тексты бота на русском и английском."""
import config

DEFAULT_LANG = "ru"
LANGS_AVAILABLE = ("ru", "en")


def _num(n: int) -> str:
    return f"{n:,}".replace(",", " ")


STR = {
"ru": {
 "pick_lang": "Выберите язык / Choose your language",
 "welcome": (
    "<b>Tele License</b>\n"
    "Реестр проверенных и безопасных ресурсов Telegram.\n\n"
    "Мы рассматриваем публичные каналы, чаты и ботов. Ресурс, прошедший проверку, получает лицензию "
    "и попадает в открытый реестр. Подлинность лицензии может проверить любой пользователь.\n\n"
    "<b>Через бота можно:</b>\n"
    "• подать заявку на лицензию;\n"
    "• отслеживать статус заявок;\n"
    "• изучить правила и документы.\n\n"
    "<i>Продолжая пользоваться ботом, вы принимаете Условия использования и Политику конфиденциальности.</i>"),
 "requirements": (
    "<b>Требования к ресурсам</b>\n\n"
    "<b>Каналы и чаты</b>\n"
    "• публичные, с постоянной ссылкой t.me/username;\n"
    "• не менее {members} участников;\n"
    "• существуют более одного месяца;\n"
    "• опубликовано не менее 20 сообщений.\n\n"
    "<b>Боты</b>\n"
    "• не менее {bots} пользователей;\n"
    "• бот работает и отвечает на команды.\n\n"
    "<b>Приватные ресурсы не принимаются.</b>"),
 "apply_note": "Нажимая «Продолжить», вы подтверждаете, что ознакомились с правилами, по которым ресурсы отклоняются.",
 "rules": (
    "<b>Правила Tele License</b>\n\n"
    "Лицензия не выдаётся, а действующая отзывается, если ресурс:\n\n"
    "1. содержит контент 18+ (кроме материалов в новостном формате);\n"
    "2. распространяет вредоносное ПО, вредоносный код или опасные ссылки, включая фишинг;\n"
    "3. обманывает людей: мошеннические схемы, финансовые пирамиды, ложные обещания гарантированного дохода;\n"
    "4. имеет метку SCAM или FAKE;\n"
    "5. призывает к насилию, разжигает ненависть, поддерживает экстремизм;\n"
    "6. продаёт или рекламирует запрещённые товары и услуги: наркотики, оружие, поддельные документы;\n"
    "7. собирает или публикует персональные данные без согласия, занимается доксингом;\n"
    "8. выдаёт себя за другой ресурс, бренд или человека;\n"
    "9. накручивает аудиторию или распространяет спам;\n"
    "10. нарушает авторские права или Условия использования Telegram.\n\n"
    "<b>Дополнительно</b>\n"
    "• Заявку подаёт владелец или администратор ресурса.\n"
    "• Данные в заявке должны быть достоверными.\n"
    "• Лицензия может быть отозвана в любой момент, если ресурс перестал соответствовать правилам.\n"
    "• Tele License — независимый проект и не связан с Telegram. Лицензия не является гарантией безопасности."),
 "docs": "<b>Документы</b>\n\nПолные версии документов опубликованы на сайте TeleProjects.",
 "about": (
    "<b>О проекте</b>\n\n"
    "Tele License — проект TeleProjects. Мы ведём открытый реестр ресурсов Telegram, "
    "которые прошли проверку модераторами.\n\n"
    "Если ресурс получил лицензию, это можно подтвердить по ссылке проверки. "
    "Если ресурс нарушает правила, на него можно подать жалобу, и лицензию отзовут."),
 # кнопки
 "b_apply": "Подать заявку", "b_my": "Мои заявки", "b_rules": "Правила", "b_docs": "Документы",
 "b_site": "Сайт", "b_news": "Новости проекта", "b_home": "В главное меню", "b_cancel": "Отменить",
 "b_continue": "Продолжить", "b_read_rules": "Читать правила", "b_terms": "Условия использования",
 "b_privacy": "Политика конфиденциальности", "b_reg_rules": "Правила реестра", "b_lang": "Язык / Language",
 "b_send": "Отправить на рассмотрение", "b_all_countries": "Для всех стран", "b_pick_countries": "Указать страны",
 "b_other": "Другое", "b_all_langs": "На всех языках", "b_registry_site": "Реестр на сайте",
 "b_open_reg": "Открыть в реестре на сайте", "b_complaint": "Жалоба", "b_verify": "Ссылка подтверждения",
 "b_reg_page": "Страница в реестре",
 "cancelled": "Действие отменено.",
 # типы
 "kind_channel": "Публичный канал", "kind_chat": "Публичный чат", "kind_bot": "Бот",
 "kind_title": "<b>Тип ресурса</b>\n\nВыберите, что вы хотите внести в реестр. Приватные каналы и чаты не принимаются.",
 "step1": "<b>Шаг 1 из 5. Название</b>\n\nВведите название ресурса так, как оно указано в Telegram.",
 "step2": "<b>Шаг 2 из 5. Ссылка</b>\n\nОтправьте публичную ссылку на ресурс: https://t.me/username или @username.",
 "title_len": "Название должно содержать от 2 до 64 символов.",
 "link_private": "Ссылки-приглашения относятся к приватным ресурсам. Лицензия выдаётся только публичным ресурсам. Отправьте ссылку вида https://t.me/username.",
 "link_format": "Не удалось распознать ссылку. Отправьте ссылку вида https://t.me/username или @username.",
 "taken": "Этот ресурс уже находится в реестре или на рассмотрении.",
 "not_found": "Ресурс не найден или является приватным. Проверьте ссылку: ресурс должен быть публичным.",
 "not_channel": "По этой ссылке находится не канал. Выберите подходящий тип ресурса.",
 "not_chat": "По этой ссылке находится не чат. Выберите подходящий тип ресурса.",
 "not_bot": "По этой ссылке находится не бот.",
 "not_admin": "Вы не значитесь администратором этого ресурса. Заявку может подать только владелец или администратор.",
 "members_low": "Ресурс не соответствует требованиям: {n} из {min} участников. Вы сможете подать заявку, когда аудитория достигнет минимума.",
 "users_prompt": "Укажите число ежемесячных пользователей бота так, как оно показано в его профиле. Например: 12500.",
 "users_nan": "Введите число цифрами, например 12500.",
 "users_low": "Бот не соответствует требованиям: {n} из {min} пользователей.",
 "step3": "<b>Шаг 3 из 5. Назначение</b>\n\nВыберите тематику ресурса.",
 "purpose_other": "Опишите назначение ресурса в нескольких словах (до 40 символов).",
 "purpose_len": "Описание должно содержать от 2 до 40 символов.",
 "step4": "<b>Шаг 4 из 5. Страны</b>\n\nДля аудитории каких стран предназначен ресурс?",
 "countries_prompt": "Перечислите страны через запятую, например: Россия, Казахстан, Беларусь.",
 "countries_len": "Список должен содержать от 2 до 120 символов.",
 "step5": "<b>Шаг 5 из 5. Языки</b>\n\nОтметьте языки, на которых ведётся ресурс, и нажмите «Продолжить».",
 "pick_one_lang": "Выберите хотя бы один язык",
 "all_countries": "Все страны", "all_languages": "Все языки",
 "confirm": (
    "<b>Проверьте данные заявки</b>\n\n"
    "<b>Тип:</b> {kind}\n<b>Название:</b> {title}\n<b>Ссылка:</b> https://t.me/{username}\n"
    "<b>Назначение:</b> {purpose}\n<b>Страны:</b> {countries}\n<b>Языки:</b> {languages}\n\n"
    "Отправляя заявку, вы подтверждаете, что являетесь владельцем или администратором ресурса, "
    "что указанные данные достоверны, а ресурс соответствует требованиям и правилам."),
 "sent": "<b>Заявка №{id} отправлена</b>\n\nМодераторы рассмотрят её. Результат придёт в этот чат. Статус можно посмотреть в разделе «Мои заявки».",
 "no_apps": "У вас пока нет заявок.", "my_header": "<b>Ваши заявки</b>\n",
 "st_pending": "на рассмотрении", "st_rejected": "отклонена. Причина: {reason}",
 "st_approved": "одобрена, лицензия {lic}", "st_revoked": "лицензия {lic} отозвана",
 # проверка лицензии
 "v_none": "Лицензия не найдена. Такого ресурса нет в реестре.",
 "v_revoked": "<b>Лицензия недействительна</b>\n\nРесурс «{title}» исключён из реестра безопасных ресурсов {date}.\nНомер лицензии: {lic}",
 "v_ok": (
    "<b>Ресурс находится в реестре безопасных ресурсов</b>\n\n"
    "<b>Название:</b> {title}\n<b>Ссылка:</b> https://t.me/{username}\n<b>Лицензия:</b> {lic}\n"
    "<b>Дата подтверждения:</b> {date}\n\n"
    "Считаете, что ресурс нарушает правила? Нажмите на кнопку жалобы, чтобы модераторы рассмотрели вашу проблему!"),
 # жалобы
 "c_revoked_alert": "Лицензия уже недействительна",
 "c_exists_alert": "Ваша жалоба на этот ресурс уже рассматривается",
 "c_prompt": "<b>Жалоба на «{title}»</b>\n\nОпишите, какое правило нарушает ресурс (от 10 до 1000 символов). По возможности приложите ссылки на конкретные публикации.",
 "c_len": "Описание должно содержать от 10 до 1000 символов.",
 "c_revoked": "Лицензия уже недействительна.",
 "c_sent": "<b>Жалоба №{id} отправлена</b>\n\nМодераторы рассмотрят её, ответ придёт в этот чат.",
 # уведомления
 "n_approved": (
    "<b>Заявка №{id} одобрена</b>\n\nРесурс «{title}» внесён в реестр безопасных ресурсов.\n"
    "<b>Номер лицензии:</b> {lic}\n<b>Ссылка подтверждения:</b> {link}\n\n"
    "Разместите ссылку подтверждения в описании ресурса. Перейдя по ней, пользователи увидят, что ресурс находится в реестре."),
 "n_rejected": "<b>Заявка №{id} отклонена</b>\n\nРесурс «{title}» отклонён модератором.\n<b>Причина:</b> {reason}",
 "n_c_dismissed": "<b>Жалоба №{id} рассмотрена</b>\n\nРесурс «{title}»: модераторы приняли решение, что нарушений не обнаружено.",
 "n_c_upheld": "<b>Жалоба рассмотрена</b>\n\nНарушение подтверждено. Ресурс «{title}» исключён из реестра безопасных ресурсов, лицензия недействительна.",
 "n_revoked_owner": "<b>Лицензия {lic} отозвана</b>\n\nПо результатам рассмотрения жалобы ресурс «{title}» исключён из реестра. Если вы считаете это ошибкой, свяжитесь с нами через канал проекта.",
 "use_buttons": "Используйте кнопки под предыдущим сообщением или отправьте /cancel.",
},
"en": {
 "pick_lang": "Выберите язык / Choose your language",
 "welcome": (
    "<b>Tele License</b>\n"
    "A registry of verified and safe Telegram resources.\n\n"
    "We review public channels, chats and bots. A resource that passes the review receives a license "
    "and is listed in the open registry. Anyone can verify a license.\n\n"
    "<b>With this bot you can:</b>\n"
    "• apply for a license;\n"
    "• track the status of your applications;\n"
    "• read the rules and documents.\n\n"
    "<i>By using the bot, you accept the Terms of Use and the Privacy Policy.</i>"),
 "requirements": (
    "<b>Resource requirements</b>\n\n"
    "<b>Channels and chats</b>\n"
    "• public, with a permanent t.me/username link;\n"
    "• at least {members} members;\n"
    "• existed for more than one month;\n"
    "• at least 20 messages published.\n\n"
    "<b>Bots</b>\n"
    "• at least {bots} users;\n"
    "• the bot is working and responds to commands.\n\n"
    "<b>Private resources are not accepted.</b>"),
 "apply_note": "By tapping “Continue”, you confirm that you have read the rules under which resources are rejected.",
 "rules": (
    "<b>Tele License rules</b>\n\n"
    "A license is not issued, and an existing one is revoked, if the resource:\n\n"
    "1. contains 18+ content (except news-style material);\n"
    "2. distributes malware, malicious code or dangerous links, including phishing;\n"
    "3. deceives people: scams, financial pyramids, false promises of guaranteed income;\n"
    "4. carries a SCAM or FAKE label;\n"
    "5. calls for violence, incites hatred or supports extremism;\n"
    "6. sells or promotes prohibited goods and services: drugs, weapons, forged documents;\n"
    "7. collects or publishes personal data without consent, or engages in doxxing;\n"
    "8. impersonates another resource, brand or person;\n"
    "9. inflates its audience artificially or spreads spam;\n"
    "10. violates copyright or Telegram’s Terms of Service.\n\n"
    "<b>Additionally</b>\n"
    "• The application must be submitted by the owner or an administrator of the resource.\n"
    "• The data in the application must be accurate.\n"
    "• A license may be revoked at any time if the resource stops complying with the rules.\n"
    "• Tele License is an independent project and is not affiliated with Telegram. A license is not a guarantee of safety."),
 "docs": "<b>Documents</b>\n\nFull versions of the documents are published on the TeleProjects website.",
 "about": (
    "<b>About</b>\n\n"
    "Tele License is a TeleProjects project. We maintain an open registry of Telegram resources "
    "that have been reviewed by moderators.\n\n"
    "If a resource has a license, you can confirm it with a verification link. "
    "If a resource breaks the rules, you can file a complaint and the license will be revoked."),
 "b_apply": "Apply for a license", "b_my": "My applications", "b_rules": "Rules", "b_docs": "Documents",
 "b_site": "Website", "b_news": "Project news", "b_home": "Main menu", "b_cancel": "Cancel",
 "b_continue": "Continue", "b_read_rules": "Read the rules", "b_terms": "Terms of Use",
 "b_privacy": "Privacy Policy", "b_reg_rules": "Registry rules", "b_lang": "Язык / Language",
 "b_send": "Submit for review", "b_all_countries": "All countries", "b_pick_countries": "Specify countries",
 "b_other": "Other", "b_all_langs": "All languages", "b_registry_site": "Registry on the website",
 "b_open_reg": "Open in the registry", "b_complaint": "Report", "b_verify": "Verification link",
 "b_reg_page": "Registry page",
 "cancelled": "Action cancelled.",
 "kind_channel": "Public channel", "kind_chat": "Public chat", "kind_bot": "Bot",
 "kind_title": "<b>Resource type</b>\n\nChoose what you want to add to the registry. Private channels and chats are not accepted.",
 "step1": "<b>Step 1 of 5. Name</b>\n\nEnter the name of the resource exactly as it appears in Telegram.",
 "step2": "<b>Step 2 of 5. Link</b>\n\nSend the public link to the resource: https://t.me/username or @username.",
 "title_len": "The name must be between 2 and 64 characters long.",
 "link_private": "Invite links belong to private resources. Licenses are issued to public resources only. Send a link like https://t.me/username.",
 "link_format": "Could not recognize the link. Send a link like https://t.me/username or @username.",
 "taken": "This resource is already in the registry or under review.",
 "not_found": "The resource was not found or is private. Check the link: the resource must be public.",
 "not_channel": "This link does not lead to a channel. Choose the correct resource type.",
 "not_chat": "This link does not lead to a chat. Choose the correct resource type.",
 "not_bot": "This link does not lead to a bot.",
 "not_admin": "You are not listed as an administrator of this resource. Only the owner or an administrator can apply.",
 "members_low": "The resource does not meet the requirements: {n} of {min} members. You can apply once the audience reaches the minimum.",
 "users_prompt": "Enter the number of monthly users of the bot as shown in its profile. For example: 12500.",
 "users_nan": "Enter the number in digits, for example 12500.",
 "users_low": "The bot does not meet the requirements: {n} of {min} users.",
 "step3": "<b>Step 3 of 5. Purpose</b>\n\nChoose the topic of the resource.",
 "purpose_other": "Describe the purpose of the resource in a few words (up to 40 characters).",
 "purpose_len": "The description must be between 2 and 40 characters long.",
 "step4": "<b>Step 4 of 5. Countries</b>\n\nWhich countries’ audience is the resource intended for?",
 "countries_prompt": "List the countries separated by commas, for example: Germany, France, Spain.",
 "countries_len": "The list must be between 2 and 120 characters long.",
 "step5": "<b>Step 5 of 5. Languages</b>\n\nSelect the languages of the resource and tap “Continue”.",
 "pick_one_lang": "Select at least one language",
 "all_countries": "All countries", "all_languages": "All languages",
 "confirm": (
    "<b>Check your application</b>\n\n"
    "<b>Type:</b> {kind}\n<b>Name:</b> {title}\n<b>Link:</b> https://t.me/{username}\n"
    "<b>Purpose:</b> {purpose}\n<b>Countries:</b> {countries}\n<b>Languages:</b> {languages}\n\n"
    "By submitting the application, you confirm that you are the owner or an administrator of the resource, "
    "that the data is accurate, and that the resource meets the requirements and rules."),
 "sent": "<b>Application #{id} submitted</b>\n\nModerators will review it. The result will arrive in this chat. You can check the status under “My applications”.",
 "no_apps": "You have no applications yet.", "my_header": "<b>Your applications</b>\n",
 "st_pending": "under review", "st_rejected": "rejected. Reason: {reason}",
 "st_approved": "approved, license {lic}", "st_revoked": "license {lic} revoked",
 "v_none": "License not found. This resource is not in the registry.",
 "v_revoked": "<b>License is no longer valid</b>\n\nThe resource “{title}” was removed from the registry of safe resources on {date}.\nLicense number: {lic}",
 "v_ok": (
    "<b>This resource is in the registry of safe resources</b>\n\n"
    "<b>Name:</b> {title}\n<b>Link:</b> https://t.me/{username}\n<b>License:</b> {lic}\n"
    "<b>Verified on:</b> {date}\n\n"
    "Think the resource breaks the rules? Tap the report button so moderators can look into it!"),
 "c_revoked_alert": "The license is no longer valid",
 "c_exists_alert": "Your report on this resource is already being reviewed",
 "c_prompt": "<b>Report on “{title}”</b>\n\nDescribe which rule the resource breaks (10 to 1000 characters). If possible, include links to specific posts.",
 "c_len": "The description must be between 10 and 1000 characters long.",
 "c_revoked": "The license is no longer valid.",
 "c_sent": "<b>Report #{id} submitted</b>\n\nModerators will review it. The answer will arrive in this chat.",
 "n_approved": (
    "<b>Application #{id} approved</b>\n\nThe resource “{title}” has been added to the registry of safe resources.\n"
    "<b>License number:</b> {lic}\n<b>Verification link:</b> {link}\n\n"
    "Place the verification link in the description of your resource. Users who open it will see that the resource is in the registry."),
 "n_rejected": "<b>Application #{id} rejected</b>\n\nThe resource “{title}” was rejected by a moderator.\n<b>Reason:</b> {reason}",
 "n_c_dismissed": "<b>Report #{id} reviewed</b>\n\nResource “{title}”: moderators decided that no violations were found.",
 "n_c_upheld": "<b>Report reviewed</b>\n\nThe violation was confirmed. The resource “{title}” has been removed from the registry of safe resources and its license is no longer valid.",
 "n_revoked_owner": "<b>License {lic} revoked</b>\n\nFollowing the review of a report, the resource “{title}” has been removed from the registry. If you believe this is a mistake, contact us through the project channel.",
 "use_buttons": "Use the buttons under the previous message or send /cancel.",
},
}

PURPOSE_KEYS = ["news", "sports", "tech", "finance", "education", "entertainment", "games", "services", "community"]
STR["ru"].update({
 "p_news": "Новости", "p_sports": "Спорт", "p_tech": "Технологии и разработка", "p_finance": "Финансы и бизнес",
 "p_education": "Образование", "p_entertainment": "Развлечения", "p_games": "Игры",
 "p_services": "Сервисы и VPN", "p_community": "Сообщество"})
STR["en"].update({
 "p_news": "News", "p_sports": "Sports", "p_tech": "Technology & development", "p_finance": "Finance & business",
 "p_education": "Education", "p_entertainment": "Entertainment", "p_games": "Games",
 "p_services": "Services & VPN", "p_community": "Community"})

LANG_NAMES = ["Русский", "English", "Українська", "Қазақша", "Oʻzbekcha", "Español",
              "Deutsch", "Français", "Türkçe", "العربية"]


def tr(lang: str, key: str, **kw) -> str:
    table = STR.get(lang) or STR[DEFAULT_LANG]
    text = table.get(key) or STR[DEFAULT_LANG][key]
    kw.setdefault("members", _num(config.MIN_MEMBERS))
    kw.setdefault("bots", _num(config.MIN_BOT_USERS))
    return text.format(**kw) if kw else text


def disp_purpose(value: str, lang: str) -> str:
    return tr(lang, "p_" + value) if value in PURPOSE_KEYS else value


def disp_countries(value: str, lang: str) -> str:
    return tr(lang, "all_countries") if value == "all" else value


def disp_languages(value: str, lang: str) -> str:
    return tr(lang, "all_languages") if value == "all" else value
