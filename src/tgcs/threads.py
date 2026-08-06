import json

from tgcs.models import Thread


def build_threads(history_raw: str) -> list[Thread]:
    # create threads from raw daily tg history (jsonl) by walking reply chains
    history = [json.loads(line) for line in history_raw.splitlines() if line.strip()]
    messages = sorted(history, key=lambda m: m["date"])
    messages_map = {m["id"]: m for m in messages}
    threads = {}
    for m in messages:
        if m["reply_to_message_id"] is None:
            threads[m["id"]] = [m]
        else:
            root = messages_map.get(m["reply_to_message_id"])
            if not root:
                threads[m["id"]] = [m]
                continue
            while root["reply_to_message_id"] and messages_map.get(
                root["reply_to_message_id"]
            ):
                root = messages_map[root["reply_to_message_id"]]
            threads[root["id"]].append(m)

    thread_list = []
    for starter, msgs in threads.items():
        thread_temp = Thread(messages=msgs, thread_starter_id=starter)
        thread_list.append(thread_temp)
    return thread_list
