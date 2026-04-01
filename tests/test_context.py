import sqlite3

from src.core.context import ContextManager
from src.models.schemas import Contact, Group, Message, MessageDirection, TriggerMode


def test_init_creates_tables(tmp_path):
    db_path = tmp_path / "test.db"
    ctx = ContextManager(db_path)
    ctx.close()


def test_save_and_get_messages(tmp_path):
    db_path = tmp_path / "test.db"
    ctx = ContextManager(db_path)
    msg = Message(
        msg_id="msg_001", contact_id="wxid_abc",
        direction=MessageDirection.INCOMING, content="你好",
    )
    ctx.save_message(msg)
    messages = ctx.get_recent_messages("wxid_abc", limit=10)
    assert len(messages) == 1
    assert messages[0].content == "你好"
    ctx.close()


def test_duplicate_message_ignored(tmp_path):
    db_path = tmp_path / "test.db"
    ctx = ContextManager(db_path)
    msg = Message(
        msg_id="msg_001", contact_id="wxid_abc",
        direction=MessageDirection.INCOMING, content="你好",
    )
    ctx.save_message(msg)
    ctx.save_message(msg)
    messages = ctx.get_recent_messages("wxid_abc", limit=10)
    assert len(messages) == 1
    ctx.close()


def test_save_and_get_contact(tmp_path):
    db_path = tmp_path / "test.db"
    ctx = ContextManager(db_path)
    contact = Contact(wxid="wxid_abc", nickname="张三", is_whitelist=True)
    ctx.save_contact(contact)
    result = ctx.get_contact("wxid_abc")
    assert result is not None
    assert result.nickname == "张三"
    assert result.is_whitelist is True
    ctx.close()


def test_get_whitelist_contacts(tmp_path):
    db_path = tmp_path / "test.db"
    ctx = ContextManager(db_path)
    ctx.save_contact(Contact(wxid="wxid_1", nickname="A", is_whitelist=True))
    ctx.save_contact(Contact(wxid="wxid_2", nickname="B", is_whitelist=False))
    ctx.save_contact(Contact(wxid="wxid_3", nickname="C", is_whitelist=True))
    whitelist = ctx.get_whitelist_contacts()
    assert len(whitelist) == 2
    ctx.close()


def test_get_recent_messages_with_group(tmp_path):
    db_path = tmp_path / "test.db"
    ctx = ContextManager(db_path)
    ctx.save_message(Message(
        msg_id="msg_g1", contact_id="wxid_a", group_id="group_1",
        direction=MessageDirection.INCOMING, content="群消息1",
    ))
    ctx.save_message(Message(
        msg_id="msg_g2", contact_id="wxid_b", group_id="group_1",
        direction=MessageDirection.INCOMING, content="群消息2",
    ))
    ctx.save_message(Message(
        msg_id="msg_p1", contact_id="wxid_a",
        direction=MessageDirection.INCOMING, content="私聊消息",
    ))
    group_msgs = ctx.get_recent_messages("wxid_a", group_id="group_1", limit=10)
    assert len(group_msgs) == 2
    private_msgs = ctx.get_recent_messages("wxid_a", limit=10)
    assert len(private_msgs) == 1
    ctx.close()


def test_save_and_get_group_preserves_keywords_as_list(tmp_path):
    db_path = tmp_path / "test.db"
    ctx = ContextManager(db_path)
    ctx.save_group(Group(
        group_id="group_1",
        group_name="测试群",
        is_active=True,
        trigger_mode=TriggerMode.ALL,
        keywords=["小明", "帮忙"],
    ))

    group = ctx.get_group("group_1")

    assert group is not None
    assert group.trigger_mode == TriggerMode.ALL
    assert group.keywords == ["小明", "帮忙"]
    ctx.close()


def test_analysis_runs_table_insert(tmp_path):
    db_path = tmp_path / "test.db"
    ctx = ContextManager(db_path)
    ctx._conn.execute(
        """INSERT INTO analysis_runs (target_type, target_id, trigger_type, status)
           VALUES ('contact', 'wxid_abc', 'manual', 'queued')"""
    )
    ctx._conn.commit()
    row = ctx._conn.execute("SELECT * FROM analysis_runs WHERE target_id = 'wxid_abc'").fetchone()
    assert row is not None
    assert row["trigger_type"] == "manual"
    assert row["status"] == "queued"
    ctx.close()


def test_review_items_table_insert(tmp_path):
    db_path = tmp_path / "test.db"
    ctx = ContextManager(db_path)
    ctx._conn.execute(
        """INSERT INTO review_items (review_type, target_type, target_id, proposed_payload_json)
           VALUES ('rule_change', 'contact', 'wxid_abc', '{"key": "value"}')"""
    )
    ctx._conn.commit()
    row = ctx._conn.execute("SELECT * FROM review_items WHERE target_id = 'wxid_abc'").fetchone()
    assert row is not None
    assert row["review_type"] == "rule_change"
    assert row["status"] == "pending"
    assert row["apply_attempts"] == 0
    ctx.close()


def test_analysis_policies_table_insert(tmp_path):
    db_path = tmp_path / "test.db"
    ctx = ContextManager(db_path)
    ctx._conn.execute(
        """INSERT INTO analysis_policies (id, enabled, cron_expr)
           VALUES (1, 1, '0 */12 * * *')"""
    )
    ctx._conn.commit()
    row = ctx._conn.execute("SELECT * FROM analysis_policies WHERE id = 1").fetchone()
    assert row is not None
    assert row["enabled"] == 1
    assert row["cron_expr"] == "0 */12 * * *"
    assert row["max_targets_per_run"] == 20
    ctx.close()


def test_runtime_events_table_insert(tmp_path):
    db_path = tmp_path / "test.db"
    ctx = ContextManager(db_path)
    ctx._conn.execute(
        """INSERT INTO runtime_events (event_type, level, message)
           VALUES ('agent_started', 'info', 'Agent started successfully')"""
    )
    ctx._conn.commit()
    row = ctx._conn.execute("SELECT * FROM runtime_events WHERE event_type = 'agent_started'").fetchone()
    assert row is not None
    assert row["level"] == "info"
    assert row["message"] == "Agent started successfully"
    ctx.close()


def test_contacts_has_profile_columns(tmp_path):
    db_path = tmp_path / "test.db"
    ctx = ContextManager(db_path)
    ctx._conn.execute(
        """INSERT INTO contacts (wxid, persona_summary, style_summary, interaction_style_summary, last_analysis_at)
           VALUES ('wxid_test', 'friendly person', 'casual', 'responsive', '2026-03-30T12:00:00')"""
    )
    ctx._conn.commit()
    row = ctx._conn.execute("SELECT * FROM contacts WHERE wxid = 'wxid_test'").fetchone()
    assert row["persona_summary"] == "friendly person"
    assert row["style_summary"] == "casual"
    assert row["interaction_style_summary"] == "responsive"
    assert row["last_analysis_at"] == "2026-03-30T12:00:00"
    ctx.close()


def test_groups_has_profile_columns(tmp_path):
    db_path = tmp_path / "test.db"
    ctx = ContextManager(db_path)
    ctx._conn.execute(
        """INSERT INTO groups (group_id, group_profile, reply_strategy, last_analysis_at)
           VALUES ('group_test', 'tech discussion', 'formal', '2026-03-30T12:00:00')"""
    )
    ctx._conn.commit()
    row = ctx._conn.execute("SELECT * FROM groups WHERE group_id = 'group_test'").fetchone()
    assert row["group_profile"] == "tech discussion"
    assert row["reply_strategy"] == "formal"
    assert row["last_analysis_at"] == "2026-03-30T12:00:00"
    ctx.close()


def test_migration_adds_columns_to_existing_db(tmp_path):
    """Verify migration logic adds columns to a database created without them."""
    db_path = tmp_path / "test.db"
    # Create a DB with old schema (no new columns)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE contacts (
        wxid TEXT PRIMARY KEY, nickname TEXT, remark TEXT,
        relationship TEXT, chat_prefs TEXT,
        is_whitelist BOOLEAN DEFAULT 0, is_paused BOOLEAN DEFAULT 0,
        last_interaction DATETIME, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE groups (
        group_id TEXT PRIMARY KEY, group_name TEXT,
        is_active BOOLEAN DEFAULT 0, trigger_mode TEXT DEFAULT 'at_me',
        keywords TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()

    # Now open with ContextManager which should run migrations
    ctx = ContextManager(db_path)
    # Verify new columns exist by inserting data that uses them
    ctx._conn.execute(
        "UPDATE contacts SET persona_summary = 'test' WHERE wxid = 'nonexistent'"
    )
    ctx._conn.execute(
        "UPDATE groups SET group_profile = 'test' WHERE group_id = 'nonexistent'"
    )
    ctx.close()
