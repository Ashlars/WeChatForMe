from src.models.schemas import Message, Contact, Group, MessageDirection, TriggerMode


def test_message_creation():
    msg = Message(
        msg_id="test_123",
        contact_id="wxid_abc",
        direction=MessageDirection.INCOMING,
        content="你好",
    )
    assert msg.msg_id == "test_123"
    assert msg.direction == MessageDirection.INCOMING
    assert msg.group_id is None
    assert msg.msg_type == "text"


def test_contact_creation():
    contact = Contact(
        wxid="wxid_abc",
        nickname="张三",
        remark="大学同学",
        relationship="大学室友",
    )
    assert contact.is_whitelist is False
    assert contact.is_paused is False


def test_group_creation():
    group = Group(
        group_id="group_123",
        group_name="测试群",
        is_active=True,
        trigger_mode=TriggerMode.AT_ME,
    )
    assert group.keywords == []


def test_message_direction_enum():
    assert MessageDirection.INCOMING == "incoming"
    assert MessageDirection.OUTGOING == "outgoing"


def test_trigger_mode_all_enum():
    assert TriggerMode("all") == TriggerMode.ALL
