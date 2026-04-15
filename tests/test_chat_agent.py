from unittest.mock import MagicMock
from src.agents.chat_agent import ChatAgent
from src.backend.base import IncomingMessage
from src.models.schemas import Contact, Message, MessageDirection


def test_build_system_prompt():
    agent = ChatAgent.__new__(ChatAgent)
    agent._user_name = "小明"
    agent._context = MagicMock()
    agent._context.get_contact.return_value = None
    agent._context.get_config.return_value = ""
    agent._style_manager = MagicMock()
    agent._style_manager.format_style_prompt.return_value = "tone: 随意"

    prompt = agent._build_system_prompt(contact_id="wxid_abc")
    assert "小明" in prompt
    assert "随意" in prompt


def test_build_messages_for_api():
    agent = ChatAgent.__new__(ChatAgent)
    agent._user_name = "小明"
    agent._context = MagicMock()
    agent._context.get_contact.return_value = None
    history = [
        Message(msg_id="1", contact_id="wxid_abc", direction=MessageDirection.INCOMING, content="你好"),
        Message(msg_id="2", contact_id="wxid_abc", direction=MessageDirection.OUTGOING, content="你好呀"),
    ]
    api_messages = agent._build_messages(history, "最近怎么样")
    # Now uses single-message chronological format
    assert len(api_messages) == 1
    assert api_messages[0]["role"] == "user"
    assert "你好" in api_messages[0]["content"]
    assert "你好呀" in api_messages[0]["content"]


def test_clean_response():
    agent = ChatAgent.__new__(ChatAgent)
    agent._style_manager = MagicMock()
    agent._style_manager.get_forbidden_patterns.return_value = ["作为AI", "我来为你"]

    assert agent._clean_response("作为AI，我觉得不错") == "，我觉得不错"
    assert agent._clean_response("好的呀") == "好的呀"


def test_should_respond_whitelist():
    agent = ChatAgent.__new__(ChatAgent)
    agent._context = MagicMock()
    agent._whitelist_only = True

    agent._context.get_contact.return_value = Contact(wxid="wxid_abc", is_whitelist=False)
    msg = IncomingMessage(sender_name="张三", sender_id="wxid_abc", content="你好", is_group=False)
    assert agent._should_respond(msg) is False

    agent._context.get_contact.return_value = Contact(wxid="wxid_abc", is_whitelist=True)
    assert agent._should_respond(msg) is True


def test_should_respond_paused():
    agent = ChatAgent.__new__(ChatAgent)
    agent._context = MagicMock()
    agent._whitelist_only = True

    agent._context.get_contact.return_value = Contact(wxid="wxid_abc", is_whitelist=True, is_paused=True)
    msg = IncomingMessage(sender_name="张三", sender_id="wxid_abc", content="你好", is_group=False)
    assert agent._should_respond(msg) is False


def test_group_trigger_mode_all_matches_any_message():
    agent = ChatAgent.__new__(ChatAgent)
    assert agent._check_trigger("随便说一句", "all", []) is True
