(() => {
  const C = window.TL_CONFIG;
  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const KIND = { channel: "Канал", chat: "Чат", bot: "Бот" };
  const fmt = iso => new Date(iso).toLocaleDateString("ru-RU");
  const safe = u => (/^https:\/\/t\.me\/[A-Za-z0-9_]+$/.test(u) ? u : "#");

  async function api(path) {
    const r = await fetch(C.API + path);
    if (r.status === 404) return { notFound: true };
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }

  // ----- вкладки проекта -----
  const tabs = $("#tabs");
  if (tabs) {
    const names = ["about", "registry", "rules"];
    const botLink = $("#bot-link");
    if (botLink) botLink.href = C.BOT;
    const apply = () => {
      const name = names.includes(location.hash.slice(1)) ? location.hash.slice(1) : "about";
      names.forEach(n => { $("#tab-" + n).hidden = n !== name; });
      tabs.querySelectorAll("a").forEach(a => a.classList.toggle("on", a.dataset.tab === name));
      if (name === "registry" && !state.loaded) load(true);
    };

    // ----- реестр -----
    const state = { loaded: false, offset: 0, limit: 20, total: 0 };
    const body = $("#reg-body"), more = $("#more"), q = $("#q"), kind = $("#kind");

    const row = r => `
      <a class="reg-row" role="listitem" href="/registry/${esc(r.id)}">
        <span class="t">${esc(r.title)}<small>${esc(r.link.replace("https://", ""))}</small></span>
        <span>${esc(KIND[r.kind] || r.kind)}</span>
        <span>${esc(r.purpose)}</span>
        <span>${fmt(r.approved_at)}</span>
        <span class="lic">${esc(r.id)}</span>
      </a>`;

    async function load(reset) {
      if (reset) { state.offset = 0; body.innerHTML = '<div class="empty">Загрузка реестра…</div>'; }
      const p = new URLSearchParams({ limit: state.limit, offset: state.offset });
      if (q.value.trim()) p.set("q", q.value.trim());
      if (kind.value) p.set("kind", kind.value);
      try {
        const data = await api("/api/registry?" + p);
        state.loaded = true;
        state.total = data.total;
        const html = data.items.map(row).join("");
        if (reset) body.innerHTML = html || '<div class="empty">Ресурсы не найдены. Измените запрос или фильтр.</div>';
        else body.insertAdjacentHTML("beforeend", html);
        state.offset += data.items.length;
        more.hidden = state.offset >= state.total;
      } catch (e) {
        more.hidden = true;
        body.innerHTML = '<div class="empty">Реестр временно недоступен. Повторите попытку через минуту.</div>';
      }
    }

    let timer;
    q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => load(true), 300); });
    kind.addEventListener("change", () => load(true));
    more.addEventListener("click", () => load(false));
    window.addEventListener("hashchange", apply);
    apply();
  }

  // ----- страница ресурса -----
  const detail = $("#detail");
  if (detail) {
    const id = decodeURIComponent(location.pathname.split("/").pop() || "");
    const num = id.replace(/^TL-/i, "");
    const card = inner => (detail.innerHTML = `<div class="card">${inner}</div>`);
    const back = '<p><a href="/tele-license#registry">Вернуться к реестру</a></p>';

    (async () => {
      if (!/^\d+$/.test(num)) return card("<h2>Лицензия не найдена</h2><p>Проверьте номер лицензии.</p>" + back);
      try {
        const r = await api("/api/registry/" + num);
        if (r.notFound) return card("<h2>Лицензия не найдена</h2><p>Ресурса с таким номером нет в реестре.</p>" + back);
        document.title = `${r.title} — лицензия ${r.id}`;
        const ok = r.active;
        card(`
          <span class="badge ${ok ? "ok" : "bad"}">${ok ? "Лицензия действительна" : "Лицензия недействительна"}</span>
          <h1 style="margin-top:14px">${esc(r.title)}</h1>
          <p style="color:var(--muted)">${ok
            ? "Ресурс находится в реестре безопасных ресурсов Tele License."
            : "Ресурс исключён из реестра " + fmt(r.revoked_at) + ". Подтверждение не действует."}</p>
          <dl>
            <dt>Номер лицензии</dt><dd class="lic">${esc(r.id)}</dd>
            <dt>Тип</dt><dd>${esc(KIND[r.kind] || r.kind)}</dd>
            <dt>Ссылка</dt><dd>${ok ? `<a href="${esc(safe(r.link))}" rel="noopener noreferrer">${esc(r.link.replace("https://", ""))}</a>` : esc(r.link.replace("https://", ""))}</dd>
            <dt>Тематика</dt><dd>${esc(r.purpose)}</dd>
            <dt>Страны</dt><dd>${esc(r.countries)}</dd>
            <dt>Языки</dt><dd>${esc(r.languages)}</dd>
            <dt>Дата подтверждения</dt><dd>${fmt(r.approved_at)}</dd>
          </dl>
          <div class="actions" style="margin-top:8px">
            ${ok ? `<a class="btn btn-dark" href="${esc(safe(r.link))}" rel="noopener noreferrer">Перейти к ресурсу</a>
            <a class="btn btn-line" href="${esc(C.BOT)}?start=v_${r.num}" rel="noopener noreferrer">Подать жалобу в боте</a>` : ""}
            <a class="btn btn-line" href="/tele-license#registry">Весь реестр</a>
          </div>`);
      } catch (e) {
        card("<h2>Не удалось загрузить данные</h2><p>Сервис проверки временно недоступен. Повторите попытку через минуту.</p>" + back);
      }
    })();
  }
})();
