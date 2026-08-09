from dataclasses import dataclass


@dataclass
class Thread:
    messages: list[dict]
    thread_starter_id: int
    link_prefix: str | None = None
    # 1-based position handed to the llm, not the telegram message id
    id: int | None = None
    name: str | None = None

    def __len__(self):
        return len(self.messages)

    @property
    def len(self):
        return len(self)

    @property
    def url(self):
        return f"{self.link_prefix}{self.thread_starter_id}/"
