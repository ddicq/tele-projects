// Язык сайта: ru / en. Статические тексты переводятся по data-i18n (словарь в en.js),
// динамические — через t().
(() => {
  const RU_LIKE = ["ru", "be", "kk", "uk"];
  let stored = null;
  try { stored = localStorage.getItem("tp_lang"); } catch (e) {}
  const nav = (navigator.language || "ru").slice(0, 2).toLowerCase();
  const lang = stored === "ru" || stored === "en" ? stored : (RU_LIKE.includes(nav) ? "ru" : "en");
  document.documentElement.lang = lang;

  const EN = window.TL_EN || {};
  const DYN = {
    ru: {
      kind_channel: "Канал", kind_chat: "Чат", kind_bot: "Бот",
      p_news: "Новости", p_sports: "Спорт", p_tech: "Технологии и разработка", p_finance: "Финансы и бизнес",
      p_education: "Образование", p_entertainment: "Развлечения", p_games: "Игры", p_services: "Сервисы и VPN",
      p_community: "Сообщество",
      all_countries: "Все страны", all_languages: "Все языки",
      reg_loading: "Загрузка реестра…", reg_empty: "Ресурсы не найдены. Измените запрос или фильтр.",
      reg_error: "Реестр временно недоступен. Повторите попытку через минуту.",
      res_nf_title: "Лицензия не найдена", res_nf_bad: "Проверьте номер лицензии.", res_nf_text: "Ресурса с таким номером нет в реестре.",
      res_back: "Вернуться к реестру", res_ok: "Лицензия действительна", res_bad: "Лицензия недействительна",
      res_ok_text: "Ресурс находится в реестре безопасных ресурсов Tele License.",
      res_bad_text: "Ресурс исключён из реестра {date}. Подтверждение не действует.",
      dt_lic: "Номер лицензии", dt_type: "Тип", dt_addr: "Адрес", dt_topic: "Тематика", dt_countries: "Страны",
      dt_langs: "Языки", dt_date: "Дата подтверждения",
      btn_go: "Перейти к ресурсу", btn_report: "Подать жалобу в боте", btn_all: "Весь реестр",
      res_err_title: "Не удалось загрузить данные", res_err_text: "Сервис проверки временно недоступен. Повторите попытку через минуту.",
      doc_title: "{title} — лицензия {id}",
      au_loading: "Загрузка аукциона…", au_error: "Аукцион временно недоступен. Повторите попытку через минуту.",
      au_st_idle: "Ожидает первой ставки", au_st_active: "Идёт аукцион", au_st_closing: "Завершается", au_st_sold: "Продан",
      au_left_dh: "{d} д {h} ч", au_left_hm: "{h} ч {m} мин", au_bid: "Сделать ставку", au_start: "старт", au_bids: "ставок: {n}"
    },
    en: {
      kind_channel: "Channel", kind_chat: "Chat", kind_bot: "Bot",
      p_news: "News", p_sports: "Sports", p_tech: "Technology & development", p_finance: "Finance & business",
      p_education: "Education", p_entertainment: "Entertainment", p_games: "Games", p_services: "Services & VPN",
      p_community: "Community",
      all_countries: "All countries", all_languages: "All languages",
      reg_loading: "Loading the registry…", reg_empty: "No resources found. Change the search or the filter.",
      reg_error: "The registry is temporarily unavailable. Please try again in a minute.",
      res_nf_title: "License not found", res_nf_bad: "Check the license number.", res_nf_text: "There is no resource with this number in the registry.",
      res_back: "Back to the registry", res_ok: "License is valid", res_bad: "License is no longer valid",
      res_ok_text: "This resource is in the Tele License registry of safe resources.",
      res_bad_text: "This resource was removed from the registry on {date}. The verification is no longer valid.",
      dt_lic: "License number", dt_type: "Type", dt_addr: "Address", dt_topic: "Topic", dt_countries: "Countries",
      dt_langs: "Languages", dt_date: "Verified on",
      btn_go: "Go to the resource", btn_report: "Report in the bot", btn_all: "Full registry",
      res_err_title: "Could not load the data", res_err_text: "The verification service is temporarily unavailable. Please try again in a minute.",
      doc_title: "{title} — license {id}",
      au_loading: "Loading the auction…", au_error: "The auction is temporarily unavailable. Please try again in a minute.",
      au_st_idle: "Waiting for the first bid", au_st_active: "In progress", au_st_closing: "Ending", au_st_sold: "Sold",
      au_left_dh: "{d}d {h}h", au_left_hm: "{h}h {m}m", au_bid: "Place a bid", au_start: "start", au_bids: "bids: {n}"
    }
  };

  const t = (k, vars) => {
    let s = (DYN[lang] && DYN[lang][k]) ?? DYN.ru[k] ?? k;
    if (vars) for (const x in vars) s = s.split("{" + x + "}").join(vars[x]);
    return s;
  };
  const fmt = iso => new Date(iso).toLocaleDateString(lang === "ru" ? "ru-RU" : "en-GB", { day: "numeric", month: "long", year: "numeric" });

  if (lang === "en") {
    document.querySelectorAll("[data-i18n]").forEach(el => {
      const text = EN[el.dataset.i18n];
      if (text === undefined) return;
      const attr = el.dataset.i18nAttr;
      if (attr) el.setAttribute(attr, text);
      else el.innerHTML = text;
    });
  }

  document.querySelectorAll("[data-lang]").forEach(b => {
    const on = b.dataset.lang === lang;
    b.classList.toggle("on", on);
    b.setAttribute("aria-pressed", String(on));
    b.addEventListener("click", () => {
      if (b.dataset.lang === lang) return;
      try { localStorage.setItem("tp_lang", b.dataset.lang); } catch (e) {}
      location.reload();
    });
  });

  window.TL_I18N = { lang, t, fmt };
})();
