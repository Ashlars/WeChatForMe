from unittest.mock import MagicMock
from src.agents.supervisor import SupervisorAgent
from src.models.schemas import Message, MessageDirection


def test_build_analysis_prompt():
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._style_manager = MagicMock()
    agent._style_manager.get_style.return_value = {"tone": "随意"}

    messages = [
        Message(msg_id="1", contact_id="wxid_abc", direction=MessageDirection.INCOMING, content="你好"),
        Message(msg_id="2", contact_id="wxid_abc", direction=MessageDirection.OUTGOING, content="你好呀", agent_model="sonnet"),
        Message(msg_id="3", contact_id="wxid_abc", direction=MessageDirection.INCOMING, content="最近怎么样"),
    ]
    prompt = agent._build_analysis_prompt(messages)
    assert "你好" in prompt
    assert "你好呀" in prompt


def test_detect_anomaly_negative_sentiment():
    agent = SupervisorAgent.__new__(SupervisorAgent)
    assert agent._detect_anomaly("你说的什么鬼东西") is True
    assert agent._detect_anomaly("？？？") is True
    assert agent._detect_anomaly("好的") is False


def test_classify_change_level():
    agent = SupervisorAgent.__new__(SupervisorAgent)
    assert agent._classify_change_level({"tone": "稍微正式一点"}) == 1
    assert agent._classify_change_level({"whitelist_add": "wxid_new"}) == 2
