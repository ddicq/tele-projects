// Админ-панель. Код доступа проверяет сервер (бот на Render), здесь секретов нет.
(() => {
  const C = window.TL_CONFIG;
  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let token = null;
  try { token = sessionStorage.getItem("tp_adm"); } catch (e) {}
  let root = null, pollTimer = null;

  async function call(path, { method = "GET", json, form } = {}) {
    const headers = {};
    if (token) headers.Authorization = "Bearer " + token;
    let body;
    if (json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
    if (form) body = form;
    const r = await fetch(C.API + path, { method, headers, body });
    let data = {};
    try { data = await r.json(); } catch (e) {}
    if (r.status === 401 && token) { setToken(null); showLogin("Сессия истекла. Введите код снова."); }
    if (!r.ok) throw new Error(data.error || "Ошибка " + r.status);
    return data;
  }

  function setToken(t) {
    token = t;
    try { t ? sessionStorage.setItem("tp_adm", t) : sessionStorage.removeItem("tp_adm"); } catch (e) {}
  }

  function close() {
    clearInterval(pollTimer);
    if (root) { root.remove(); root = null; }
    document.body.style.overflow = "";
  }

  function mount(html) {
    close();
    root = document.createElement("div");
    root.className = "adm-overlay";
    root.innerHTML = html;
    document.body.appendChild(root);
    document.body.style.overflow = "hidden";
    root.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
    return root;
  }

  // ---------- вход ----------
  function showLogin(msg) {
    mount(`<form class="adm-login" autocomplete="off">
      <h3>Доступ</h3>
      <input id="adm-code" type="password" inputmode="numeric" autocomplete="off" placeholder="Код" required>
      <div class="adm-msg" id="adm-msg">${esc(msg || "")}</div>
      <div class="adm-actions"><button type="button" class="btn btn-line btn-sm" data-close>Отмена</button><button class="btn btn-dark btn-sm">Войти</button></div>
    </form>`);
    const form = $("form", root), msgEl = $("#adm-msg", root);
    $("[data-close]", root).onclick = close;
    $("#adm-code", root).focus();
    form.addEventListener("submit", async e => {
      e.preventDefault();
      msgEl.textContent = "";
      try {
        const data = await call("/api/admin/login", { method: "POST", json: { code: $("#adm-code", root).value } });
        setToken(data.token);
        showPanel();
      } catch (err) { msgEl.textContent = err.message; $("#adm-code", root).value = ""; }
    });
  }

  // ---------- каркас панели ----------
  function showPanel() {
    mount(`<div class="adm-box">
      <div class="adm-top"><b>Админ-панель</b>
        <span><button class="btn btn-line btn-sm" id="adm-out">Выйти</button> <button class="btn btn-dark btn-sm" data-close>Закрыть</button></span></div>
      <div class="adm-tabs"><button class="on" data-tab="user">Пользователи</button><button data-tab="bc">Рассылка</button></div>
      <div id="adm-body"></div></div>`);
    $("[data-close]", root).onclick = close;
    $("#adm-out", root).onclick = async () => { try { await call("/api/admin/logout", { method: "POST" }); } catch (e) {} setToken(null); close(); };
    const tabs = root.querySelectorAll(".adm-tabs button");
    const open = name => {
      tabs.forEach(b => b.classList.toggle("on", b.dataset.tab === name));
      clearInterval(pollTimer);
      (name === "bc" ? broadcastTab : userTab)($("#adm-body", root));
    };
    tabs.forEach(b => b.onclick = () => open(b.dataset.tab));
    open("user");
  }

  const note = (el, text, ok) => { el.className = "adm-msg " + (ok ? "ok" : ""); el.textContent = text; };

  // ---------- вкладка: пользователи ----------
  function userTab(el) {
    el.innerHTML = `<div class="adm-row"><input id="u-id" inputmode="numeric" placeholder="Telegram ID пользователя"><button class="btn btn-dark btn-sm" id="u-find">Найти</button></div>
      <div class="adm-msg" id="u-msg"></div><div id="u-out"></div>`;
    const input = $("#u-id", el), msg = $("#u-msg", el), out = $("#u-out", el);
    let currentId = null;

    async function load(id) {
      note(msg, "");
      try {
        const d = await call("/api/admin/user?id=" + encodeURIComponent(id));
        currentId = d.id;
        out.innerHTML = render(d);
      } catch (e) { out.innerHTML = ""; note(msg, e.message); }
    }

    function render(d) {
      const rows = d.resources.length ? d.resources.map(r => `<tr>
          <td class="lic">${esc(r.id)}${r.special ? " ★" : ""}</td>
          <td>${esc(r.title)}<small>${esc(r.link.replace("https://", ""))}</small></td>
          <td>${r.active ? "действует" : "отозвана"}</td>
          <td class="adm-renum"><input type="number" min="1" max="999999" placeholder="Новый №"><button class="btn btn-line btn-sm" data-renum="${r.num}">Сменить</button></td></tr>`).join("")
        : `<tr><td colspan="4" class="adm-muted">Ресурсов нет</td></tr>`;
      const nums = d.numbers.length ? d.numbers.map(n => `${esc(n.id)} (${n.price} ⭐, ${n.assigned ? "присвоен" : "свободен"})`).join(", ") : "—";
      const lead = d.leading.length ? d.leading.map(n => `${esc(n.id)} (${n.price} ⭐)`).join(", ") : "—";
      return `<div class="adm-card">
        <p><b>ID ${d.id}</b> · ${d.known ? "язык: " + esc(d.lang) : "в базе бота не найден"} ·
          <span class="badge ${d.banned ? "bad" : "ok"}">${d.banned ? "забанен" : "активен"}</span></p>
        <p class="adm-muted">Заявок: ${d.apps} · Потрачено на ставки: ${d.spent} ⭐</p>
        <h4>Ресурсы</h4>
        <div class="adm-scroll"><table class="adm-table"><tbody>${rows}</tbody></table></div>
        <p><b>Номера с аукциона:</b> ${nums}</p>
        <p><b>Лидирует в лотах:</b> ${lead}</p>
        <div class="adm-actions" style="justify-content:flex-start">
          ${d.banned ? `<button class="btn btn-dark btn-sm" data-act="unban">Разбанить</button>`
                     : `<button class="btn btn-dark btn-sm" data-act="ban">Забанить</button>`}
        </div>
        <h4>Сообщение пользователю</h4>
        <textarea id="u-text" rows="4" placeholder="Текст сообщения (поддерживается HTML-разметка Telegram)"></textarea>
        <div class="adm-actions" style="justify-content:flex-start"><button class="btn btn-primary btn-sm" data-act="send">Отправить</button></div>
      </div>`;
    }

    $("#u-find", el).onclick = () => input.value.trim() && load(input.value.trim());
    input.addEventListener("keydown", e => { if (e.key === "Enter") $("#u-find", el).click(); });

    out.addEventListener("click", async e => {
      const b = e.target.closest("button");
      if (!b || !currentId) return;
      try {
        if (b.dataset.renum) {
          const v = b.previousElementSibling.value;
          if (!v) return note(msg, "Введите новый номер");
          if (!confirm(`Сменить номер лицензии на TL-${String(v).padStart(5, "0")}? Владелец получит уведомление.`)) return;
          const r = await call("/api/admin/renumber", { method: "POST", json: { number: Number(b.dataset.renum), new_number: Number(v) } });
          await load(currentId); note(msg, "Номер изменён: " + r.id, true);
        } else if (b.dataset.act === "ban") {
          if (!confirm("Забанить пользователя? Его номера с аукциона вернутся на аукцион, звёзды не возвращаются.")) return;
          const r = await call("/api/admin/ban", { method: "POST", json: { user_id: currentId } });
          await load(currentId); note(msg, r.released.length ? "Забанен. Номера вернулись на аукцион: " + r.released.join(", ") : "Забанен", true);
        } else if (b.dataset.act === "unban") {
          await call("/api/admin/unban", { method: "POST", json: { user_id: currentId } });
          await load(currentId); note(msg, "Разбанен", true);
        } else if (b.dataset.act === "send") {
          const text = $("#u-text", out).value.trim();
          if (!text) return note(msg, "Введите текст");
          await call("/api/admin/message", { method: "POST", json: { user_id: currentId, text } });
          $("#u-text", out).value = ""; note(msg, "Сообщение отправлено", true);
        }
      } catch (err) { note(msg, err.message); }
    });
  }

  // ---------- вкладка: рассылка ----------
  function broadcastTab(el) {
    const buttons = [];
    el.innerHTML = `<div class="adm-card">
      <label>Аудитория
        <select id="bc-aud"><option value="all">Все пользователи бота</option><option value="ru">Только русский язык</option><option value="en">Только английский язык</option></select></label>
      <div class="adm-tools">
        <button data-tag="b"><b>B</b></button><button data-tag="i"><i>I</i></button><button data-tag="u"><u>U</u></button>
        <button data-tag="s"><s>S</s></button><button data-tag="tg-spoiler">Спойлер</button><button data-tag="code">Код</button>
        <button data-tag="blockquote">Цитата</button><button data-tag="a">Ссылка</button><button data-tag="emoji">Premium-эмодзи</button>
      </div>
      <textarea id="bc-text" rows="8" placeholder="Текст рассылки. Форматирование — HTML-разметка Telegram (кнопки выше оборачивают выделенный текст)"></textarea>
      <p class="adm-muted">Premium-эмодзи вставляются как &lt;tg-emoji emoji-id="ID"&gt;🙂&lt;/tg-emoji&gt; и работают, только если у бота есть такая возможность в Telegram.</p>
      <label>Фото или видео (до 50 МБ)<input type="file" id="bc-media" accept="image/*,video/*"></label>
      <h4>Кнопки под сообщением</h4>
      <div id="bc-buttons"></div>
      <button class="btn btn-line btn-sm" id="bc-add" type="button">+ Добавить кнопку</button>
      <div class="adm-msg" id="bc-msg"></div>
      <div class="adm-row" style="margin-top:14px">
        <input id="bc-test" inputmode="numeric" placeholder="Telegram ID для теста">
        <button class="btn btn-line btn-sm" id="bc-send-test">Отправить тест</button>
        <button class="btn btn-primary btn-sm" id="bc-send">Отправить рассылку</button>
      </div>
      <div class="adm-msg" id="bc-status"></div>
    </div>`;
    const text = $("#bc-text", el), msg = $("#bc-msg", el), status = $("#bc-status", el), list = $("#bc-buttons", el);

    // форматирование
    el.querySelectorAll("[data-tag]").forEach(b => b.onclick = () => {
      const tag = b.dataset.tag, a = text.selectionStart, z = text.selectionEnd, sel = text.value.slice(a, z);
      let open, closeTag;
      if (tag === "a") {
        const url = prompt("Адрес ссылки (https://…)");
        if (!url) return;
        open = `<a href="${url.replace(/"/g, "&quot;")}">`; closeTag = "</a>";
      } else if (tag === "emoji") {
        const id = prompt("ID премиум-эмодзи (число)");
        if (!id || !/^\d+$/.test(id)) return;
        const fb = prompt("Обычный эмодзи на случай, если премиум не отобразится", "🙂") || "🙂";
        open = `<tg-emoji emoji-id="${id}">${fb}`; closeTag = "</tg-emoji>";
        text.setRangeText(open + closeTag, a, z, "end"); text.focus(); return;
      } else { open = `<${tag}>`; closeTag = `</${tag}>`; }
      text.setRangeText(open + sel + closeTag, a, z, "end");
      text.focus();
    });

    // кнопки
    function drawButtons() {
      list.innerHTML = buttons.map((b, i) => `<div class="adm-btnrow">
        <input data-f="text" data-i="${i}" placeholder="Текст кнопки" value="${esc(b.text)}">
        <select data-f="type" data-i="${i}"><option value="url" ${b.type === "url" ? "selected" : ""}>Ссылка</option><option value="action" ${b.type === "action" ? "selected" : ""}>Действие бота</option></select>
        ${b.type === "url"
          ? `<input data-f="value" data-i="${i}" placeholder="https://…" value="${esc(b.value)}">`
          : `<select data-f="value" data-i="${i}">${[["apply", "Подать заявку"], ["auction", "Аукцион номеров"], ["numbers", "Мои номера"], ["rules", "Правила"], ["menu", "Главное меню"]]
              .map(([v, l]) => `<option value="${v}" ${b.value === v ? "selected" : ""}>${l}</option>`).join("")}</select>`}
        <button class="btn btn-line btn-sm" data-del="${i}" type="button">×</button></div>`).join("");
    }
    $("#bc-add", el).onclick = () => { buttons.push({ text: "", type: "url", value: "" }); drawButtons(); };
    list.addEventListener("input", e => { const t = e.target, i = t.dataset.i; if (i !== undefined) buttons[i][t.dataset.f] = t.value; });
    list.addEventListener("change", e => {
      const t = e.target, i = t.dataset.i;
      if (i === undefined) return;
      buttons[i][t.dataset.f] = t.value;
      if (t.dataset.f === "type") { buttons[i].value = t.value === "action" ? "apply" : ""; drawButtons(); }
    });
    list.addEventListener("click", e => { const d = e.target.closest("[data-del]"); if (d) { buttons.splice(+d.dataset.del, 1); drawButtons(); } });

    function form(audience, testId) {
      const f = new FormData();
      f.append("payload", JSON.stringify({
        audience, test_id: testId, text: text.value,
        buttons: buttons.filter(b => b.text.trim()).map(b => b.type === "url" ? { text: b.text, url: b.value } : { text: b.text, action: b.value })
      }));
      const file = $("#bc-media", el).files[0];
      if (file) f.append("media", file, file.name);
      return f;
    }

    $("#bc-send-test", el).onclick = async () => {
      const id = $("#bc-test", el).value.trim();
      if (!id) return note(msg, "Укажите ID для теста");
      note(msg, "Отправляю тест…", true);
      try { await call("/api/admin/broadcast", { method: "POST", form: form("test", id) }); note(msg, "Тест отправлен", true); }
      catch (e) { note(msg, e.message); }
    };

    $("#bc-send", el).onclick = async () => {
      if (!text.value.trim() && !$("#bc-media", el).files[0]) return note(msg, "Добавьте текст или медиа");
      if (!confirm("Отправить рассылку всей выбранной аудитории? Отменить её будет нельзя.")) return;
      note(msg, "Запускаю…", true);
      try {
        const r = await call("/api/admin/broadcast", { method: "POST", form: form($("#bc-aud", el).value) });
        note(msg, `Рассылка запущена, получателей: ${r.total}`, true);
        clearInterval(pollTimer);
        pollTimer = setInterval(async () => {
          try {
            const s = await call("/api/admin/broadcast/" + r.job);
            note(status, `Отправлено ${s.sent} из ${s.total} · ошибок: ${s.failed} · заблокировали бота: ${s.blocked}` +
              (s.state === "done" ? " · готово" : s.state === "aborted" ? " · " + s.error : ""), s.state !== "aborted");
            if (s.state !== "running") clearInterval(pollTimer);
          } catch (e) { clearInterval(pollTimer); }
        }, 2000);
      } catch (e) { note(msg, e.message); }
    };
  }

  window.TP_ADMIN = { open: () => (token ? showPanel() : showLogin()) };
})();
