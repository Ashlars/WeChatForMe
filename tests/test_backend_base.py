import pytest
from src.backend.base import WeChatBackend, IncomingMessage


def test_cannot_instantiate_abstract():
    with pytest.raises(TypeError):
        WeChatBackend()


def test_incoming_message_dataclass():
    msg = IncomingMessage(
        sender_name="张三",
        sender_id="wxid_abc",
        content="你好",
        is_group=False,
    )
    assert msg.sender_name == "张三"
    assert msg.group_id is None
    assert msg.group_name is None
