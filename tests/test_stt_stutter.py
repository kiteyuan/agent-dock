from runtime.transport.speech.whisper_stt import collapse_char_stutter


def test_repeated_whisper_characters_collapse() -> None:
    raw = "你你好好,你你还还记记得得上上次次的的对对话话吗吗?"
    assert collapse_char_stutter(raw) == "你好,你还记得上次的对话吗?"


def test_normal_speech_is_not_collapsed() -> None:
    text = "你好，你还记得上次的对话吗？"
    assert collapse_char_stutter(text) == text
