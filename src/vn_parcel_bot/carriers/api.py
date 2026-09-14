"""Contract for carrier modules in carriers/modules/.

A module file defines MODULE = CarrierModule(...). The running bot reloads module files,
so they must not do I/O, start tasks or change global state at import time.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from vn_parcel_bot.carriers.models import Carrier

PRIORITY_PREFIXED = 100
PRIORITY_NUMERIC = 60
PRIORITY_SHARED_NUMERIC = 40
PRIORITY_GENERIC = 10


def no_client() -> Carrier | None:
    return None


def no_hint(tracking_number: str) -> str | None:
    return None


@dataclass(frozen=True)
class Rule:
    pattern: str
    priority: int
    rank: int = 0
    standalone_only: bool = False
    compiled: re.Pattern[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "compiled", re.compile(self.pattern, re.ASCII))

    def matches(self, code: str) -> bool:
        return self.compiled.fullmatch(code) is not None


@dataclass(frozen=True)
class CarrierModule:
    code: str
    display_name: str
    rules: tuple[Rule, ...]
    order: int = 100
    needs_phone: bool = False
    link_template: str | None = None
    examples: tuple[tuple[str, bool], ...] = ()
    build_client: Callable[[], Carrier | None] = no_client
    pending_hint: Callable[[str], str | None] = no_hint
