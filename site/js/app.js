(() => {
  const C = window.TL_CONFIG;
  const { t, fmt } = window.TL_I18N;
  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const PURPOSES = ["news", "sports", "tech", "finance", "education", "entertainment", "games", "services", "community"];
  const kind = k => ["channel", "chat", "bot"].includes(k) ? t("kind_" + k) : k;
  const purpose = v => PURPOSES.includes(v) ? t("p_" + v) : v;
  const countries = v => v === "all" ? t("all_countries") : v;
  const languages = v => v === "all" ? t("all_languages") : v;
  const safe = u => (/^https:\/\/t\.me\/[A-Za-z0-9_]+$/.test(u) ? u : "#");

  async function api(path) {
    const r = await fetch(C.API + path);
    if (r.status === 404) return { notFound: true };
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }

  // ----- скрытый вход в админ-панель: 10 нажатий на значок в шапке -----
  const mark = $(".brand .mark");
  if (mark) {
    let taps = 0, timer;
    const openAdmin = () => {
      if (window.TP_ADMIN) return window.TP_ADMIN.open();
      const s = document.createElement("script");
      s.src = "/js/admin.js";
      s.onload = () => window.TP_ADMIN.open();
      document.head.appendChild(s);
    };
    mark.addEventListener("click", e => {
      e.preventDefault();
      clearTimeout(timer);
      if (++taps >= 10) { taps = 0; openAdmin(); return; }
      // одиночное нажатие по-прежнему ведёт на главную
      timer = setTimeout(() => { if (taps === 1) location.href = "/"; taps = 0; }, 700);
    });
  }

  // ----- вкладки проекта -----
  const tabs = $("#tabs");
  if (tabs) {
    const names = ["about", "registry", "auction", "rules"];
    for (const id of ["#bot-link", "#bot-link-au"]) { const el = $(id); if (el) el.href = C.BOT; }
    const state = { loaded: false, offset: 0, limit: 20, total: 0 };
    const body = $("#reg-body"), more = $("#more"), q = $("#q"), kindSel = $("#kind");

    const apply = () => {
      const name = names.includes(location.hash.slice(1)) ? location.hash.slice(1) : "about";
      names.forEach(n => { $("#tab-" + n).hidden = n !== name; });
      tabs.querySelectorAll("a").forEach(a => a.classList.toggle("on", a.dataset.tab === name));
      if (name === "registry" && !state.loaded) load(true);
      if (name === "auction") startAuction(); else stopAuction();
    };

    // ----- аукцион номеров -----
    const aBody = $("#au-body");
    const au = { loaded: false, timer: null };
    const leftTxt = iso => {
      let s = Math.max(Math.floor((new Date(iso) - Date.now()) / 1000), 0);
      const d = Math.floor(s / 86400); s %= 86400;
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
      return d ? t("au_left_dh", { d, h }) : t("au_left_hm", { h, m });
    };
    const auRow = a => {
      const closing = a.status === "active" && new Date(a.ends_at) <= Date.now();
      const st = a.status === "sold" ? "sold" : closing ? "closing" : a.status;
      const badge = `<span class="badge ${st === "sold" ? "bad" : st === "idle" ? "" : "ok"}">${esc(t("au_st_" + st))}</span>`;
      const price = a.status === "idle" ? `${a.price} ⭐ · ${esc(t("au_start"))}` : `${a.price} ⭐`;
      const time = a.status === "active" && !closing ? esc(leftTxt(a.ends_at)) : "—";
      const action = a.status === "sold" ? "" :
        `<a class="btn btn-line btn-sm" href="${esc(C.BOT)}?start=a_${a.num}" rel="noopener noreferrer">${esc(t("au_bid"))}</a>`;
      return `<div class="au-row" role="listitem"><span class="lic">${esc(a.id)}</span><span>${badge}</span><span>${price}</span><span>${time}</span><span>${action}</span></div>`;
    };
    async function loadAuction() {
      try {
        const data = await api("/api/auctions");
        au.loaded = true;
        aBody.innerHTML = data.items.map(auRow).join("");
      } catch (e) {
        if (!au.loaded) aBody.innerHTML = `<div class="empty">${esc(t("au_error"))}</div>`;
      }
    }
    function startAuction() {
      if (au.timer) return;
      if (!au.loaded) aBody.innerHTML = `<div class="empty">${esc(t("au_loading"))}</div>`;
      loadAuction();
      au.timer = setInterval(loadAuction, 60000);
    }
    function stopAuction() { clearInterval(au.timer); au.timer = null; }

    const row = r => `
      <a class="reg-row" role="listitem" href="/registry/${esc(r.id)}">
        <span class="t">${esc(r.title)}<small>${esc(r.link.replace("https://", ""))}</small></span>
        <span>${esc(kind(r.kind))}</span>
        <span>${esc(purpose(r.purpose))}</span>
        <span>${fmt(r.approved_at)}</span>
        <span class="lic">${esc(r.id)}</span>
      </a>`;

    async function load(reset) {
      if (reset) { state.offset = 0; body.innerHTML = `<div class="empty">${esc(t("reg_loading"))}</div>`; }
      const p = new URLSearchParams({ limit: state.limit, offset: state.offset });
      if (q.value.trim()) p.set("q", q.value.trim());
      if (kindSel.value) p.set("kind", kindSel.value);
      try {
        const data = await api("/api/registry?" + p);
        state.loaded = true;
        state.total = data.total;
        const html = data.items.map(row).join("");
        if (reset) body.innerHTML = html || `<div class="empty">${esc(t("reg_empty"))}</div>`;
        else body.insertAdjacentHTML("beforeend", html);
        state.offset += data.items.length;
        more.hidden = state.offset >= state.total;
      } catch (e) {
        more.hidden = true;
        body.innerHTML = `<div class="empty">${esc(t("reg_error"))}</div>`;
      }
    }

    let timer;
    q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => load(true), 300); });
    kindSel.addEventListener("change", () => load(true));
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
    const back = `<p><a href="/tele-license#registry">${esc(t("res_back"))}</a></p>`;

    (async () => {
      if (!/^\d+$/.test(num)) return card(`<h2>${esc(t("res_nf_title"))}</h2><p>${esc(t("res_nf_bad"))}</p>` + back);
      try {
        const r = await api("/api/registry/" + num);
        if (r.notFound) return card(`<h2>${esc(t("res_nf_title"))}</h2><p>${esc(t("res_nf_text"))}</p>` + back);
        document.title = t("doc_title", { title: r.title, id: r.id });
        if (r.id !== id.toUpperCase()) history.replaceState(null, "", "/registry/" + r.id);
        const ok = r.active;
        card(`
          <span class="badge ${ok ? "ok" : "bad"}">${esc(t(ok ? "res_ok" : "res_bad"))}</span>
          <h1>${esc(r.title)}</h1>
          <p style="color:var(--muted)">${esc(ok ? t("res_ok_text") : t("res_bad_text", { date: fmt(r.revoked_at) }))}</p>
          <dl>
            <dt>${esc(t("dt_lic"))}</dt><dd class="lic">${esc(r.id)}</dd>
            <dt>${esc(t("dt_type"))}</dt><dd>${esc(kind(r.kind))}</dd>
            <dt>${esc(t("dt_addr"))}</dt><dd>${esc(r.link.replace("https://", ""))}</dd>
            <dt>${esc(t("dt_topic"))}</dt><dd>${esc(purpose(r.purpose))}</dd>
            <dt>${esc(t("dt_countries"))}</dt><dd>${esc(countries(r.countries))}</dd>
            <dt>${esc(t("dt_langs"))}</dt><dd>${esc(languages(r.languages))}</dd>
            <dt>${esc(t("dt_date"))}</dt><dd>${fmt(r.approved_at)}</dd>
          </dl>
          <div class="actions" style="margin-top:8px">
            ${ok ? `<a class="btn btn-dark" href="${esc(safe(r.link))}" rel="noopener noreferrer">${esc(t("btn_go"))}</a>
            <a class="btn btn-line" href="${esc(C.BOT)}?start=v_${r.num}" rel="noopener noreferrer">${esc(t("btn_report"))}</a>` : ""}
            <a class="btn btn-line" href="/tele-license#registry">${esc(t("btn_all"))}</a>
          </div>`);
      } catch (e) {
        card(`<h2>${esc(t("res_err_title"))}</h2><p>${esc(t("res_err_text"))}</p>` + back);
      }
    })();
  }
})();
