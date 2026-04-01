from src.core.security import SecurityManager


def test_sensitive_word_filter():
    sm = SecurityManager(sensitive_words=["政治", "赌博"], rate_limit=30, pause_keyword="#人工")
    assert sm.contains_sensitive("今天聊聊政治") is True
    assert sm.contains_sensitive("今天天气不错") is False


def test_pause_keyword_detection():
    sm = SecurityManager(sensitive_words=[], rate_limit=30, pause_keyword="#人工")
    assert sm.is_pause_command("#人工") is True
    assert sm.is_pause_command("你好") is False


def test_rate_limiter_allows_within_limit():
    sm = SecurityManager(sensitive_words=[], rate_limit=2, pause_keyword="#人工")
    assert sm.check_rate_limit("wxid_abc") is True
    sm.record_reply("wxid_abc")
    assert sm.check_rate_limit("wxid_abc") is True
    sm.record_reply("wxid_abc")
    assert sm.check_rate_limit("wxid_abc") is False


def test_generate_delay():
    sm = SecurityManager(sensitive_words=[], rate_limit=30, pause_keyword="#人工")
    delay = sm.generate_delay(2, 8)
    assert 2 <= delay <= 8
