"""WeChat message monitor using DB decryption (WAL polling + SQLCipher decrypt)."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from Crypto.Cipher import AES
from loguru import logger

PAGE_SZ = 4096
SALT_SZ = 16
RESERVE_SZ = 80
SQLITE_HDR = b"SQLite format 3\x00"


def _decrypt_page(enc_key: bytes, page_data: bytes, pgno: int) -> bytes:
    iv = page_data[PAGE_SZ - RESERVE_SZ : PAGE_SZ - RESERVE_SZ + 16]
    if pgno == 1:
        encrypted = page_data[SALT_SZ : PAGE_SZ - RESERVE_SZ]
        decrypted = AES.new(enc_key, AES.MODE_CBC, iv).decrypt(encrypted)
        return bytes(SQLITE_HDR + decrypted + b"\x00" * RESERVE_SZ)
    else:
        encrypted = page_data[: PAGE_SZ - RESERVE_SZ]
        decrypted = AES.new(enc_key, AES.MODE_CBC, iv).decrypt(encrypted)
        return decrypted + b"\x00" * RESERVE_SZ


def decrypt_db_to_file(db_path: str, enc_key_hex: str, out_path: str) -> str:
    """Decrypt an entire SQLCipher DB to a plain SQLite file."""
    enc_key = bytes.fromhex(enc_key_hex)
    file_size = os.path.getsize(db_path)
    total_pages = file_size // PAGE_SZ
    out = bytearray()
    with open(db_path, "rb") as f:
        for pgno in range(1, total_pages + 1):
            out.extend(_decrypt_page(enc_key, f.read(PAGE_SZ), pgno))
    with open(out_path, "wb") as f:
        f.write(out)
    return out_path


class MessageMonitor:
    """Monitor WeChat messages via DB file polling + decryption."""

    def __init__(
        self,
        keys_file: str = "data/wechat_keys.json",
        poll_interval: float = 2.0,
    ) -> None:
        self._poll_interval = poll_interval
        self._callback: Callable | None = None
        self._running = False
        self._thread: threading.Thread | None = None

        # Load keys
        with open(keys_file) as f:
            self._keys = json.load(f)

        # Find WeChat DB directory
        self._db_dir = self._find_db_dir()

        # Track last seen timestamps per chat
        self._last_timestamps: dict[str, int] = {}

        # Contact cache: wxid -> nickname
        self._contact_cache: dict[str, str] = {}

        # Decrypt cache directory
        self._cache_dir = "/tmp/wechat_agent_cache"
        os.makedirs(self._cache_dir, exist_ok=True)

        # Track WAL mtimes
        self._wal_mtimes: dict[str, float] = {}

        # Discover all message DBs with keys
        self._message_dbs: list[str] = [
            k for k in self._keys
            if k.startswith("message/message_") and k.endswith(".db")
        ]
        logger.info("Monitoring {} message DBs: {}", len(self._message_dbs),
                     [d.split("/")[1] for d in self._message_dbs])

    def _find_db_dir(self) -> str:
        base = os.path.expanduser(
            "~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"
        )
        for entry in os.listdir(base):
            db_dir = os.path.join(base, entry, "db_storage")
            if os.path.isdir(db_dir):
                return db_dir
        raise FileNotFoundError("WeChat db_storage directory not found")

    def on_notification(self, callback: Callable) -> None:
        self._callback = callback

    def start(self) -> None:
        if not self._callback:
            logger.warning("No callback set, monitor won't deliver messages")

        self._running = True
        self._load_contacts()
        self._init_timestamps()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("MessageMonitor started (DB decrypt), dir={}", self._db_dir)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("MessageMonitor stopped")

    def _load_contacts(self) -> None:
        """Decrypt contact.db and build wxid -> nickname cache."""
        key_info = self._keys.get("contact/contact.db")
        if not key_info:
            logger.warning("No key for contact.db")
            return

        db_path = os.path.join(self._db_dir, "contact", "contact.db")
        out_path = os.path.join(self._cache_dir, "contact.db")
        try:
            decrypt_db_to_file(db_path, key_info["enc_key"], out_path)
            conn = sqlite3.connect(out_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT username, nick_name, remark FROM contact"
            ).fetchall()
            for r in rows:
                wxid = r["username"]
                name = r["remark"] or r["nick_name"] or wxid
                self._contact_cache[wxid] = name
            conn.close()
            logger.info("Loaded {} contacts", len(self._contact_cache))
        except Exception as e:
            logger.error("Failed to load contacts: {}", e)

    def _init_timestamps(self) -> None:
        """Initialize last seen timestamps from session.db."""
        key_info = self._keys.get("session/session.db")
        if not key_info:
            return
        try:
            db_path = os.path.join(self._db_dir, "session", "session.db")
            out_path = os.path.join(self._cache_dir, "session.db")
            decrypt_db_to_file(db_path, key_info["enc_key"], out_path)
            conn = sqlite3.connect(out_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT username, last_timestamp FROM SessionTable"
            ).fetchall()
            for r in rows:
                self._last_timestamps[r["username"]] = r["last_timestamp"]
            conn.close()
            logger.debug("Initialized timestamps for {} sessions", len(self._last_timestamps))
        except Exception as e:
            logger.error("Failed to init timestamps: {}", e)

        # Also init WAL mtimes
        monitored = ["session/session.db"] + self._message_dbs
        for db_rel in monitored:
            wal_path = os.path.join(self._db_dir, db_rel + "-wal")
            if os.path.exists(wal_path):
                self._wal_mtimes[db_rel] = os.path.getmtime(wal_path)

    def _poll_loop(self) -> None:
        logger.debug("Poll loop started")
        poll_count = 0
        while self._running:
            time.sleep(self._poll_interval)
            poll_count += 1
            try:
                if poll_count <= 3 or poll_count % 30 == 0:
                    logger.debug("Poll cycle #{}", poll_count)
                self._check_new_messages()
            except Exception as e:
                logger.exception("Poll error: {}", e)

    def _check_new_messages(self) -> None:
        """Decrypt session.db, find updated chats, fetch new messages."""
        key_info = self._keys.get("session/session.db")
        if not key_info:
            return

        db_path = os.path.join(self._db_dir, "session", "session.db")
        out_path = os.path.join(self._cache_dir, "session_live.db")
        decrypt_db_to_file(db_path, key_info["enc_key"], out_path)

        conn = sqlite3.connect(out_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT username, last_timestamp, summary, last_msg_sender, "
            "last_sender_display_name, last_msg_type "
            "FROM SessionTable WHERE last_timestamp > 0 "
            "ORDER BY last_timestamp DESC"
        ).fetchall()
        conn.close()

        for r in rows:
            username = r["username"]
            ts = r["last_timestamp"]
            prev_ts = self._last_timestamps.get(username, 0)

            if ts > prev_ts:
                self._last_timestamps[username] = ts
                # Fetch actual new messages from message DB
                self._fetch_and_deliver(username, prev_ts)

    def _fetch_and_deliver(self, username: str, since_ts: int) -> None:
        """Decrypt message DBs and deliver new messages for a chat."""
        if not self._callback:
            return

        table_hash = hashlib.md5(username.encode()).hexdigest()
        table_name = f"Msg_{table_hash}"

        # Search across all message DBs for this table
        rows = []
        for db_rel in self._message_dbs:
            msg_key = self._keys.get(db_rel)
            if not msg_key:
                continue

            db_file = db_rel.split("/")[1]  # e.g. "message_0.db"
            db_path = os.path.join(self._db_dir, "message", db_file)
            out_path = os.path.join(self._cache_dir, f"{db_file.replace('.db', '_live.db')}")

            try:
                decrypt_db_to_file(db_path, msg_key["enc_key"], out_path)
            except Exception as e:
                logger.debug("Failed to decrypt {}: {}", db_file, e)
                continue

            try:
                conn = sqlite3.connect(out_path)
                conn.row_factory = sqlite3.Row
                found = conn.execute(
                    f"SELECT local_id, create_time, local_type, message_content, "
                    f"real_sender_id FROM [{table_name}] "
                    f"WHERE create_time > ? ORDER BY create_time ASC",
                    (since_ts,),
                ).fetchall()
                conn.close()
                if found:
                    rows = found
                    break  # Found the right DB
            except Exception:
                continue  # Table not in this DB, try next

        if not rows:
            return

        is_group = username.endswith("@chatroom")

        for r in rows:
            content = r["message_content"] or ""
            if isinstance(content, bytes):
                try:
                    import zstandard
                    content = zstandard.ZstdDecompressor().decompress(content).decode("utf-8", "replace")
                except Exception:
                    continue

            content = str(content)
            msg_type = r["local_type"]

            # Skip non-text messages
            if msg_type != 1:
                continue

            sender_wxid = r["real_sender_id"] or ""

            # Group messages: content = "sender_wxid:\ncontent"
            # Self-sent group messages have NO prefix — skip them
            if is_group:
                if ":\n" in content:
                    parts = content.split(":\n", 1)
                    sender_wxid = parts[0]
                    content = parts[1]
                else:
                    # No prefix = self-sent message, skip
                    continue

            sender_name = self._contact_cache.get(sender_wxid, sender_wxid)
            group_name = self._contact_cache.get(username, username) if is_group else None

            parsed = {
                "sender_name": sender_name,
                "sender_id": sender_wxid,
                "content": content,
                "is_group": is_group,
                "group_name": group_name,
                "group_id": username if is_group else None,
                "msg_id": str(r["local_id"]),
                "timestamp": r["create_time"],
            }

            logger.info(
                "New msg: [{}] {} -> {}",
                group_name or sender_name,
                sender_name,
                content[:50],
            )
            self._callback(parsed)

    def resolve_name(self, wxid: str) -> str:
        return self._contact_cache.get(wxid, wxid)
