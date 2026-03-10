from __future__ import annotations

import copy

from lacuna.context import TOOL_RESULT_KEEP_CHARS, trim_messages


def _make_tool_result_msg(tool_use_id: str, content: str) -> dict:
    return {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": content}],
    }


def _make_assistant_msg(text: str = "thinking") -> dict:
    return {"role": "assistant", "content": [{"type": "text", "text": text}]}


def test_tool_result_keep_chars_value():
    assert TOOL_RESULT_KEEP_CHARS == 2000


def test_no_trim_when_under_threshold():
    messages = [{"role": "user", "content": "hi"}]
    result = trim_messages(messages, max_input_tokens=180_000)
    assert result is messages  # exact same object — no copy made


def test_does_not_mutate_input(sample_messages: list[dict]):
    original = copy.deepcopy(sample_messages)
    # Force trim by using a tiny token budget
    trim_messages(sample_messages, max_input_tokens=10, keep_last_n_turns=2)
    assert sample_messages == original


def test_first_message_never_trimmed(sample_messages: list[dict]):
    result = trim_messages(sample_messages, max_input_tokens=10, keep_last_n_turns=2)
    assert result[0] == sample_messages[0]


def test_long_tool_result_truncated(sample_messages: list[dict]):
    # sample_messages[2] is the user message with a long tool_result.
    # keep_last_n_turns=2 protects only the last 2 assistant turns, so index 2 gets trimmed.
    result = trim_messages(sample_messages, max_input_tokens=10, keep_last_n_turns=2)
    old_block = result[2]["content"][0]
    assert old_block["type"] == "tool_result"
    assert len(old_block["content"]) <= TOOL_RESULT_KEEP_CHARS + 100  # small overhead for suffix


def test_truncated_content_has_suffix(sample_messages: list[dict]):
    result = trim_messages(sample_messages, max_input_tokens=10, keep_last_n_turns=2)
    old_block = result[2]["content"][0]
    assert "[...truncated, original length:" in old_block["content"]


def test_short_tool_results_not_truncated():
    short = "x" * 100
    messages = [
        {"role": "user", "content": "start"},
        _make_assistant_msg(),
        _make_tool_result_msg("t1", short),
        _make_assistant_msg(),
        _make_tool_result_msg("t2", short),
    ]
    result = trim_messages(messages, max_input_tokens=10, keep_last_n_turns=1)
    # The tool result in msg[2] is outside the keep window and short — should be unchanged
    assert result[2]["content"][0]["content"] == short


def test_assistant_messages_never_trimmed(sample_messages: list[dict]):
    result = trim_messages(sample_messages, max_input_tokens=10, keep_last_n_turns=2)
    for orig, trimmed in zip(sample_messages, result):
        if orig.get("role") == "assistant":
            assert orig == trimmed


def test_kept_window_messages_unchanged(sample_messages: list[dict]):
    keep_last_n_turns = 2
    result = trim_messages(
        sample_messages, max_input_tokens=10, keep_last_n_turns=keep_last_n_turns
    )
    # Find the index where we started keeping
    assistant_count = 0
    keep_from = 0
    for i in range(len(sample_messages) - 1, -1, -1):
        if sample_messages[i].get("role") == "assistant":
            assistant_count += 1
            if assistant_count >= keep_last_n_turns:
                keep_from = i
                break
    for i in range(keep_from, len(sample_messages)):
        assert result[i] == sample_messages[i]


def test_returns_list_same_length(sample_messages: list[dict]):
    result = trim_messages(sample_messages, max_input_tokens=10, keep_last_n_turns=2)
    assert len(result) == len(sample_messages)
