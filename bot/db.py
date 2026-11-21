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
    registry_id INT NOT NULL REFERENCES registry(id),
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
CREATE INDEX IF NOT EXISTS idx_registry_active ON registry (active, approved_at DESC);
"""


async def init() -> None:
    global pool
    # statement_cache_size=0 — совместимость с pgbouncer (Supabase pooler)
    pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=5, statement_cache_size=0)
    await pool.execute(SCHEMA)


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
            return await c.fetchrow(
                """INSERT INTO registry (application_id,user_id,kind,title,username,purpose,countries,languages)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *""",
                app["id"], app["user_id"], app["kind"], app["title"], app["username"],
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
    return await pool.fetchrow("SELECT * FROM registry WHERE id=$1", reg_id)


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
