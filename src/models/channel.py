from dataclasses import dataclass
from typing import Any, Coroutine, Callable, Self

@dataclass
class Channel:
    client: Any = None
    user: str = None
    session_token: str = None
    auth: bool = False
    pub_key: bytes = None
    current_key: bytes = None
    stale_timer: None = None

@dataclass
class DnsRecord:
    host: str
    value: str
    label: str
    priority: int
    ttl: int