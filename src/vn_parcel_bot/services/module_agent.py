"""Turn a plain-language request into a carrier module file.

The agent only ever returns text. This module decides what that text is allowed to be, where
it may land, and whether it loads: the Claude CLI runs with no tools, the reply is checked
before anything is written, writes are confined to carriers/modules/, and the registry's own
example validation is the final gate. A module that fails it is rolled back.

Detection only: rules, names, links and examples. A generated module never gets a tracking
client, so `/hozk` cannot produce code that makes network calls.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from vn_parcel_bot.carriers.registry import MODULES_DIR

MODULE_CODE = re.compile(r'code\s*=\s*["\']([a-z][a-z0-9_]{1,20})["\']', re.ASCII)
FENCE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)

# A generated file may import the contract and the standard regex module, nothing else.
ALLOWED_IMPORT_LINES = (
    "from vn_parcel_bot.carriers.api import",
    "import re",
)
# Anything that touches the machine, the network, or the interpreter.
FORBIDDEN = (
    "open(",
    "subprocess",
    "os.",
    "sys.",
    "eval(",
    "exec(",
    "__import__",
    "httpx",
    "requests",
    "socket",
    "shutil",
    "pathlib",
    "build_client",
)

EXAMPLE_MODULE = """from vn_parcel_bot.carriers.api import PRIORITY_PREFIXED, CarrierModule, Rule

MODULE = CarrierModule(
    code="ghtk",
    display_name="GHTK",
    order=90,
    rules=(
        Rule(r"S\\d{5,10}(\\.[0-9A-Z]{1,12}){1,4}", PRIORITY_PREFIXED),
        Rule(r"GHTK[0-9A-Z]{6,16}", PRIORITY_PREFIXED),
    ),
    link_template="https://i.ghtk.vn/{code}",
    examples=(("S1234567.MB12.D5.123456789", True), ("GHTK0012345678", True)),
)
"""

PROMPT = """You write one carrier module for a Vietnamese parcel-tracking bot.

The file must define MODULE = CarrierModule(...) and import only from
vn_parcel_bot.carriers.api (and `re` if needed). It must not do any I/O at import time.

Fields you may set:
  code           short lowercase id, also the file name
  display_name   the carrier's name as people write it
  rules          tuple of Rule(pattern, priority) - a full-match regex per code shape
  order          detection order, lower wins ties (default 100)
  needs_phone    True when tracking needs the recipient's phone digits
  link_template  public tracking URL with {code} in it
  examples       tuple of (code, True) pairs - REAL-LOOKING codes that your rules match
  code_lengths   tuple of valid code lengths, when the carrier has fixed lengths

Never set build_client: this bot adds tracking clients by hand, not here.

The examples are checked the moment the file loads. If a rule does not match its own
example the module is rejected, so make them agree.

Here is a complete, working module to copy the shape of:

<<EXAMPLE>>

Write the module for this request. Reply with the file content only, no explanation:

<<REQUEST>>
"""


@dataclass(frozen=True)
class AgentOutcome:
    """What came back, and whether it is safe to write."""

    ok: bool
    code: str | None = None
    source: str | None = None
    error: str | None = None


def build_prompt(request: str) -> str:
    # Plain replacement, not str.format: the prompt documents {code} and shows regex braces.
    return PROMPT.replace("<<EXAMPLE>>", EXAMPLE_MODULE).replace(
        "<<REQUEST>>", " ".join(request.split())
    )


def extract_source(reply: str) -> str | None:
    """The module file out of the agent's reply, fenced or bare."""
    fenced = FENCE.search(reply)
    text = (fenced.group(1) if fenced else reply).strip()
    return text if "MODULE" in text and "CarrierModule(" in text else None


def module_code(source: str) -> str | None:
    found = MODULE_CODE.search(source)
    return found.group(1) if found else None


def unsafe_reason(source: str) -> str | None:
    """Why this text must not be written, or None when it looks like a plain module.

    A speed bump, not a sandbox: the file is imported by the running bot, so this only
    catches the obvious. The narrow contract above is what keeps the blast radius small.
    """
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")) and not stripped.startswith(
            ALLOWED_IMPORT_LINES
        ):
            return f"import not allowed: {stripped}"
    for token in FORBIDDEN:
        if token in source:
            return f"not allowed here: {token}"
    return None


def target_path(code: str, directory: Path = MODULES_DIR) -> Path | None:
    """Where this module belongs, or None when the name could escape the directory."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,20}", code, re.ASCII):
        return None
    path = (directory / f"{code}.py").resolve()
    return path if path.parent == Path(directory).resolve() else None


def review(reply: str) -> AgentOutcome:
    """Everything that can be decided from the text alone, before anything is written."""
    source = extract_source(reply)
    if source is None:
        return AgentOutcome(False, error="the reply did not contain a module")
    code = module_code(source)
    if code is None:
        return AgentOutcome(False, error="the module has no usable code=")
    if target_path(code) is None:
        return AgentOutcome(False, error=f"unusable module name: {code}")
    reason = unsafe_reason(source)
    if reason is not None:
        return AgentOutcome(False, error=reason)
    return AgentOutcome(True, code=code, source=source if source.endswith("\n") else source + "\n")
