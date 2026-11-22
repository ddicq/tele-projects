import asyncpg

import config

pool: asyncpg.Pool | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id            SERIAL PRIMARY KEY,
    user_id       BIGINT NOT NULL,
    user_tag      TEXT,
    kind          TEXT NOT NULL,
    title         TEXT NOT NULL,
    username      TEXT NOT NULL,
    purpose       TEXT NOT NULL,
    countries     TEXT NOT NULL,
    languages     TEXT NOT NULL,
    members       INT,
    owner_status  TEXT NOT NULL DEFAULT 'unverified',
    status        TEXT NOT NULL DEFAULT 'pending',
    reject_reason TEXT,
    mod_msg_id    BIGINT,
    decided_by    BIGINT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at    TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS registry (
    id             SERIAL PRIMARY KEY,
    application_id INT UNIQUE REFERENCES applications(id),
    user_id        BIGINT NOT NULL,
    kind           TEXT NOT NULL,
    title          TEXT NOT NULL,
    username       TEXT NOT NULL,
    purpose        TEXT NOT NULL,
    countries      TEXT NOT NULL,
    languages      TEXT NOT NULL,
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    approved_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at     TIMESTAMPTZ,
    revoke_reason  TEXT
);
CREATE TABLE IF NOT EXISTS complaints (
    id          SERIAL PRIMARY KEY,
    registry_id INT NOT NULL REFERENCES registry(id) ON UPDATE CASCADE,
    user_id     BIGINT NOT NULL,
    reason      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',
    mod_msg_id  BIGINT,
    decided_by  BIGINT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at  TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS pending_actions (
    chat_id       BIGINT NOT NULL,
    prompt_msg_id BIGINT NOT NULL,
    action        TEXT NOT NULL,
    target_id     INT NOT NULL,
    mod_id        BIGINT NOT NULL,
    PRIMARY KEY (chat_id, prompt_msg_id)
);
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    lang    TEXT NOT NULL DEFAULT 'ru'
);
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE TABLE IF NOT EXISTS auctions (
    number       INT PRIMARY KEY,
    start_price  INT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'idle',
    top_user_id  BIGINT,
    top_amount   INT,
    started_at   TIMESTAMPTZ,
    ends_at      TIMESTAMPTZ,
    winner_id    BIGINT,
    final_amount INT,
    sold_at      TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS auction_bids (
    id         SERIAL PRIMARY KEY,
    number     INT NOT NULL REFERENCES auctions(number),
    user_id    BIGINT NOT NULL,
    amount     INT NOT NULL,
    charge_id  TEXT NOT NULL UNIQUE,
    status     TEXT NOT NULL DEFAULT 'leading',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bids_number ON auction_bids (number, status);
CREATE TABLE IF NOT EXISTS license_aliases (
    old_number INT PRIMARY KEY,
    new_number INT NOT NULL
);
ALTER TABLE auctions ENABLE ROW LEVEL SECURITY;
ALTER TABLE auction_bids ENABLE ROW LEVEL SECURITY;
ALTER TABLE license_aliases ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS idx_registry_active ON registry (active, approved_at DESC);
"""


async def init() -> None:
    global pool
    # statement_cache_size=0 — совместимость с pgbouncer (Supabase pooler)
    pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=5, statement_cache_size=0)
    await pool.execute(SCHEMA)
    await pool.executemany(
        "INSERT INTO auctions (number, start_price) VALUES ($1,$2) ON CONFLICT (number) DO NOTHING",
        list(config.AUCTION_LOTS.items()),
    )


# ---------- заявки ----------
async def username_taken(username: str) -> bool:
    row = await pool.fetchval(
        """SELECT 1 FROM applications WHERE lower(username)=lower($1) AND status='pending'
           UNION ALL
           SELECT 1 FROM registry WHERE lower(username)=lower($1) AND active
           LIMIT 1""",
        username,
    )
    return bool(row)


async def create_application(user_id, user_tag, kind, title, username, purpose, countries, languages, members, owner_status):
    return await pool.fetchrow(
        """INSERT INTO applications (user_id,user_tag,kind,title,username,purpose,countries,languages,members,owner_status)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING *""",
        user_id, user_tag, kind, title, username, purpose, countries, languages, members, owner_status,
    )


async def set_mod_msg(app_id: int, msg_id: int) -> None:
    await pool.execute("UPDATE applications SET mod_msg_id=$2 WHERE id=$1", app_id, msg_id)


async def get_application(app_id: int):
    return await pool.fetchrow("SELECT * FROM applications WHERE id=$1", app_id)


async def _next_license_id(c) -> int:
    """Следующий обычный номер: пропускает номера аукциона, занятые и ранее использованные."""
    while True:
        n = await c.fetchval("SELECT nextval(pg_get_serial_sequence('registry','id'))")
        taken = await c.fetchval(
            """SELECT 1 FROM auctions WHERE number=$1
               UNION ALL SELECT 1 FROM registry WHERE id=$1
               UNION ALL SELECT 1 FROM license_aliases WHERE old_number=$1 LIMIT 1""", n)
        if not taken:
            return n


async def approve_application(app_id: int, mod_id: int):
    """Атомарно одобряет заявку и создаёт запись в реестре. None — если заявка уже обработана."""
    async with pool.acquire() as c:
        async with c.transaction():
            app = await c.fetchrow(
                """UPDATE applications SET status='approved', decided_by=$2, decided_at=now()
                   WHERE id=$1 AND status='pending' RETURNING *""",
                app_id, mod_id,
            )
            if not app:
                return None
            new_id = await _next_license_id(c)
            return await c.fetchrow(
                """INSERT INTO registry (id,application_id,user_id,kind,title,username,purpose,countries,languages)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *""",
                new_id, app["id"], app["user_id"], app["kind"], app["title"], app["username"],
                app["purpose"], app["countries"], app["languages"],
            )


async def reject_application(app_id: int, reason: str, mod_id: int):
    return await pool.fetchrow(
        """UPDATE applications SET status='rejected', reject_reason=$2, decided_by=$3, decided_at=now()
           WHERE id=$1 AND status='pending' RETURNING *""",
        app_id, reason, mod_id,
    )


async def user_applications(user_id: int, limit: int = 15):
    return await pool.fetch(
        """SELECT a.*, r.id AS reg_id, r.active AS reg_active
           FROM applications a LEFT JOIN registry r ON r.application_id = a.id
           WHERE a.user_id=$1 ORDER BY a.id DESC LIMIT $2""",
        user_id, limit,
    )


# ---------- реестр ----------
async def get_registry(reg_id: int):
    """Лицензия по номеру. Если номер был заменён на номер с аукциона — возвращает актуальную запись."""
    row = await pool.fetchrow("SELECT * FROM registry WHERE id=$1", reg_id)
    if row:
        return row
    return await pool.fetchrow(
        "SELECT r.* FROM license_aliases a JOIN registry r ON r.id = a.new_number WHERE a.old_number=$1", reg_id)


async def list_registry(q: str | None, kind: str | None, limit: int, offset: int):
    rows = await pool.fetch(
        """SELECT *, count(*) OVER() AS total FROM registry
           WHERE active
             AND ($1::text IS NULL OR kind = $1)
             AND ($2::text IS NULL
                  OR strpos(lower(title), lower($2)) > 0
                  OR strpos(lower(username), lower($2)) > 0
                  OR strpos(lower(purpose), lower($2)) > 0)
           ORDER BY approved_at DESC LIMIT $3 OFFSET $4""",
        kind, q, limit, offset,
    )
    total = rows[0]["total"] if rows else 0
    return rows, total


async def revoke_registry(reg_id: int, reason: str):
    return await pool.fetchrow(
        """UPDATE registry SET active=FALSE, revoked_at=now(), revoke_reason=$2
           WHERE id=$1 AND active RETURNING *""",
        reg_id, reason,
    )


# ---------- жалобы ----------
async def open_complaint_exists(reg_id: int, user_id: int) -> bool:
    return bool(await pool.fetchval(
        "SELECT 1 FROM complaints WHERE registry_id=$1 AND user_id=$2 AND status='open'", reg_id, user_id))


async def create_complaint(reg_id: int, user_id: int, reason: str):
    return await pool.fetchrow(
        "INSERT INTO complaints (registry_id,user_id,reason) VALUES ($1,$2,$3) RETURNING *",
        reg_id, user_id, reason,
    )


async def set_complaint_msg(complaint_id: int, msg_id: int) -> None:
    await pool.execute("UPDATE complaints SET mod_msg_id=$2 WHERE id=$1", complaint_id, msg_id)


async def get_complaint(complaint_id: int):
    return await pool.fetchrow("SELECT * FROM complaints WHERE id=$1", complaint_id)


async def resolve_complaint(complaint_id: int, status: str, mod_id: int):
    return await pool.fetchrow(
        """UPDATE complaints SET status=$2, decided_by=$3, decided_at=now()
           WHERE id=$1 AND status='open' RETURNING *""",
        complaint_id, status, mod_id,
    )


async def close_open_complaints(reg_id: int, status: str, mod_id: int):
    return await pool.fetch(
        """UPDATE complaints SET status=$2, decided_by=$3, decided_at=now()
           WHERE registry_id=$1 AND status='open' RETURNING *""",
        reg_id, status, mod_id,
    )


# ---------- ожидание ответа модератора ----------
async def add_pending(chat_id: int, prompt_msg_id: int, action: str, target_id: int, mod_id: int) -> None:
    await pool.execute(
        """INSERT INTO pending_actions (chat_id,prompt_msg_id,action,target_id,mod_id)
           VALUES ($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING""",
        chat_id, prompt_msg_id, action, target_id, mod_id,
    )


async def get_pending(chat_id: int, prompt_msg_id: int):
    return await pool.fetchrow(
        "SELECT * FROM pending_actions WHERE chat_id=$1 AND prompt_msg_id=$2", chat_id, prompt_msg_id)


async def del_pending(chat_id: int, prompt_msg_id: int) -> None:
    await pool.execute("DELETE FROM pending_actions WHERE chat_id=$1 AND prompt_msg_id=$2", chat_id, prompt_msg_id)


# ---------- язык пользователей ----------
async def get_lang(user_id: int):
    return await pool.fetchval("SELECT lang FROM users WHERE user_id=$1", user_id)


async def set_lang(user_id: int, lang: str) -> None:
    await pool.execute(
        """INSERT INTO users (user_id, lang) VALUES ($1,$2)
           ON CONFLICT (user_id) DO UPDATE SET lang = EXCLUDED.lang""",
        user_id, lang,
    )


# ---------- аукцион номеров ----------
async def list_auctions():
    return await pool.fetch(
        """SELECT a.*, (SELECT count(*) FROM auction_bids b WHERE b.number = a.number) AS bids
           FROM auctions a ORDER BY a.number""")


async def get_auction(number: int):
    return await pool.fetchrow("SELECT * FROM auctions WHERE number=$1", number)


async def place_bid(number: int, user_id: int, amount: int, charge_id: str, step: int, days: int) -> dict:
    """Атомарно принимает оплаченную ставку. Возвращает {'status': ok|dup|ended|low|self|none, ...}."""
    async with pool.acquire() as c:
        async with c.transaction():
            a = await c.fetchrow("SELECT * FROM auctions WHERE number=$1 FOR UPDATE", number)
            if not a:
                return {"status": "none"}
            if await c.fetchval("SELECT 1 FROM auction_bids WHERE charge_id=$1", charge_id):
                return {"status": "dup"}
            now = await c.fetchval("SELECT now()")
            if a["status"] == "sold" or (a["status"] == "active" and a["ends_at"] <= now):
                return {"status": "ended"}
            if a["status"] == "active" and a["top_user_id"] == user_id:
                return {"status": "self"}
            min_amount = a["start_price"] if a["status"] == "idle" else a["top_amount"] + step
            if amount < min_amount:
                return {"status": "low", "min": min_amount}
            prev = None
            if a["status"] == "active":
                prev = await c.fetchrow(
                    "SELECT * FROM auction_bids WHERE number=$1 AND status='leading'", number)
                if prev:
                    await c.execute("UPDATE auction_bids SET status='outbid' WHERE id=$1", prev["id"])
            await c.execute(
                "INSERT INTO auction_bids (number,user_id,amount,charge_id,status) VALUES ($1,$2,$3,$4,'leading')",
                number, user_id, amount, charge_id)
            if a["status"] == "idle":
                a = await c.fetchrow(
                    """UPDATE auctions SET status='active', started_at=now(),
                              ends_at=now() + make_interval(days => $4), top_user_id=$2, top_amount=$3
                       WHERE number=$1 RETURNING *""", number, user_id, amount, days)
                return {"status": "ok", "prev": None, "ends_at": a["ends_at"], "first": True}
            a = await c.fetchrow(
                "UPDATE auctions SET top_user_id=$2, top_amount=$3 WHERE number=$1 RETURNING *",
                number, user_id, amount)
            return {"status": "ok", "prev": prev, "ends_at": a["ends_at"], "first": False}


async def set_bid_status(bid_id: int, status: str) -> None:
    await pool.execute("UPDATE auction_bids SET status=$2 WHERE id=$1", bid_id, status)


async def finish_due_auctions():
    """Завершает аукционы, у которых вышло время. Возвращает проданные лоты."""
    async with pool.acquire() as c:
        async with c.transaction():
            rows = await c.fetch(
                """UPDATE auctions SET status='sold', winner_id=top_user_id, final_amount=top_amount, sold_at=now()
                   WHERE status='active' AND ends_at <= now() RETURNING *""")
            for r in rows:
                await c.execute("UPDATE auction_bids SET status='won' WHERE number=$1 AND status='leading'", r["number"])
            return rows


async def user_numbers(user_id: int):
    return await pool.fetch(
        """SELECT a.*, r.title AS assigned_title, (r.id IS NOT NULL) AS assigned
           FROM auctions a LEFT JOIN registry r ON r.id = a.number
           WHERE a.winner_id=$1 AND a.status='sold' ORDER BY a.number""", user_id)


async def eligible_resources(user_id: int):
    """Действующие ресурсы пользователя с обычным номером."""
    return await pool.fetch(
        """SELECT * FROM registry r
           WHERE r.user_id=$1 AND r.active AND NOT EXISTS (SELECT 1 FROM auctions a WHERE a.number = r.id)
           ORDER BY r.id""", user_id)


async def assign_number(number: int, user_id: int, reg_id: int) -> dict:
    """Присваивает купленный номер ресурсу: меняет номер в реестре, старый номер остаётся ссылкой-перенаправлением."""
    async with pool.acquire() as c:
        async with c.transaction():
            a = await c.fetchrow(
                "SELECT * FROM auctions WHERE number=$1 AND winner_id=$2 AND status='sold' FOR UPDATE", number, user_id)
            if not a or await c.fetchval("SELECT 1 FROM registry WHERE id=$1", number):
                return {"status": "fail"}
            r = await c.fetchrow("SELECT * FROM registry WHERE id=$1 AND user_id=$2 AND active FOR UPDATE", reg_id, user_id)
            if not r or await c.fetchval("SELECT 1 FROM auctions WHERE number=$1", r["id"]):
                return {"status": "fail"}
            old = r["id"]
            await c.execute("UPDATE registry SET id=$1 WHERE id=$2", number, old)  # жалобы переедут каскадом
            await c.execute("UPDATE license_aliases SET new_number=$1 WHERE new_number=$2", number, old)
            await c.execute(
                """INSERT INTO license_aliases (old_number,new_number) VALUES ($1,$2)
                   ON CONFLICT (old_number) DO UPDATE SET new_number = EXCLUDED.new_number""", old, number)
            return {"status": "ok", "old": old, "title": r["title"]}
