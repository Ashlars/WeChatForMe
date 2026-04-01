from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from loguru import logger

from src.models.schemas import Contact, Group, Message, MessageDirection, TriggerMode


class ContextManager:
    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                msg_id TEXT UNIQUE,
                contact_id TEXT NOT NULL,
                group_id TEXT,
                direction TEXT NOT NULL,
                content TEXT NOT NULL,
                msg_type TEXT DEFAULT 'text',
                agent_model TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_messages_group ON messages(group_id, created_at);
            CREATE TABLE IF NOT EXISTS contacts (
                wxid TEXT PRIMARY KEY,
                nickname TEXT,
                remark TEXT,
                relationship TEXT,
                chat_prefs TEXT,
                is_whitelist BOOLEAN DEFAULT 0,
                is_paused BOOLEAN DEFAULT 0,
                last_interaction DATETIME,
                persona_summary TEXT,
                style_summary TEXT,
                interaction_style_summary TEXT,
                last_analysis_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS groups (
                group_id TEXT PRIMARY KEY,
                group_name TEXT,
                is_active BOOLEAN DEFAULT 0,
                trigger_mode TEXT DEFAULT 'at_me',
                keywords TEXT,
                group_profile TEXT,
                reply_strategy TEXT,
                last_analysis_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS rule_sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_type TEXT NOT NULL,
                scope_id TEXT NOT NULL,
                source TEXT NOT NULL,
                rules_json TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                is_active BOOLEAN NOT NULL DEFAULT 0,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_rule_sets_scope_version
            ON rule_sets(scope_type, scope_id, version);
            CREATE TABLE IF NOT EXISTS supervisor_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis TEXT NOT NULL,
                changes TEXT,
                change_level INTEGER,
                approved BOOLEAN,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                trigger_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                summary TEXT,
                persona_json TEXT,
                suggestions_json TEXT,
                error_message TEXT,
                started_at DATETIME,
                finished_at DATETIME,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS review_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_type TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                analysis_run_id INTEGER,
                proposed_payload_json TEXT NOT NULL,
                rationale_json TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                edited_payload_json TEXT,
                apply_attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                reviewed_at DATETIME,
                applied_at DATETIME,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS analysis_policies (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                enabled BOOLEAN NOT NULL DEFAULT 0,
                cron_expr TEXT NOT NULL DEFAULT '0 */6 * * *',
                max_targets_per_run INTEGER NOT NULL DEFAULT 20,
                contacts_enabled BOOLEAN NOT NULL DEFAULT 1,
                groups_enabled BOOLEAN NOT NULL DEFAULT 1,
                min_hours_since_last_analysis INTEGER NOT NULL DEFAULT 24,
                selection_strategy TEXT NOT NULL DEFAULT 'recently_active_first',
                overlap_policy TEXT NOT NULL DEFAULT 'skip',
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS runtime_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                level TEXT NOT NULL DEFAULT 'info',
                message TEXT NOT NULL,
                payload_json TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS runtime_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS group_members (
                group_id TEXT NOT NULL,
                wxid TEXT NOT NULL,
                nickname TEXT,
                role TEXT DEFAULT '',
                personality TEXT DEFAULT '',
                style_notes TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                msg_count INTEGER DEFAULT 0,
                last_msg_at DATETIME,
                PRIMARY KEY (group_id, wxid)
            );
            CREATE TABLE IF NOT EXISTS proactive_chats (
                id TEXT PRIMARY KEY,
                chat_type TEXT NOT NULL,
                chat_name TEXT,
                enabled BOOLEAN NOT NULL DEFAULT 0,
                interval_minutes INTEGER NOT NULL DEFAULT 5,
                topic TEXT NOT NULL DEFAULT '',
                last_sent_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self._conn.commit()

        # Migrate existing databases — add columns if missing
        for col in ["persona_summary", "style_summary", "interaction_style_summary", "last_analysis_at"]:
            try:
                self._conn.execute(f"ALTER TABLE contacts ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists

        for col in ["group_profile", "reply_strategy", "last_analysis_at"]:
            try:
                self._conn.execute(f"ALTER TABLE groups ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass

        # Add my_alias_for column to contacts (what I call them)
        try:
            self._conn.execute("ALTER TABLE contacts ADD COLUMN my_alias_for TEXT")
        except sqlite3.OperationalError:
            pass

        # Add my_alias_for column to group_members
        try:
            self._conn.execute("ALTER TABLE group_members ADD COLUMN my_alias_for TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass

        # Add is_ai_generated column to messages
        try:
            self._conn.execute("ALTER TABLE messages ADD COLUMN is_ai_generated BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        # Backfill: mark existing AI-generated messages
        self._conn.execute("UPDATE messages SET is_ai_generated = 1 WHERE agent_model IS NOT NULL AND is_ai_generated = 0")
        # Also mark proactive messages (msg_id starts with proactive_ or out_)
        self._conn.execute("UPDATE messages SET is_ai_generated = 1 WHERE msg_id LIKE 'proactive_%' AND is_ai_generated = 0")
        self._conn.execute("UPDATE messages SET is_ai_generated = 1 WHERE msg_id LIKE 'out_%' AND is_ai_generated = 0")
        self._conn.commit()

    def save_message(self, msg: Message) -> None:
        try:
            is_ai = 1 if msg.agent_model else 0
            self._conn.execute(
                """INSERT OR IGNORE INTO messages
                   (msg_id, contact_id, group_id, direction, content, msg_type, agent_model, is_ai_generated, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (msg.msg_id, msg.contact_id, msg.group_id, msg.direction.value,
                 msg.content, msg.msg_type, msg.agent_model, is_ai,
                 msg.created_at.isoformat()),
            )
            self._conn.commit()
        except sqlite3.Error as e:
            logger.error("Failed to save message {}: {}", msg.msg_id, e)

    def get_recent_messages(
        self, contact_id: str, *, group_id: str | None = None, limit: int = 20
    ) -> list[Message]:
        if group_id:
            rows = self._conn.execute(
                """SELECT * FROM messages WHERE group_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (group_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT * FROM messages
                   WHERE contact_id = ? AND group_id IS NULL
                   ORDER BY created_at DESC LIMIT ?""",
                (contact_id, limit),
            ).fetchall()
        return [
            Message(
                msg_id=r["msg_id"],
                contact_id=r["contact_id"],
                group_id=r["group_id"],
                direction=MessageDirection(r["direction"]),
                content=r["content"],
                msg_type=r["msg_type"],
                agent_model=r["agent_model"],
            )
            for r in reversed(rows)
        ]

    def get_recent_messages_human_only(
        self, contact_id: str, *, group_id: str | None = None, limit: int = 20,
    ) -> list[Message]:
        """Get recent messages excluding AI-generated ones (for user persona analysis)."""
        if group_id:
            rows = self._conn.execute(
                """SELECT * FROM messages WHERE group_id = ? AND (is_ai_generated = 0 OR is_ai_generated IS NULL)
                   ORDER BY created_at DESC LIMIT ?""",
                (group_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT * FROM messages
                   WHERE contact_id = ? AND group_id IS NULL AND (is_ai_generated = 0 OR is_ai_generated IS NULL)
                   ORDER BY created_at DESC LIMIT ?""",
                (contact_id, limit),
            ).fetchall()
        return [
            Message(
                msg_id=r["msg_id"],
                contact_id=r["contact_id"],
                group_id=r["group_id"],
                direction=MessageDirection(r["direction"]),
                content=r["content"],
                msg_type=r["msg_type"],
                agent_model=r["agent_model"],
            )
            for r in reversed(rows)
        ]

    def save_contact(self, contact: Contact) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO contacts
               (wxid, nickname, remark, relationship, chat_prefs,
                is_whitelist, is_paused, last_interaction, my_alias_for, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (contact.wxid, contact.nickname, contact.remark,
             contact.relationship,
             json.dumps(contact.chat_prefs) if contact.chat_prefs else None,
             contact.is_whitelist, contact.is_paused,
             contact.last_interaction.isoformat() if contact.last_interaction else None,
             contact.my_alias_for,
             contact.created_at.isoformat()),
        )
        self._conn.commit()

    def save_group(self, group: Group) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO groups
               (group_id, group_name, is_active, trigger_mode, keywords, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                group.group_id,
                group.group_name,
                group.is_active,
                group.trigger_mode.value,
                json.dumps(group.keywords),
                group.created_at.isoformat(),
            ),
        )
        self._conn.commit()

    def get_contact(self, wxid: str) -> Contact | None:
        row = self._conn.execute(
            "SELECT * FROM contacts WHERE wxid = ?", (wxid,)
        ).fetchone()
        if not row:
            return None
        prefs = json.loads(row["chat_prefs"]) if row["chat_prefs"] else None
        return Contact(
            wxid=row["wxid"], nickname=row["nickname"], remark=row["remark"],
            relationship=row["relationship"], chat_prefs=prefs,
            is_whitelist=bool(row["is_whitelist"]),
            is_paused=bool(row["is_paused"]),
            my_alias_for=row["my_alias_for"] if "my_alias_for" in row.keys() else None,
        )

    def get_whitelist_contacts(self) -> list[Contact]:
        rows = self._conn.execute(
            "SELECT * FROM contacts WHERE is_whitelist = 1"
        ).fetchall()
        return [
            Contact(
                wxid=r["wxid"], nickname=r["nickname"], remark=r["remark"],
                is_whitelist=True, is_paused=bool(r["is_paused"]),
            )
            for r in rows
        ]

    def get_group(self, group_id: str) -> Group | None:
        row = self._conn.execute(
            "SELECT * FROM groups WHERE group_id = ?",
            (group_id,),
        ).fetchone()
        if not row:
            return None

        raw_keywords = row["keywords"] or "[]"
        try:
            keywords = json.loads(raw_keywords)
        except json.JSONDecodeError:
            keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]

        return Group(
            group_id=row["group_id"],
            group_name=row["group_name"],
            is_active=bool(row["is_active"]),
            trigger_mode=TriggerMode(row["trigger_mode"] or "at_me"),
            keywords=keywords,
        )

    def get_config(self, key: str, default: str = "") -> str:
        row = self._conn.execute(
            "SELECT value FROM runtime_config WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_config(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO runtime_config (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
