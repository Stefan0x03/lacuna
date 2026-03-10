from __future__ import annotations

import copy

TOOL_RESULT_KEEP_CHARS = 2000


def trim_messages(
    messages: list[dict],
    max_input_tokens: int = 180_000,
    keep_last_n_turns: int = 6,
) -> list[dict]:
    estimated_tokens = sum(len(str(m)) // 4 for m in messages)
    if estimated_tokens < max_input_tokens * 0.8:
        return messages

    # Find the start index of the last keep_last_n_turns assistant messages.
    # We protect those assistant messages and all messages after them.
    assistant_count = 0
    keep_from_idx = 0
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "assistant":
            assistant_count += 1
            if assistant_count >= keep_last_n_turns:
                keep_from_idx = i
                break

    result: list[dict] = []
    for i, msg in enumerate(messages):
        # Never touch the first message or anything in the kept window.
        if i == 0 or i >= keep_from_idx:
            result.append(msg)
            continue

        # Only truncate tool_result blocks in user-role messages.
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            new_content = []
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    original = block.get("content", "")
                    if isinstance(original, str) and len(original) > TOOL_RESULT_KEEP_CHARS:
                        block = copy.copy(block)
                        block["content"] = (
                            original[:TOOL_RESULT_KEEP_CHARS]
                            + f"\n[...truncated, original length: {len(original)} chars]"
                        )
                new_content.append(block)
            result.append({**msg, "content": new_content})
        else:
            result.append(msg)

    return result
