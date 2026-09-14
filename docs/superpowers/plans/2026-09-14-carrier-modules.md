# Carrier Modules with Hot Reload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every carrier lives in one file under `src/vn_parcel_bot/carriers/modules/`, the running bot reloads a changed module after a self-check, and every 15-digit number is tracked as Cainiao.

**Architecture:** `carriers/api.py` defines the module contract (`Rule`, `CarrierModule`). `carriers/registry.py` loads module files into an immutable `CarrierSnapshot` (detection, links, hints, clients) held by a `CarrierRegistry`; a 30 s job refreshes changed files (debounced, validated, last good version kept). Services get the registry injected; formatting, parsing and code extraction read the process-wide registry through `current_snapshot()`. Schema migration 2 drops the carrier CHECK.

**Tech Stack:** Python 3.13, python-telegram-bot 22.8 (JobQueue), aiosqlite, httpx, pytest (asyncio auto), respx, ruff 0.16.7.

**Spec:** `docs/superpowers/specs/2026-09-14-carrier-modules-design.md` (Parts A and B; Part C dropped).

## Global Constraints

- Test first: write the test, run it red, implement, run green.
- Gates before every commit, from the repo root in PowerShell: `.\.venv\Scripts\ruff check . --fix`, `.\.venv\Scripts\ruff format .`, `.\.venv\Scripts\ruff check . --output-format concise`, `.\.venv\Scripts\ruff format --check .`, `.\.venv\Scripts\python -m pytest -q`. Commit only when all pass.
- Commit explicit paths only. Every commit message ends with:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01JNknSSDZMR9Cg8iyhqGxQN`.
- Never commit real tracking codes, the bot token or `.env` contents; tests use synthetic codes.
- No captcha or anti-bot tooling (insane-search stays uninstalled).
- User-visible behaviour stays the same except: 15-digit numbers are added as Cainiao, the typed order-number reply is gone, and the admin gets `MODULE_REJECTED` for a rejected module.
- Deviations from the spec, decided while planning: `CarrierModule.build_client` takes no argument (no module needs settings once Part C is dropped); `CarrierModule.order` sets display order (`/help`, listings); `texts.HELP` gets `{tracked}` and `{link_only}` placeholders filled by `format_help()`.
- Module files must not do I/O at import time. The registry executes the exact bytes it hashed (`compile` + `exec`), which also avoids stale `__pycache__` bytecode after a quick edit.

## File Structure

| File | Responsibility |
|---|---|
| `src/vn_parcel_bot/carriers/api.py` (new) | Module contract: priorities, `Rule`, `CarrierModule` |
| `src/vn_parcel_bot/carriers/registry.py` (new) | Load/validate module files, `CarrierSnapshot`, `CarrierRegistry` (load, refresh), process-wide default |
| `src/vn_parcel_bot/carriers/modules/__init__.py` (new, empty) | Package so tests can import parsers; skipped by the loader |
| `src/vn_parcel_bot/carriers/modules/{spx,jt,cainiao,fourpx,ninjavan,ghn}.py` (moved from `carriers/`) | Parser + client + `MODULE` |
| `src/vn_parcel_bot/carriers/modules/{best,yunexpress,ghtk,viettelpost,vnpost,lex,sf}.py` (new) | Link-only `MODULE` |
| `src/vn_parcel_bot/carriers/models.py` | `CarrierCode = str` |
| `src/vn_parcel_bot/carrier_catalog.py`, `carriers/__init__.py` contents | Deleted / emptied |
| `src/vn_parcel_bot/tracking_codes.py` | Carrier-neutral code handling; `detect_carriers`/`extract_codes` use the snapshot |
| `src/vn_parcel_bot/services/{parcels,poller,formatting}.py`, `bot/{parsing,handlers_user,app,deps}.py`, `texts.py`, `db/{schema,repo}.py`, `constants.py`, `scripts/probe_carriers.py` | Wiring |

---

### Task 1: Module contract and registry (static load)

**Files:**
- Create: `src/vn_parcel_bot/carriers/api.py`, `src/vn_parcel_bot/carriers/registry.py`, `tests/test_module_registry.py`
- Modify: `src/vn_parcel_bot/carriers/models.py:8`, `src/vn_parcel_bot/carriers/common.py:9`

**Interfaces:**
- Produces: `api.Rule(pattern, priority, rank=0, standalone_only=False).matches(code) -> bool`; `api.CarrierModule(code, display_name, rules, order=100, needs_phone=False, link_template=None, examples=(), build_client=..., pending_hint=...)`; `PRIORITY_PREFIXED=100`, `PRIORITY_NUMERIC=60`, `PRIORITY_SHARED_NUMERIC=40`, `PRIORITY_GENERIC=10`.
- Produces: `registry.Detection(candidates: tuple[str, ...] = (), standalone_only: bool = False)`; `LoadedModule(module, client, file_hash, import_name)`; `CarrierSnapshot.of(loaded)`, `.with_clients(clients)`, `.get(code)`, `.ordered()`, `.detect(code)`, `.is_tracked(code)`, `.client(code)`, `.needs_phone(code)`, `.display_name(code)`, `.link(code, tracking_number)`, `.pending_hint(carriers, tracking_number)`, attribute `.clients`; `Rejection(code, file_hash, error)`; `CarrierRegistry(snapshot, directory=None)`, `.current`, `.startup_rejections`, `CarrierRegistry.load(directory=MODULES_DIR)`; `get_registry()`, `set_registry(registry)`, `current_snapshot()`; `MODULES_DIR`; `ModuleLoadError`.

- [ ] **Step 1: Point `CarrierCode` at a plain string**

In `src/vn_parcel_bot/carriers/models.py` replace `from vn_parcel_bot.carrier_catalog import CarrierCode` with nothing and add after the imports:

```python
CarrierCode = str
```

In `src/vn_parcel_bot/carriers/common.py` replace `from vn_parcel_bot.carrier_catalog import CarrierCode` with `from vn_parcel_bot.carriers.models import CarrierCode` (merge with the existing `CarrierError` import: `from vn_parcel_bot.carriers.models import CarrierCode, CarrierError`).

- [ ] **Step 2: Write the failing registry tests**

Create `tests/test_module_registry.py`:

```python
import textwrap

from vn_parcel_bot.carriers.registry import CarrierRegistry, Detection

ALPHA = r'''
from vn_parcel_bot.carriers.api import CarrierModule, Rule

MODULE = CarrierModule(
    code="alpha",
    display_name="Alpha & Co",
    order=1,
    rules=(Rule(r"AL\d{8}", 100), Rule(r"\d{12}", 40, rank=0)),
    link_template="https://alpha.example/track?c={code}",
    examples=(("AL00000001", True),),
)
'''

BETA = r'''
from vn_parcel_bot.carriers.api import CarrierModule, Rule
from vn_parcel_bot.carriers.models import TrackingResult


class BetaCarrier:
    code = "beta"
    display_name = "Beta"
    needs_phone = False

    async def fetch(self, http, tracking_number, phone_last4=None):
        return TrackingResult(carrier="beta", tracking_number=tracking_number, found=False)


def beta_hint(tracking_number):
    return "\nbeta hint" if tracking_number.startswith("BE") else None


MODULE = CarrierModule(
    code="beta",
    display_name="Beta",
    order=2,
    rules=(Rule(r"\d{12}", 40, rank=1), Rule(r"BE[0-9A-Z]{8}", 10, standalone_only=True)),
    examples=(("000000000001", True),),
    build_client=BetaCarrier,
    pending_hint=beta_hint,
)
'''

ZETA = r'''
from vn_parcel_bot.carriers.api import CarrierModule, Rule

MODULE = CarrierModule(
    code="zeta",
    display_name="Zeta",
    order=3,
    rules=(Rule(r"AL\d{8}", 200),),
    link_template="https://zeta.example/",
)
'''


def write(directory, name, source):
    (directory / f"{name}.py").write_text(textwrap.dedent(source), encoding="utf-8")


def load(tmp_path, **sources):
    for name, source in sources.items():
        write(tmp_path, name, source)
    return CarrierRegistry.load(tmp_path)


def test_load_reads_every_module(tmp_path):
    registry = load(tmp_path, alpha=ALPHA, beta=BETA)
    snapshot = registry.current
    assert [module.code for module in snapshot.ordered()] == ["alpha", "beta"]
    assert snapshot.is_tracked("beta")
    assert not snapshot.is_tracked("alpha")
    assert snapshot.client("alpha") is None
    assert snapshot.display_name("alpha") == "Alpha & Co"
    assert snapshot.display_name("gone") == "gone"
    assert not snapshot.needs_phone("gone")
    assert registry.startup_rejections == []


def test_detect_keeps_highest_priority_and_orders_by_rank(tmp_path):
    snapshot = load(tmp_path, alpha=ALPHA, beta=BETA).current
    assert snapshot.detect("AL00000001") == Detection(("alpha",), False)
    assert snapshot.detect("000000000001") == Detection(("alpha", "beta"), False)
    assert snapshot.detect("BE00000001") == Detection(("beta",), True)
    assert snapshot.detect("nothing") == Detection()


def test_links_and_hints(tmp_path):
    snapshot = load(tmp_path, alpha=ALPHA, beta=BETA).current
    assert snapshot.link("alpha", "A#1") == "https://alpha.example/track?c=A%231"
    assert snapshot.link("beta", "X") is None
    assert snapshot.link("gone", "X") is None
    assert snapshot.pending_hint(("alpha", "beta"), "BE00000001") == "\nbeta hint"
    assert snapshot.pending_hint(("alpha",), "BE00000001") is None


def test_with_clients_replaces_clients_only(tmp_path):
    snapshot = load(tmp_path, alpha=ALPHA, beta=BETA).current
    fake = object()
    swapped = snapshot.with_clients({"beta": fake})
    assert swapped.client("beta") is fake
    assert swapped.is_tracked("beta")
    assert swapped.detect("AL00000001") == snapshot.detect("AL00000001")


def test_startup_skips_a_broken_module(tmp_path):
    registry = load(tmp_path, alpha=ALPHA, broken="MODULE = 1 / 0\n")
    assert list(registry.current.modules) == ["alpha"]
    [rejection] = registry.startup_rejections
    assert rejection.code == "broken"
    assert rejection.error == "ZeroDivisionError line 1"


def test_syntax_error_reports_its_line(tmp_path):
    registry = load(tmp_path, broken="x = 1\nMODULE = (\n")
    assert registry.startup_rejections[0].error.startswith("SyntaxError line")


def test_module_code_must_match_file_name(tmp_path):
    registry = load(tmp_path, gamma=ALPHA)
    assert dict(registry.current.modules) == {}
    assert "must equal the file name" in registry.startup_rejections[0].error


def test_link_only_module_needs_https_link(tmp_path):
    registry = load(tmp_path, alpha=ALPHA.replace("https://alpha.example", "http://alpha.example"))
    assert "https link_template" in registry.startup_rejections[0].error


def test_rule_taking_another_carriers_codes_is_rejected(tmp_path):
    registry = load(tmp_path, alpha=ALPHA, zeta=ZETA)
    assert list(registry.current.modules) == ["alpha"]
    [rejection] = registry.startup_rejections
    assert rejection.code == "zeta"
    assert "alpha: example AL00000001" in rejection.error


def test_missing_directory_loads_nothing(tmp_path):
    registry = CarrierRegistry.load(tmp_path / "nope")
    assert dict(registry.current.modules) == {}
```

- [ ] **Step 3: Run to verify it fails**

Run: `.\.venv\Scripts\python -m pytest tests/test_module_registry.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'vn_parcel_bot.carriers.registry'`.

- [ ] **Step 4: Write `carriers/api.py`**

```python
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
```

- [ ] **Step 5: Write `carriers/registry.py`**

```python
import hashlib
import logging
import re
import sys
import traceback
import urllib.parse
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from vn_parcel_bot.carriers.api import CarrierModule
from vn_parcel_bot.carriers.models import Carrier

log = logging.getLogger(__name__)

MODULES_DIR = Path(__file__).parent / "modules"
_CODE_RE = re.compile(r"[a-z0-9]{2,20}", re.ASCII)


class ModuleLoadError(Exception):
    pass


@dataclass(frozen=True)
class Detection:
    candidates: tuple[str, ...] = ()
    standalone_only: bool = False


@dataclass(frozen=True)
class LoadedModule:
    module: CarrierModule
    client: Carrier | None
    file_hash: str
    import_name: str | None = None

    @property
    def tracked(self) -> bool:
        return self.client is not None


@dataclass(frozen=True)
class Rejection:
    code: str
    file_hash: str
    error: str


@dataclass(frozen=True)
class CarrierSnapshot:
    modules: Mapping[str, LoadedModule]
    clients: Mapping[str, Carrier]

    @classmethod
    def of(cls, loaded: Mapping[str, LoadedModule]) -> "CarrierSnapshot":
        clients = {code: item.client for code, item in loaded.items() if item.client is not None}
        return cls(dict(loaded), clients)

    def with_clients(self, clients: Mapping[str, Carrier]) -> "CarrierSnapshot":
        return CarrierSnapshot(self.modules, dict(clients))

    def get(self, code: str) -> CarrierModule | None:
        item = self.modules.get(code)
        return None if item is None else item.module

    def ordered(self) -> list[CarrierModule]:
        return sorted(
            (item.module for item in self.modules.values()), key=lambda m: (m.order, m.code)
        )

    def detect(self, code: str) -> Detection:
        best = -1
        kept: list[tuple[int, str, bool]] = []
        for item in self.modules.values():
            for rule in item.module.rules:
                if not rule.matches(code):
                    continue
                if rule.priority > best:
                    best, kept = rule.priority, []
                if rule.priority == best:
                    kept.append((rule.rank, item.module.code, rule.standalone_only))
        if not kept:
            return Detection()
        kept.sort()
        candidates = tuple(dict.fromkeys(carrier for _, carrier, _ in kept))
        return Detection(candidates, all(flag for _, _, flag in kept))

    def is_tracked(self, code: str) -> bool:
        item = self.modules.get(code)
        return item is not None and item.tracked

    def client(self, code: str) -> Carrier | None:
        return self.clients.get(code)

    def needs_phone(self, code: str) -> bool:
        module = self.get(code)
        return module is not None and module.needs_phone

    def display_name(self, code: str) -> str:
        module = self.get(code)
        return code if module is None else module.display_name

    def link(self, code: str, tracking_number: str) -> str | None:
        module = self.get(code)
        if module is None or module.link_template is None:
            return None
        return module.link_template.replace(
            "{code}", urllib.parse.quote(tracking_number, safe="")
        )

    def pending_hint(self, carriers: Iterable[str], tracking_number: str) -> str | None:
        for code in carriers:
            module = self.get(code)
            hint = None if module is None else module.pending_hint(tracking_number)
            if hint:
                return hint
        return None


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def module_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("*.py") if not path.name.startswith("_"))


def describe_error(exc: BaseException, path: Path) -> str:
    if isinstance(exc, ModuleLoadError):
        return str(exc)
    line = exc.lineno if isinstance(exc, SyntaxError) else None
    if line is None:
        frames = [f for f in traceback.extract_tb(exc.__traceback__) if Path(f.filename) == path]
        line = frames[-1].lineno if frames else None
    return f"{type(exc).__name__} line {line}" if line else type(exc).__name__


def _module_object(module: ModuleType, stem: str) -> CarrierModule:
    carrier = getattr(module, "MODULE", None)
    if not isinstance(carrier, CarrierModule):
        raise ModuleLoadError("MODULE is missing or is not a CarrierModule")
    if carrier.code != stem or not _CODE_RE.fullmatch(carrier.code):
        raise ModuleLoadError(f"code {carrier.code!r} must equal the file name")
    if not carrier.rules:
        raise ModuleLoadError("MODULE has no rules")
    return carrier


def load_module_file(path: Path, data: bytes) -> LoadedModule:
    digest = file_hash(data)
    import_name = f"_vn_parcel_bot_carrier_{path.stem}_{digest[:8]}"
    module = ModuleType(import_name)
    module.__file__ = str(path)
    sys.modules[import_name] = module
    try:
        # Trusted local module file; running the hashed bytes avoids stale bytecode.
        exec(compile(data, str(path), "exec"), module.__dict__)  # noqa: S102
        carrier = _module_object(module, path.stem)
        client = carrier.build_client()
    except Exception as exc:
        sys.modules.pop(import_name, None)
        raise ModuleLoadError(describe_error(exc, path)) from exc
    return LoadedModule(carrier, client, digest, import_name)


def discard(item: LoadedModule | None) -> None:
    if item is not None and item.import_name is not None:
        sys.modules.pop(item.import_name, None)


def validate_snapshot(snapshot: CarrierSnapshot) -> None:
    for item in snapshot.modules.values():
        module = item.module
        if not item.tracked and not (module.link_template or "").startswith("https://"):
            raise ModuleLoadError(f"{module.code}: a link-only module needs an https link_template")
        for example, expected in module.examples:
            detected = module.code in snapshot.detect(example).candidates
            if detected != expected:
                raise ModuleLoadError(f"{module.code}: example {example} detected={detected}")


class CarrierRegistry:
    def __init__(self, snapshot: CarrierSnapshot, directory: Path | None = None) -> None:
        self._current = snapshot
        self._directory = directory
        self._rejected: dict[str, str] = {}
        self.startup_rejections: list[Rejection] = []

    @property
    def current(self) -> CarrierSnapshot:
        return self._current

    @classmethod
    def load(cls, directory: Path = MODULES_DIR) -> "CarrierRegistry":
        registry = cls(CarrierSnapshot.of({}), directory)
        loaded: dict[str, LoadedModule] = {}
        for path in module_files(directory):
            data = path.read_bytes()
            item = None
            try:
                item = load_module_file(path, data)
                validate_snapshot(CarrierSnapshot.of({**loaded, item.module.code: item}))
            except ModuleLoadError as err:
                discard(item)
                registry.startup_rejections.append(
                    registry._reject(path.stem, file_hash(data), str(err))
                )
                continue
            loaded[item.module.code] = item
        registry._current = CarrierSnapshot.of(loaded)
        return registry

    def _reject(self, code: str, digest: str, error: str) -> Rejection:
        self._rejected[code] = digest
        log.warning("carrier module rejected code=%s hash=%s error=%s", code, digest[:8], error)
        return Rejection(code, digest, error)


_DEFAULT: dict[str, CarrierRegistry] = {}


def get_registry() -> CarrierRegistry:
    if "registry" not in _DEFAULT:
        _DEFAULT["registry"] = CarrierRegistry.load()
    return _DEFAULT["registry"]


def set_registry(registry: CarrierRegistry) -> None:
    _DEFAULT["registry"] = registry


def current_snapshot() -> CarrierSnapshot:
    return get_registry().current
```

- [ ] **Step 6: Run to verify it passes**

Run: `.\.venv\Scripts\python -m pytest tests/test_module_registry.py -q`
Expected: 10 passed.

- [ ] **Step 7: Gates and commit**

Run the gates. Commit `src/vn_parcel_bot/carriers/api.py src/vn_parcel_bot/carriers/registry.py src/vn_parcel_bot/carriers/models.py src/vn_parcel_bot/carriers/common.py tests/test_module_registry.py` with message `Add carrier module contract and registry`.

---

### Task 2: Built-in carrier modules

**Files:**
- Move: `src/vn_parcel_bot/carriers/{spx,jt,cainiao,fourpx,ninjavan,ghn}.py` → `src/vn_parcel_bot/carriers/modules/`
- Create: `src/vn_parcel_bot/carriers/modules/__init__.py` (empty), `modules/{best,yunexpress,ghtk,viettelpost,vnpost,lex,sf}.py`, `tests/test_carrier_modules.py`
- Modify: `src/vn_parcel_bot/carriers/__init__.py`, `tests/test_{spx,jt,cainiao,fourpx,ninjavan,ghn}.py` and every other import of the moved modules (`scripts/probe_carriers.py`, `tests/test_fixtures.py`, `tests/test_probe_script.py` if present)

**Interfaces:**
- Consumes: Task 1 `CarrierModule`, `Rule`, priorities, `CarrierRegistry.load()`.
- Produces: 13 modules loaded from `MODULES_DIR`; `modules.jt.CROSS_BORDER_HINT`, `modules.cainiao.LAZADA_HINT`.

- [ ] **Step 1: Write the failing module tests**

Create `tests/test_carrier_modules.py`:

```python
import pytest

from vn_parcel_bot.carriers.registry import CarrierRegistry

ORDER = [
    "spx", "jt", "cainiao", "fourpx", "ninjavan", "ghn",
    "best", "yunexpress", "ghtk", "viettelpost", "vnpost", "lex", "sf",
]


@pytest.fixture(scope="module")
def snapshot():
    registry = CarrierRegistry.load()
    assert registry.startup_rejections == []
    return registry.current


def test_builtin_modules_in_display_order(snapshot):
    assert [module.code for module in snapshot.ordered()] == ORDER


def test_tracked_and_phone_carriers(snapshot):
    tracked = [module.code for module in snapshot.ordered() if snapshot.is_tracked(module.code)]
    assert tracked == ["spx", "jt", "cainiao", "fourpx", "ninjavan", "ghn"]
    assert {module.code for module in snapshot.ordered() if module.needs_phone} == {"jt", "ghn"}


def test_display_names(snapshot):
    assert snapshot.display_name("jt") == "J&T"
    assert snapshot.display_name("lex") == "LEX VN"
    assert snapshot.display_name("fourpx") == "4PX"
    assert snapshot.display_name("sf") == "SF Express"


def test_links(snapshot):
    assert snapshot.link("ghtk", "S123.AB") == "https://i.ghtk.vn/S123.AB"
    assert "YT1%232" in snapshot.link("yunexpress", "YT1#2")
    assert snapshot.link("viettelpost", "123") == "https://viettelpost.com.vn/tra-cuu-hanh-trinh-don/"
    assert snapshot.link("spx", "SPXVN05338454932C") is None


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("SPXVN05338454932C", ["spx"]),
        ("SPEVN000000000001", ["ninjavan"]),
        ("LP00123456789012", ["cainiao"]),
        ("LX123456789CN", ["cainiao"]),
        ("4PX3000123456789CN", ["fourpx"]),
        ("YT1234567890123456", ["yunexpress"]),
        ("YT0000000000001", ["cainiao"]),
        ("SF0000000000001", ["sf"]),
        ("EB123456789VN", ["vnpost"]),
        ("LEXVN00123456", ["lex"]),
        ("S1234567.MB12.D5.123456789", ["ghtk"]),
        ("JNTXB0000000001", ["jt"]),
        ("JNTX0000000001", ["jt"]),
        ("BESTMP0000000001VNA", ["best"]),
        ("BEST0000000001VN", ["best"]),
        ("841000072647", ["jt", "best", "viettelpost"]),
        ("8410000726470", ["best"]),
        ("773440000000001", ["cainiao"]),
        ("500000000000001", ["cainiao"]),
        ("GAN6DKKU12", ["ghn", "ninjavan"]),
    ],
)
def test_detect_each_rule(snapshot, code, expected):
    assert list(snapshot.detect(code).candidates) == expected


@pytest.mark.parametrize(
    "code",
    ["", "AB12", "ABCDEFGH", "12345678", "71426082060", "GAN6DKKU12345678",
     "84000000000001", "94000000000001", "7734400000000011"],
)
def test_detect_no_match(snapshot, code):
    assert snapshot.detect(code).candidates == ()


def test_generic_rule_is_standalone_only(snapshot):
    assert snapshot.detect("GAN6DKKU12").standalone_only
    assert not snapshot.detect("841000072647").standalone_only


def test_pending_hints(snapshot):
    assert "J&amp;T" in snapshot.pending_hint(("jt",), "JNTXB0000000001")
    assert snapshot.pending_hint(("jt",), "841000072647") is None
    assert "app Lazada" in snapshot.pending_hint(("cainiao",), "YT0000000000001")
    assert snapshot.pending_hint(("cainiao",), "LP00000000000001") is None


def test_clients_match_their_modules(snapshot):
    for code, client in snapshot.clients.items():
        module = snapshot.get(code)
        assert (client.code, client.display_name, client.needs_phone) == (
            code, module.display_name, module.needs_phone,
        )
```

- [ ] **Step 2: Run to verify it fails**

Run: `.\.venv\Scripts\python -m pytest tests/test_carrier_modules.py -q`
Expected: FAIL in the fixture (`[module.code ...] == []`, no modules directory yet).

- [ ] **Step 3: Move the six clients**

```powershell
New-Item -ItemType Directory -Force src\vn_parcel_bot\carriers\modules | Out-Null
New-Item -ItemType File src\vn_parcel_bot\carriers\modules\__init__.py | Out-Null
foreach ($name in "spx","jt","cainiao","fourpx","ninjavan","ghn") { git mv "src/vn_parcel_bot/carriers/$name.py" "src/vn_parcel_bot/carriers/modules/$name.py" }
```

In each moved file replace `from vn_parcel_bot.carrier_catalog import CarrierCode` with `from vn_parcel_bot.carriers.models import CarrierCode` (ruff `--fix` merges it with the existing models import).

Replace every import path `vn_parcel_bot.carriers.<name>` (for the six names) with `vn_parcel_bot.carriers.modules.<name>` in `src/`, `tests/` and `scripts/`. Find them with:
`rg -n "vn_parcel_bot\.carriers\.(spx|jt|cainiao|fourpx|ninjavan|ghn)\b" src tests scripts`

`src/vn_parcel_bot/carriers/__init__.py` imports become `from vn_parcel_bot.carriers.modules.cainiao import CainiaoCarrier` etc. (this file is emptied in Task 3).

- [ ] **Step 4: Append `MODULE` to the moved files**

`modules/spx.py` (add `from vn_parcel_bot.carriers.api import PRIORITY_PREFIXED, CarrierModule, Rule` to the imports):

```python
MODULE = CarrierModule(
    code="spx",
    display_name="SPX",
    order=10,
    rules=(Rule(r"SPXVN[0-9A-Z]{8,16}", PRIORITY_PREFIXED),),
    examples=(("SPXVN05338454932C", True), ("SPEVN000000000001", False)),
    build_client=SpxCarrier,
)
```

`modules/jt.py` (add `import re` and `from vn_parcel_bot.carriers.api import PRIORITY_PREFIXED, PRIORITY_SHARED_NUMERIC, CarrierModule, Rule`):

```python
CROSS_BORDER = re.compile(r"JNTX[A-Z]?\d{8,12}", re.ASCII)
CROSS_BORDER_HINT = (
    "\n🌏 Đây là đơn quốc tế của J&amp;T: J&amp;T VN chỉ có dữ liệu sau khi hàng "
    "thông quan về Việt Nam. Trong lúc chờ, bạn xem hành trình trong app Lazada nhé."
)


def cross_border_hint(tracking_number: str) -> str | None:
    return CROSS_BORDER_HINT if CROSS_BORDER.fullmatch(tracking_number) else None


MODULE = CarrierModule(
    code="jt",
    display_name="J&T",
    order=20,
    needs_phone=True,
    rules=(
        Rule(CROSS_BORDER.pattern, PRIORITY_PREFIXED),
        Rule(r"\d{12}", PRIORITY_SHARED_NUMERIC, rank=0),
    ),
    examples=(("JNTXB0000000001", True), ("841000072647", True), ("SPXVN05338454932C", False)),
    build_client=JtCarrier,
    pending_hint=cross_border_hint,
)
```

`modules/cainiao.py` (add `import re` and `from vn_parcel_bot.carriers.api import PRIORITY_NUMERIC, PRIORITY_PREFIXED, CarrierModule, Rule`):

```python
LAZADA_WAYBILL = re.compile(r"YT\d{13}", re.ASCII)
LAZADA_HINT = (
    "\n🌏 Đơn quốc tế Lazada qua Cainiao: Cainiao có thể chưa công bố hành trình ngay. "
    "Trong lúc chờ, bạn xem hành trình trong app Lazada nhé."
)


def lazada_hint(tracking_number: str) -> str | None:
    return LAZADA_HINT if LAZADA_WAYBILL.fullmatch(tracking_number) else None


MODULE = CarrierModule(
    code="cainiao",
    display_name="Cainiao",
    order=30,
    rules=(
        Rule(r"LP\d{14}", PRIORITY_PREFIXED),
        Rule(r"[A-Z]{2}\d{9}CN", PRIORITY_PREFIXED),
        Rule(LAZADA_WAYBILL.pattern, PRIORITY_PREFIXED),
        Rule(r"\d{15}", PRIORITY_NUMERIC),
    ),
    examples=(
        ("LP00123456789012", True),
        ("LX123456789CN", True),
        ("YT0000000000001", True),
        ("773440000000001", True),
        ("YT1234567890123456", False),
    ),
    build_client=CainiaoCarrier,
    pending_hint=lazada_hint,
)
```

`modules/fourpx.py` (import `PRIORITY_PREFIXED, CarrierModule, Rule`):

```python
MODULE = CarrierModule(
    code="fourpx",
    display_name="4PX",
    order=40,
    rules=(Rule(r"4PX[0-9A-Z]{10,20}", PRIORITY_PREFIXED),),
    examples=(("4PX3000123456789CN", True),),
    build_client=FourPxCarrier,
)
```

`modules/ninjavan.py` (import `PRIORITY_GENERIC, PRIORITY_PREFIXED, CarrierModule, Rule`):

```python
MODULE = CarrierModule(
    code="ninjavan",
    display_name="Ninja Van",
    order=50,
    rules=(
        Rule(r"SPEVN[0-9A-Z]{6,20}", PRIORITY_PREFIXED),
        Rule(
            r"(?=[0-9A-Z]*[A-Z])(?=[0-9A-Z]*\d)[0-9A-Z]{8,14}",
            PRIORITY_GENERIC,
            rank=1,
            standalone_only=True,
        ),
    ),
    examples=(("SPEVN000000000001", True), ("GAN6DKKU12", True)),
    build_client=NinjaVanCarrier,
)
```

`modules/ghn.py` (import `PRIORITY_GENERIC, CarrierModule, Rule`):

```python
MODULE = CarrierModule(
    code="ghn",
    display_name="GHN",
    order=60,
    needs_phone=True,
    rules=(
        Rule(
            r"(?=[0-9A-Z]*[A-Z])(?=[0-9A-Z]*\d)[0-9A-Z]{8,14}",
            PRIORITY_GENERIC,
            rank=0,
            standalone_only=True,
        ),
    ),
    examples=(("GAN6DKKU12", True), ("SPXVN05338454932C", False)),
    build_client=GhnCarrier,
)
```

- [ ] **Step 5: Create the link-only modules**

`modules/best.py`:

```python
from vn_parcel_bot.carriers.api import (
    PRIORITY_NUMERIC,
    PRIORITY_PREFIXED,
    PRIORITY_SHARED_NUMERIC,
    CarrierModule,
    Rule,
)

MODULE = CarrierModule(
    code="best",
    display_name="BEST Express",
    order=70,
    rules=(
        Rule(r"BEST[A-Z]{0,6}\d{8,16}VN[A-Z]{0,3}", PRIORITY_PREFIXED),
        Rule(r"\d{13}", PRIORITY_NUMERIC),
        Rule(r"\d{12}", PRIORITY_SHARED_NUMERIC, rank=1),
    ),
    link_template="https://www.best-inc.vn/track?bills={code}",
    examples=(("BESTMP0000000001VNA", True), ("8410000726470", True), ("841000072647", True)),
)
```

`modules/yunexpress.py`:

```python
from vn_parcel_bot.carriers.api import PRIORITY_PREFIXED, CarrierModule, Rule

MODULE = CarrierModule(
    code="yunexpress",
    display_name="YunExpress",
    order=80,
    rules=(Rule(r"YT\d{16}", PRIORITY_PREFIXED),),
    link_template="https://www.yuntrack.com/parcelTracking?id={code}",
    examples=(("YT1234567890123456", True), ("YT0000000000001", False)),
)
```

`modules/ghtk.py`:

```python
from vn_parcel_bot.carriers.api import PRIORITY_PREFIXED, CarrierModule, Rule

MODULE = CarrierModule(
    code="ghtk",
    display_name="GHTK",
    order=90,
    rules=(Rule(r"S\d{5,10}(\.[0-9A-Z]{1,12}){1,4}", PRIORITY_PREFIXED),),
    link_template="https://i.ghtk.vn/{code}",
    examples=(("S1234567.MB12.D5.123456789", True),),
)
```

`modules/viettelpost.py`:

```python
from vn_parcel_bot.carriers.api import PRIORITY_SHARED_NUMERIC, CarrierModule, Rule

MODULE = CarrierModule(
    code="viettelpost",
    display_name="Viettel Post",
    order=100,
    rules=(Rule(r"\d{12}", PRIORITY_SHARED_NUMERIC, rank=2),),
    link_template="https://viettelpost.com.vn/tra-cuu-hanh-trinh-don/",
    examples=(("841000072647", True),),
)
```

`modules/vnpost.py`:

```python
from vn_parcel_bot.carriers.api import PRIORITY_PREFIXED, CarrierModule, Rule

MODULE = CarrierModule(
    code="vnpost",
    display_name="VNPost",
    order=110,
    rules=(Rule(r"[A-Z]{2}\d{9}VN", PRIORITY_PREFIXED),),
    link_template=(
        "https://vnpost.vn/vi/ca-nhan/chuyen-phat/chuyen-phat-trong-nuoc"
        "#!?tab=tra-cuu-hanh-trinh&code={code}"
    ),
    examples=(("EB123456789VN", True),),
)
```

`modules/lex.py`:

```python
from vn_parcel_bot.carriers.api import PRIORITY_PREFIXED, CarrierModule, Rule

MODULE = CarrierModule(
    code="lex",
    display_name="LEX VN",
    order=120,
    rules=(Rule(r"(LEXVN|LXVN|LVS)[0-9A-Z]{6,20}", PRIORITY_PREFIXED),),
    link_template="https://logistics.lazada.vn/",
    examples=(("LEXVN00123456", True),),
)
```

`modules/sf.py`:

```python
from vn_parcel_bot.carriers.api import PRIORITY_PREFIXED, CarrierModule, Rule

MODULE = CarrierModule(
    code="sf",
    display_name="SF Express",
    order=130,
    rules=(Rule(r"SF\d{13}", PRIORITY_PREFIXED),),
    link_template="https://www.sf-express.com/chn/en/waybill/list",
    examples=(("SF0000000000001", True),),
)
```

- [ ] **Step 6: Run to verify it passes**

Run: `.\.venv\Scripts\python -m pytest tests/test_carrier_modules.py tests/test_spx.py tests/test_jt.py tests/test_cainiao.py tests/test_fourpx.py tests/test_ninjavan.py tests/test_ghn.py -q`
Expected: all pass.

- [ ] **Step 7: Gates and commit**

Run the gates (the full suite still uses the old catalog for detection and must stay green). Commit the moved and new module files, `src/vn_parcel_bot/carriers/__init__.py`, the updated test and script imports and `tests/test_carrier_modules.py` with message `Move carriers into self-contained modules`.

---

### Task 3: Core reads carriers from the registry

**Files:**
- Delete: `src/vn_parcel_bot/carrier_catalog.py`, `tests/test_carrier_catalog.py`, `tests/test_carrier_registry.py`
- Modify: `src/vn_parcel_bot/carriers/__init__.py` (empty), `tracking_codes.py`, `services/parcels.py`, `services/poller.py`, `services/formatting.py`, `bot/parsing.py`, `bot/handlers_user.py`, `bot/deps.py`, `bot/app.py`, `db/repo.py:10`, `texts.py`, `scripts/probe_carriers.py`, `tests/fakes.py`, `tests/test_parcels_service.py`, `tests/test_poller.py`, `tests/test_photo_handler.py`, `tests/test_formatting.py`, `tests/test_texts.py`, `tests/test_tracking_codes.py`

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: `ParcelService(repo, registry: CarrierRegistry, http, settings, now)`; `Poller(repo, registry, http, notifier, settings, now, sleep=..., rand=...)`; `fetch_keys(parcel, snapshot: CarrierSnapshot)`; `formatting.format_help()`, `formatting.seventeen_track_url(code)`; `Deps.registry: CarrierRegistry | None = None`; `tests.fakes.fake_registry(clients) -> CarrierRegistry`; `AddKind` without `"order_number"`.

- [ ] **Step 1: Update the tests first**

`tests/fakes.py`: replace the catalog import with `from collections.abc import Mapping` and `from vn_parcel_bot.carriers.registry import CarrierRegistry, current_snapshot`; `CarrierCode` comes from `vn_parcel_bot.carriers.models`. In `FakeCarrier.__init__` replace `info = CATALOG[code]` with:

```python
        info = current_snapshot().get(code)
        assert info is not None, code
```

and append:

```python
def fake_registry(clients: Mapping[str, object]) -> CarrierRegistry:
    return CarrierRegistry(current_snapshot().with_clients(clients))
```

`tests/test_parcels_service.py`: import `fake_registry` from `tests.fakes`; the `service` fixture and the `limited` service become `ParcelService(repo, fake_registry(fakes), None, settings, clock)` / `ParcelService(repo, fake_registry(fakes), None, replace(settings, max_parcels_per_user=2), clock)`. Replace the test asserting `outcome.kind == "order_number"` with:

```python
async def test_add_fifteen_digit_number_is_tracked_as_cainiao(service, user, fakes):
    outcome = await service.add(user, "773440000000001")
    assert outcome.kind == "added"
    assert outcome.parcel.carrier == "cainiao"
    assert fakes["cainiao"].calls == [("773440000000001", None)]
```

`tests/test_poller.py`: import `fake_registry`; `make_poller` returns `Poller(repo, fake_registry(fakes), None, notifier, settings, clock, fake_sleep, lambda: 0.5)`; every `fetch_keys(parcel, fakes)` call becomes `fetch_keys(parcel, fake_registry(fakes).current)`. Add:

```python
async def test_parcel_without_loaded_module_is_skipped_with_warning(poller, repo, caplog):
    caplog.set_level("WARNING")
    await add(repo, "XX0000000001", "oldcarrier")
    report = await poller.run_cycle()
    assert report.fetches == 0
    assert "carrier module missing carrier=oldcarrier parcels=1" in caplog.text
```

(This test needs migration 2 to store `oldcarrier`; mark it `@pytest.mark.skip(reason="needs schema v2, Task 4")` now and remove the mark in Task 4.)

`tests/test_photo_handler.py` `deps` fixture: `registry = fake_registry(carriers)`, `ParcelService(repo, registry, http, settings, lambda: T0)`, `Poller(repo, registry, http, FakeNotifier(), settings, lambda: T0)`.

`tests/test_formatting.py`: delete the lines that build and assert `AddOutcome("order_number", ...)`; import `format_help` and `seventeen_track_url` from `vn_parcel_bot.services.formatting`; add:

```python
def test_seventeen_track_url():
    assert seventeen_track_url("EB123456789VN") == "https://t.17track.net/vi#nums=EB123456789VN"


def test_help_lists_carriers_from_modules():
    text = format_help()
    assert "Tự động theo dõi: SPX, J&amp;T, Cainiao, 4PX, Ninja Van, GHN\n" in text
    assert (
        "Gửi link tra cứu: BEST Express, YunExpress, GHTK, Viettel Post, VNPost, LEX VN, "
        "SF Express\n"
    ) in text
```

`tests/test_texts.py`: delete `from vn_parcel_bot.carrier_catalog import CATALOG` and `test_carrier_names_cover_catalog`.

`tests/test_tracking_codes.py`: remove `is_jt_cross_border`/`is_lazada_cainiao` from the import and delete `test_is_lazada_cainiao` and `test_is_jt_cross_border` (covered by `test_pending_hints` in Task 2); in `test_detect_each_rule` add `("773440000000001", ["cainiao"])`; in `test_detect_no_match` remove `"500000000000001"`.

Delete `tests/test_carrier_catalog.py` and `tests/test_carrier_registry.py` (`git rm`).

- [ ] **Step 2: Run to verify it fails**

Run: `.\.venv\Scripts\python -m pytest -q -x`
Expected: FAIL (`ParcelService` still expects a mapping / `format_help` missing).

- [ ] **Step 3: `tracking_codes.py`**

Delete `_JT_CROSS_BORDER`, `_LAZADA_CAINIAO`, `_RULES`, `_JT_CROSS_BORDER_RE`, `_LAZADA_CAINIAO_RE`, `_match`, `is_jt_cross_border`, `is_lazada_cainiao` and the catalog import. Add `from vn_parcel_bot.carriers.registry import current_snapshot`. Replace `detect_carriers` and `extract_codes` with:

```python
def detect_carriers(code: str) -> list[str]:
    return list(current_snapshot().detect(code).candidates)


def extract_codes(text: str) -> list[str]:
    snapshot = current_snapshot()
    whole = normalize_code(text)
    known: list[str] = []
    fallback: list[str] = []
    for match in _TOKEN.finditer(text):
        code = normalize_code(match.group())
        detection = snapshot.detect(code)
        if (detection.candidates and not (detection.standalone_only and code != whole)) or (
            not detection.candidates and (is_order_number(code) or is_seller_fleet(code))
        ):
            target = known
        elif is_code_like(code):
            target = fallback
        else:
            continue
        if code not in target:
            target.append(code)
    return known or fallback
```

- [ ] **Step 4: `services/parcels.py`**

Imports: drop the catalog import and `is_order_number`; add `from vn_parcel_bot.carriers.models import Carrier, CarrierCode, CarrierError, TrackingEvent, TrackingResult` and `from vn_parcel_bot.carriers.registry import CarrierRegistry, CarrierSnapshot`. Remove `"order_number"` from `AddKind`. Constructor: `registry: CarrierRegistry` replaces `carriers`, stored as `self._registry`. Replace `add` and `_try_candidates`, and give `_store_found`/`_store_pending` a leading `snapshot: CarrierSnapshot` parameter used for `needs_phone`:

```python
    async def add(
        self,
        user: User,
        raw_code: str,
        phone_last4: str | None = None,
        label: str | None = None,
    ) -> AddOutcome:
        snapshot = self._registry.current
        code = normalize_code(raw_code)
        candidates = snapshot.detect(code).candidates
        if not candidates:
            if is_seller_fleet(code):
                kind: AddKind = "seller_fleet"
            elif is_code_like(code):
                kind = "unknown_carrier"
            else:
                return AddOutcome("invalid_code", code=code or None)
            log.info(
                "unrecognised code user=%s kind=%s code=%s length=%s",
                user.telegram_id,
                kind,
                mask_code(code),
                len(code),
            )
            return AddOutcome(kind, code=code)

        tracked = [
            c for c in candidates if snapshot.is_tracked(c) and snapshot.client(c) is not None
        ]
        link_only = tuple(c for c in candidates if not snapshot.is_tracked(c))
        if not tracked and not link_only:
            return AddOutcome("invalid_code", code=code or None)
        if phone_last4 is not None and not is_valid_last4(phone_last4):
            return AddOutcome("invalid_phone", code=code)

        uid = user.telegram_id
        cleaned_label = _clean_label(label)
        if not tracked:
            log.info(
                "link-only code user=%s carriers=%s code=%s",
                uid,
                ",".join(link_only),
                mask_code(code),
            )
            return AddOutcome("link_only", code=code, link_carriers=link_only)
        existing = await self._repo.find_parcel(uid, code)
        if existing is not None:
            if cleaned_label and not existing.label:
                await self._repo.set_label(existing.id, cleaned_label, self._now())
                existing = await self._repo.get_parcel(existing.id)
            log.info("duplicate code user=%s code=%s", uid, mask_code(code))
            return AddOutcome("duplicate", code=code, parcel=existing)
        if await self._repo.count_active_parcels(uid) >= self._settings.max_parcels_per_user:
            return AddOutcome("limit", code=code)

        last4 = phone_last4 or user.default_phone_last4
        tryable = [c for c in tracked if not snapshot.needs_phone(c) or last4]
        phone_missing = tuple(c for c in tracked if snapshot.needs_phone(c) and not last4)

        attempts = await self._try_candidates(snapshot, code, tryable, last4)
        try:
            if attempts:
                winner, outcome = attempts[-1]
                if isinstance(outcome, TrackingResult) and outcome.found:
                    return await self._store_found(
                        snapshot, uid, code, winner, outcome, last4, cleaned_label
                    )
            if phone_missing:
                return AddOutcome("needs_phone", code=code, candidates=phone_missing)
            return await self._store_pending(
                snapshot, uid, code, tracked, attempts, last4, link_only, cleaned_label
            )
        except DuplicateParcelError:
            return AddOutcome("duplicate", code=code)

    async def _try_candidates(
        self,
        snapshot: CarrierSnapshot,
        code: str,
        tryable: Sequence[CarrierCode],
        last4: str | None,
    ) -> list[Attempt]:
        attempts: list[Attempt] = []
        for candidate in tryable:
            client: Carrier | None = snapshot.client(candidate)
            if client is None:
                continue
            digits = last4 if snapshot.needs_phone(candidate) else None
            try:
                result = await client.fetch(self._http, code, digits)
            except CarrierError as err:
                attempts.append((candidate, err))
                continue
            attempts.append((candidate, result))
            if result.found:
                break
        return attempts
```

In `_store_found` use `phone_last4=last4 if snapshot.needs_phone(carrier) else None`; in `_store_pending` use `phone_last4=last4 if any(snapshot.needs_phone(c) for c in tracked) else None`.

- [ ] **Step 5: `services/poller.py`**

Imports: drop the catalog import; `from vn_parcel_bot.carriers.models import CarrierCode, CarrierError, TrackingResult` and `from vn_parcel_bot.carriers.registry import CarrierRegistry, CarrierSnapshot`. Constructor takes `registry: CarrierRegistry` (stored as `self._registry`). Replace `fetch_keys`:

```python
def fetch_keys(parcel: Parcel, snapshot: CarrierSnapshot) -> list[FetchKey]:
    keys = []
    for carrier in parcel.try_order():
        if snapshot.client(carrier) is None:
            continue
        if snapshot.needs_phone(carrier):
            if parcel.phone_last4:
                keys.append(FetchKey(carrier, parcel.tracking_number, parcel.phone_last4))
        else:
            keys.append(FetchKey(carrier, parcel.tracking_number, None))
    return keys
```

At the start of `_cycle` after loading `parcels`:

```python
        snapshot = self._registry.current
        missing: dict[str, int] = {}
        for parcel in parcels:
            if all(snapshot.get(carrier) is None for carrier in parcel.try_order()):
                for carrier in parcel.try_order():
                    missing[carrier] = missing.get(carrier, 0) + 1
        for carrier, count in sorted(missing.items()):
            log.warning("carrier module missing carrier=%s parcels=%d", carrier, count)
```

Use `fetch_keys(parcel, snapshot)`, call `self._fetch_carrier(snapshot, carrier, keys, outcomes, report)`, and in `_fetch_carrier(self, snapshot: CarrierSnapshot, code, keys, outcomes, report)` take `carrier = snapshot.client(code)` followed by `if carrier is None: return`.

- [ ] **Step 6: `services/formatting.py` and `texts.py`**

Imports: drop the catalog block and the `tracking_codes` import; add `import urllib.parse`, `from vn_parcel_bot.carriers.models import CarrierCode, TrackingEvent`, `from vn_parcel_bot.carriers.registry import current_snapshot`. Add and replace:

```python
SEVENTEEN_TRACK_TEMPLATE = "https://t.17track.net/vi#nums={code}"


def seventeen_track_url(code: str) -> str:
    return SEVENTEEN_TRACK_TEMPLATE.replace("{code}", urllib.parse.quote(code, safe=""))


def carrier_name(code: CarrierCode) -> str:
    return _escape(current_snapshot().display_name(code))


def format_links(code: str, carriers: Sequence[CarrierCode]) -> str:
    snapshot = current_snapshot()
    items = []
    for carrier in carriers:
        url = snapshot.link(carrier, code)
        if url is not None:
            items.append(_link_item(url, carrier_name(carrier)))
    items.append(_link_item(seventeen_track_url(code), texts.LINK_17TRACK_NAME))
    return "\n".join(items)


def format_help() -> str:
    snapshot = current_snapshot()
    modules = snapshot.ordered()
    tracked = ", ".join(_escape(m.display_name) for m in modules if snapshot.is_tracked(m.code))
    link_only = ", ".join(
        _escape(m.display_name) for m in modules if not snapshot.is_tracked(m.code)
    )
    return texts.HELP.format(tracked=tracked, link_only=link_only)
```

In `_format_added` replace the phone/JNTX/Lazada block with:

```python
    snapshot = current_snapshot()
    if any(snapshot.needs_phone(code) for code in parcel.candidates):
        text += texts.ADDED_PENDING_PHONE_HINT
    hint = snapshot.pending_hint(parcel.try_order(), parcel.tracking_number)
    if hint:
        text += hint
    return text + _link_extra(outcome)
```

In `format_add_outcome` replace the `needs_phone` case and delete the `order_number` case:

```python
        case "needs_phone":
            asked = texts.ASK_PHONE.format(code=code, carriers=carrier_names(outcome.candidates))
            hint = current_snapshot().pending_hint(outcome.candidates, outcome.code or "")
            return asked + (hint or "")
```

`texts.py`: delete `CARRIER_NAMES`, `ORDER_NUMBER`, `JT_CROSS_BORDER_HINT`, `LAZADA_CAINIAO_HINT`; in `HELP` replace the two carrier lines with `"• Tự động theo dõi: {tracked}\n"` and `"• Gửi link tra cứu: {link_only}\n"`.

- [ ] **Step 7: Bot wiring, repo, script, catalog removal**

- `bot/parsing.py`: replace the catalog import with `from vn_parcel_bot.carriers.registry import current_snapshot`; the phone check becomes `if any(current_snapshot().needs_phone(carrier) for carrier in detect_carriers(rest)):`.
- `bot/handlers_user.py`: import `format_help`; `start` replies `texts.WELCOME.format(...) + "\n\n" + format_help()`; `help_cmd` replies `format_help()`. Check `rg -n "texts\.HELP" src tests` returns only `tests/test_formatting.py`.
- `bot/deps.py`: add `from vn_parcel_bot.carriers.registry import CarrierRegistry` and the field `registry: CarrierRegistry | None = None` after `digests`.
- `bot/app.py`: replace `from vn_parcel_bot.carriers import CARRIERS` with `from vn_parcel_bot.carriers.registry import CarrierRegistry, set_registry`; in `_post_init`:

```python
    registry = CarrierRegistry.load()
    set_registry(registry)
    parcels = ParcelService(repo, registry, http, settings, _utc_now)
    poller = Poller(repo, registry, http, notifier, settings, _utc_now)
```

  and pass `registry=registry` to `Deps(...)`.
- `db/repo.py`: `from vn_parcel_bot.carriers.models import CarrierCode, TrackingEvent`.
- `scripts/probe_carriers.py`: replace `from vn_parcel_bot.carriers import CARRIERS` with `from vn_parcel_bot.carriers.registry import current_snapshot`; in `parse_summary` use `clients = current_snapshot().clients`, `if carrier not in clients:` and `fetcher = clients[carrier]`.
- `git rm src/vn_parcel_bot/carrier_catalog.py`; empty `src/vn_parcel_bot/carriers/__init__.py`.
- `rg -n "carrier_catalog|CARRIERS\b|is_jt_cross_border|is_lazada_cainiao|ORDER_NUMBER|CARRIER_NAMES" src tests scripts` must return nothing.

- [ ] **Step 8: Run to verify it passes**

Run: `.\.venv\Scripts\python -m pytest -q`
Expected: all pass (one skipped: the Task 4 poller test).

- [ ] **Step 9: Gates and commit**

Commit all files above with message `Read carriers from the module registry; 15-digit numbers track as Cainiao`.

---

### Task 4: Schema migration 2

**Files:**
- Modify: `src/vn_parcel_bot/db/schema.py`, `src/vn_parcel_bot/db/repo.py:125-134`, `tests/test_repo.py`, `tests/test_poller.py` (remove the skip mark)

**Interfaces:**
- Produces: `SCHEMA_VERSION = 2`; `migrate(conn, db_path: Path | None = None)`; `backup_target(db_path, version) -> Path | None`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_repo.py` change the user-version assertion in `test_migrate_sets_user_version_and_is_idempotent` to `== 2`, replace `test_carrier_check_constraint` and add the migration tests (add `import asyncio`, `import sqlite3` if missing, `from pathlib import Path`, `from vn_parcel_bot.db.schema import MIGRATIONS`):

```python
async def test_carrier_accepts_any_module_code(repo):
    await make_user(repo)
    parcel = await add(repo)
    await repo._conn.execute("UPDATE parcels SET carrier='newcarrier' WHERE id=?", (parcel.id,))
    await repo._conn.commit()
    assert (await repo.get_parcel(parcel.id)).carrier == "newcarrier"


def make_v1_database(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(MIGRATIONS[0])
    conn.execute("PRAGMA user_version = 1")
    conn.execute(
        "INSERT INTO users (telegram_id, name, is_admin, is_allowed, created_at) "
        "VALUES (1, 'A', 0, 1, '2026-09-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO parcels (id, user_id, carrier, candidates, tracking_number, state, "
        "next_check_at, created_at, updated_at) VALUES (7, 1, 'cainiao', 'cainiao', "
        "'LP00000000000001', 'in_transit', '2026-09-01T00:20:00+00:00', "
        "'2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO events (parcel_id, event_key, event_time, description, created_at) "
        "VALUES (7, 'k1', '2026-09-01T00:05:00+00:00', 'Picked up', '2026-09-01T00:06:00+00:00')"
    )
    conn.commit()
    conn.close()


async def test_migration_2_keeps_rows_and_events(tmp_path):
    path = tmp_path / "old.sqlite3"
    await asyncio.to_thread(make_v1_database, path)
    repo = await Repository.open(path)
    try:
        async with repo._conn.execute("PRAGMA user_version") as cursor:
            assert (await cursor.fetchone())[0] == 2
        parcel = await repo.get_parcel(7)
        assert (parcel.carrier, parcel.tracking_number, parcel.state) == (
            "cainiao",
            "LP00000000000001",
            "in_transit",
        )
        assert [event.description for event in await repo.list_events(7, 10)] == ["Picked up"]
        added = await repo.add_parcel(
            user_id=1,
            carrier="sf",
            candidates=("sf",),
            tracking_number="SF0000000000001",
            phone_last4=None,
            now=T0,
            next_check_at=T0,
        )
        assert added.id == 8
        async with repo._conn.execute("PRAGMA foreign_keys") as cursor:
            assert (await cursor.fetchone())[0] == 1
    finally:
        await repo.close()
    assert await asyncio.to_thread((tmp_path / "old.sqlite3.bak-v1").exists)


async def test_backup_is_not_overwritten(tmp_path):
    path = tmp_path / "old.sqlite3"
    await asyncio.to_thread(make_v1_database, path)
    backup = tmp_path / "old.sqlite3.bak-v1"
    await asyncio.to_thread(backup.write_bytes, b"keep")
    repo = await Repository.open(path)
    await repo.close()
    assert await asyncio.to_thread(backup.read_bytes) == b"keep"


async def test_fresh_database_has_no_backup(tmp_path):
    repo = await Repository.open(tmp_path / "new.sqlite3")
    await repo.close()
    assert not await asyncio.to_thread((tmp_path / "new.sqlite3.bak-v1").exists)
```

(`T0`, `make_user` and `add` already exist in `tests/test_repo.py`; if `T0` is named differently there, use that name.)

In `tests/test_poller.py` remove the `@pytest.mark.skip` from `test_parcel_without_loaded_module_is_skipped_with_warning`.

- [ ] **Step 2: Run to verify it fails**

Run: `.\.venv\Scripts\python -m pytest tests/test_repo.py tests/test_poller.py -q`
Expected: FAIL (user_version 1, CHECK constraint failed).

- [ ] **Step 3: Implement migration 2**

In `db/schema.py`: `SCHEMA_VERSION = 2`, add `from pathlib import Path`, append to `MIGRATIONS`:

```python
    """
BEGIN;
CREATE TABLE parcels_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
  carrier TEXT,
  candidates TEXT NOT NULL CHECK (length(candidates) > 0),
  tracking_number TEXT NOT NULL,
  phone_last4 TEXT CHECK (phone_last4 IS NULL OR phone_last4 GLOB '[0-9][0-9][0-9][0-9]'),
  label TEXT,
  state TEXT NOT NULL DEFAULT 'pending'
    CHECK (state IN ('pending', 'in_transit', 'delivered', 'returned', 'expired', 'stale')),
  last_status_text TEXT,
  last_event_at TEXT,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  next_check_at TEXT NOT NULL,
  delivered_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (carrier IS NOT NULL OR state IN ('pending', 'expired')),
  UNIQUE (user_id, tracking_number)
);
INSERT INTO parcels_new (id, user_id, carrier, candidates, tracking_number, phone_last4, label,
  state, last_status_text, last_event_at, consecutive_failures, next_check_at, delivered_at,
  created_at, updated_at)
SELECT id, user_id, carrier, candidates, tracking_number, phone_last4, label,
  state, last_status_text, last_event_at, consecutive_failures, next_check_at, delivered_at,
  created_at, updated_at FROM parcels;
DELETE FROM sqlite_sequence WHERE name = 'parcels_new';
INSERT INTO sqlite_sequence (name, seq) SELECT 'parcels_new', seq FROM sqlite_sequence
  WHERE name = 'parcels';
DROP TABLE parcels;
ALTER TABLE parcels_new RENAME TO parcels;
CREATE INDEX idx_parcels_due ON parcels (state, next_check_at);
COMMIT;
""",
```

Replace `migrate`:

```python
def backup_target(db_path: Path, version: int) -> Path | None:
    if str(db_path) == ":memory:":
        return None
    target = db_path.with_name(f"{db_path.name}.bak-v{version}")
    return None if target.exists() else target


async def migrate(conn: aiosqlite.Connection, db_path: Path | None = None) -> None:
    async with conn.execute("PRAGMA user_version") as cursor:
        row = await cursor.fetchone()
    current = row[0] if row else 0
    if 0 < current < SCHEMA_VERSION and db_path is not None:
        target = backup_target(db_path, current)
        if target is not None:
            await conn.execute("VACUUM INTO ?", (str(target),))
    for version in range(current, SCHEMA_VERSION):
        await conn.commit()
        await conn.execute("PRAGMA foreign_keys=OFF")
        try:
            await conn.executescript(MIGRATIONS[version])
            async with conn.execute("PRAGMA foreign_key_check") as cursor:
                if await cursor.fetchall():
                    raise RuntimeError(f"foreign key check failed after migration {version + 1}")
            await conn.execute(f"PRAGMA user_version = {version + 1}")
            await conn.commit()
        finally:
            await conn.execute("PRAGMA foreign_keys=ON")
```

In `Repository.open` call `await migrate(conn, path)`.

- [ ] **Step 4: Run to verify it passes**

Run: `.\.venv\Scripts\python -m pytest tests/test_repo.py tests/test_poller.py -q`
Expected: all pass.

- [ ] **Step 5: Gates and commit**

Commit `src/vn_parcel_bot/db/schema.py src/vn_parcel_bot/db/repo.py tests/test_repo.py tests/test_poller.py` with message `Schema v2: drop the carrier CHECK, back up before migrating`.

---

### Task 5: Hot reload

**Files:**
- Modify: `src/vn_parcel_bot/carriers/registry.py`, `src/vn_parcel_bot/bot/app.py`, `src/vn_parcel_bot/constants.py`, `src/vn_parcel_bot/texts.py`, `tests/test_module_registry.py`, `tests/test_scheduling.py`
- Create: `tests/test_carrier_reload.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: `RefreshReport(reloaded: list[str], rejected: list[Rejection])`; `CarrierRegistry.refresh() -> RefreshReport`; `app.carrier_modules_job(context)`; `app.alert_rejections(deps, rejections)`; `constants.MODULE_REFRESH_SECONDS = 30`; `texts.MODULE_REJECTED`.

- [ ] **Step 1: Write the failing registry refresh tests**

Append to `tests/test_module_registry.py`:

```python
def test_refresh_waits_for_two_equal_reads_then_swaps(tmp_path):
    registry = load(tmp_path, alpha=ALPHA)
    write(tmp_path, "alpha", ALPHA.replace("Alpha & Co", "Alpha Two"))
    assert registry.refresh().reloaded == []
    assert registry.current.display_name("alpha") == "Alpha & Co"
    assert registry.refresh().reloaded == ["alpha"]
    assert registry.current.display_name("alpha") == "Alpha Two"
    assert registry.refresh().reloaded == []


def test_refresh_keeps_last_version_when_new_one_fails(tmp_path, caplog):
    registry = load(tmp_path, alpha=ALPHA)
    before = registry.current
    write(tmp_path, "alpha", ALPHA + "\nraise RuntimeError('boom')\n")
    registry.refresh()
    report = registry.refresh()
    assert registry.current is before
    [rejection] = report.rejected
    assert rejection.code == "alpha"
    assert rejection.error.startswith("RuntimeError line")
    assert registry.refresh().rejected == []
    assert registry.refresh().rejected == []
    assert "boom" not in caplog.text


def test_refresh_adds_new_module_and_keeps_deleted_one(tmp_path, caplog):
    registry = load(tmp_path, alpha=ALPHA)
    write(tmp_path, "beta", BETA)
    registry.refresh()
    assert registry.refresh().reloaded == ["beta"]
    assert registry.current.is_tracked("beta")
    (tmp_path / "alpha.py").unlink()
    registry.refresh()
    registry.refresh()
    assert registry.current.get("alpha") is not None
    assert caplog.text.count("carrier module file missing code=alpha") == 1


def test_refresh_rejects_rule_taking_another_carriers_codes(tmp_path):
    registry = load(tmp_path, alpha=ALPHA, beta=BETA)
    stolen = BETA.replace('Rule(r"BE[0-9A-Z]{8}", 10, standalone_only=True)', 'Rule(r"AL\\d{8}", 200)')
    write(tmp_path, "beta", stolen)
    registry.refresh()
    [rejection] = registry.refresh().rejected
    assert "alpha: example AL00000001" in rejection.error
    assert registry.current.detect("AL00000001").candidates == ("alpha",)


def test_broken_module_at_startup_is_added_once_fixed(tmp_path):
    registry = load(tmp_path, alpha=ALPHA, beta="MODULE = 1 / 0\n")
    assert registry.refresh().rejected == []
    write(tmp_path, "beta", BETA)
    registry.refresh()
    assert registry.refresh().reloaded == ["beta"]


def test_static_registry_refresh_does_nothing(tmp_path):
    snapshot = load(tmp_path, alpha=ALPHA).current
    assert CarrierRegistry(snapshot).refresh().reloaded == []
```

Create `tests/test_carrier_reload.py`:

```python
import asyncio
import textwrap
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from tests.fakes import FakeClock, FakeNotifier
from vn_parcel_bot.bot.app import alert_rejections, carrier_modules_job
from vn_parcel_bot.carriers.registry import CarrierRegistry
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.poller import Poller

T0 = datetime(2026, 9, 1, 5, 0, tzinfo=UTC)

TRACKER = r'''
from datetime import UTC, datetime

from vn_parcel_bot.carriers.api import CarrierModule, Rule
from vn_parcel_bot.carriers.models import TrackingEvent, TrackingResult

DESCRIPTION = "version one"


class TrackerCarrier:
    code = "tracker"
    display_name = "Tracker"
    needs_phone = False

    async def fetch(self, http, tracking_number, phone_last4=None):
        event = TrackingEvent(time=datetime(2026, 9, 1, tzinfo=UTC), description=DESCRIPTION)
        return TrackingResult(
            carrier="tracker", tracking_number=tracking_number, found=True, events=(event,)
        )


MODULE = CarrierModule(
    code="tracker",
    display_name="Tracker",
    rules=(Rule(r"TR\d{8}", 100),),
    examples=(("TR00000001", True),),
    build_client=TrackerCarrier,
)
'''


def write(directory, name, source):
    (directory / f"{name}.py").write_text(textwrap.dedent(source), encoding="utf-8")


async def no_sleep(seconds):
    return None


async def test_poller_picks_up_a_reloaded_module(tmp_path, settings):
    modules = tmp_path / "modules"
    await asyncio.to_thread(modules.mkdir)
    await asyncio.to_thread(write, modules, "tracker", TRACKER)
    registry = await asyncio.to_thread(CarrierRegistry.load, modules)
    repo = await Repository.open(tmp_path / "t.sqlite3")
    try:
        await repo.upsert_user(2, now=T0, is_allowed=True)
        await repo.add_parcel(
            user_id=2,
            carrier="tracker",
            candidates=("tracker",),
            tracking_number="TR00000001",
            phone_last4=None,
            now=T0,
            next_check_at=T0,
        )
        clock = FakeClock(T0)
        quiet_free = replace(settings, quiet_hours=None)
        poller = Poller(repo, registry, None, FakeNotifier(), quiet_free, clock, no_sleep, lambda: 0.0)
        await poller.run_cycle()
        await asyncio.to_thread(write, modules, "tracker", TRACKER.replace("version one", "version two"))
        await asyncio.to_thread(registry.refresh)
        await asyncio.to_thread(registry.refresh)
        clock.advance(timedelta(hours=1))
        await poller.run_cycle()
        descriptions = {event.description for event in await repo.list_events(1, 10)}
        assert descriptions == {"version one", "version two"}
    finally:
        await repo.close()


async def test_rejections_alert_admin_once_per_version(tmp_path, settings):
    modules = tmp_path / "modules"
    await asyncio.to_thread(modules.mkdir)
    await asyncio.to_thread(write, modules, "broken", "MODULE = 1 / 0\n")
    registry = await asyncio.to_thread(CarrierRegistry.load, modules)
    repo = await Repository.open(tmp_path / "t.sqlite3")
    notifier = FakeNotifier()
    deps = SimpleNamespace(registry=registry, repo=repo, notifier=notifier, settings=settings)
    context = SimpleNamespace(bot_data={"deps": deps})
    try:
        await alert_rejections(deps, registry.startup_rejections)
        await alert_rejections(deps, registry.startup_rejections)
        assert len(notifier.sent) == 1
        chat_id, text, silent = notifier.sent[0]
        assert chat_id == settings.admin_telegram_id
        assert "<code>broken</code>" in text
        assert "ZeroDivisionError line 1" in text
        assert silent is False
        await asyncio.to_thread(write, modules, "broken", "MODULE = 2 / 0\n")
        await carrier_modules_job(context)
        await carrier_modules_job(context)
        assert len(notifier.sent) == 2
    finally:
        await repo.close()
```

In `tests/test_scheduling.py` import `carrier_modules_job`; the first test's repeating assertion becomes `[(poll_job, "poll"), (carrier_modules_job, "carrier modules")]`, add `assert queue.repeating[1][1]["interval"] == 30`, and the second test asserts `len(queue.repeating) == 2`.

- [ ] **Step 2: Run to verify it fails**

Run: `.\.venv\Scripts\python -m pytest tests/test_module_registry.py tests/test_carrier_reload.py tests/test_scheduling.py -q`
Expected: FAIL (`CarrierRegistry` has no `refresh`; `carrier_modules_job` cannot be imported).

- [ ] **Step 3: Implement refresh in `registry.py`**

Add `from dataclasses import dataclass, field`, then:

```python
@dataclass
class RefreshReport:
    reloaded: list[str] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)
```

In `CarrierRegistry.__init__` add `self._seen: dict[str, str] = {}` and `self._missing: set[str] = set()`. Add the methods:

```python
    def refresh(self) -> RefreshReport:
        report = RefreshReport()
        if self._directory is None:
            return report
        files = {path.stem: path for path in module_files(self._directory)}
        self._warn_missing(files.keys())
        for code, path in sorted(files.items()):
            try:
                data = path.read_bytes()
            except OSError:
                continue
            digest = file_hash(data)
            live = self._current.modules.get(code)
            if (live is not None and live.file_hash == digest) or self._rejected.get(code) == digest:
                self._seen.pop(code, None)
                continue
            if self._seen.get(code) != digest:
                self._seen[code] = digest
                continue
            del self._seen[code]
            self._swap(code, path, data, report)
        return report

    def _warn_missing(self, present: Iterable[str]) -> None:
        missing = set(self._current.modules) - set(present)
        for code in sorted(missing - self._missing):
            log.warning("carrier module file missing code=%s, keeping last version", code)
        self._missing = missing

    def _swap(self, code: str, path: Path, data: bytes, report: RefreshReport) -> None:
        item = None
        try:
            item = load_module_file(path, data)
            candidate = CarrierSnapshot.of({**self._current.modules, code: item})
            validate_snapshot(candidate)
        except ModuleLoadError as err:
            discard(item)
            report.rejected.append(self._reject(code, file_hash(data), str(err)))
            return
        previous = self._current.modules.get(code)
        self._current = candidate
        self._rejected.pop(code, None)
        discard(previous)
        log.info(
            "carrier module reloaded code=%s hash=%s tracked=%s",
            code,
            item.file_hash[:8],
            item.tracked,
        )
        report.reloaded.append(code)
```

- [ ] **Step 4: App job, alert text, constant**

`constants.py`: `MODULE_REFRESH_SECONDS = 30`.

`texts.py` (after `ALERT_ERROR`): `MODULE_REJECTED = "⚠️ Module <code>{code}</code> lỗi, vẫn dùng bản cũ: {error}"`.

`bot/app.py`: add `import asyncio`, `from collections.abc import Sequence`, `from vn_parcel_bot.carriers.registry import CarrierRegistry, Rejection, set_registry`, import `MODULE_REFRESH_SECONDS`; add:

```python
async def alert_rejections(deps: Deps, rejections: Sequence[Rejection]) -> None:
    for rejection in rejections:
        key = f"module-rejected:{rejection.code}"
        if await deps.repo.get_meta(key) == rejection.file_hash:
            continue
        text = texts.MODULE_REJECTED.format(
            code=escape(rejection.code), error=escape(rejection.error)
        )
        try:
            await deps.notifier.send(deps.settings.admin_telegram_id, text, silent=False)
        except Exception:
            log.warning("module rejection alert failed code=%s", rejection.code, exc_info=True)
            continue
        await deps.repo.set_meta(key, rejection.file_hash)


async def carrier_modules_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = get_deps(context)
    if deps.registry is None:
        return
    report = await asyncio.to_thread(deps.registry.refresh)
    await alert_rejections(deps, report.rejected)
```

At the end of `_post_init` (after `app.bot_data["deps"] = ...`): `await alert_rejections(app.bot_data["deps"], registry.startup_rejections)`. In `schedule_jobs` after the poll job:

```python
    job_queue.run_repeating(
        carrier_modules_job,
        interval=MODULE_REFRESH_SECONDS,
        first=MODULE_REFRESH_SECONDS,
        name="carrier modules",
    )
```

- [ ] **Step 5: Run to verify it passes**

Run: `.\.venv\Scripts\python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Gates and commit**

Commit `src/vn_parcel_bot/carriers/registry.py src/vn_parcel_bot/bot/app.py src/vn_parcel_bot/constants.py src/vn_parcel_bot/texts.py tests/test_module_registry.py tests/test_carrier_reload.py tests/test_scheduling.py` with message `Hot-reload carrier modules; alert the admin on a rejected module`.

---

### Task 6: Live rollout and reload drill

**Files:** none changed (the drill edit is reverted).

- [ ] **Step 1: Confirm the bot runs from this checkout**

Run: `.\.venv\Scripts\python -c "import vn_parcel_bot.carriers.registry as r; print(r.MODULES_DIR)"`
Expected: a path under `C:\Users\hozkg\projects\vn-parcel-bot\src\vn_parcel_bot\carriers\modules`.

- [ ] **Step 2: Safe restart**

```powershell
Stop-ScheduledTask -TaskName "VN Parcel Bot"
$procs = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -match 'vn_parcel_bot' })
foreach ($p in $procs) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch {} }
if ($procs.Count -gt 0) { try { Wait-Process -Id $procs.ProcessId -Timeout 20 -ErrorAction Stop } catch {} }
Start-ScheduledTask -TaskName "VN Parcel Bot"
```

Expected in `logs/bot.log`: `bot started as @vn_parcel_hozk_bot`, `Added job "carrier modules"`, no `carrier module rejected`, no traceback. `data/bot.sqlite3.bak-v1` exists and `PRAGMA user_version` of `data/bot.sqlite3` is 2 with the same parcel count as before.

- [ ] **Step 3: Reload drill**

Append the line `# reload drill` to `src/vn_parcel_bot/carriers/modules/sf.py`, wait 70 s, expect `carrier module reloaded code=sf` in the log; run `git checkout -- src/vn_parcel_bot/carriers/modules/sf.py`, wait 70 s, expect a second `carrier module reloaded code=sf`. `git status --short` is clean.

---

### Task 7: Docs

**Files:**
- Modify: `README.md`, `BUILD_PLAN.md`, `SPEC.md` (regenerated), `docs/superpowers/specs/2026-09-14-carrier-modules-design.md`

- [ ] **Step 1: README**

Add a section after the configuration section:

```markdown
## Fixing a carrier while the bot runs

Each carrier is one file in `src/vn_parcel_bot/carriers/modules/` (rules, name, link, notes, example codes and tracking client). Edit the file and save it: within about a minute the bot loads the new version, checks every carrier's example codes and switches over without a restart. If the new version fails, the bot keeps the last working version and sends the admin `⚠️ Module <name> lỗi, vẫn dùng bản cũ: <error>`. Adding a file adds a carrier. Changes to any other file still need a restart.
```

Remove the sentence or table rows that describe the order-number reply for typed 15-digit numbers, if present (`rg -n "order number|mã đơn hàng" README.md`), and state that 15-digit numbers are tracked as Cainiao.

- [ ] **Step 2: BUILD_PLAN 2.0 and SPEC**

With an asserted-replacement script in the scratchpad (every anchor asserted before anything is written):
- Version line `1.8` → `2.0`.
- New `## Changes in 2.0 (2026-09-14)` block above 1.8: carrier modules in `carriers/modules/` with the `api.py` contract, registry snapshot and 30 s hot reload (debounce, example validation, last good version kept, `MODULE_REJECTED` alert); every 15-digit number is Cainiao (rule priority 60) and the `order_number` outcome is removed; schema v2 without the carrier CHECK plus `<db>.bak-v1` backup; `carrier_catalog.py` removed; BEST stays link-only.
- §5.2 rule table replaced by the priority/rank table from the design doc §3.2 (with the file each rule lives in).
- §9.5 `carrier_catalog.py` code block replaced by the `carriers/api.py` contract from Task 1 Step 4.
- The `carrier` CHECK sentence and schema block updated to schema v2.
- Regenerate `SPEC.md` from Part 2 with the header `Generated from BUILD_PLAN.md Part 2 (version 2.0)`.

- [ ] **Step 3: Design doc status**

Status line: `Status: Parts A and B built (<task commits>); Part C dropped`. Add under §2 a "Planning changes" note: `build_client()` takes no argument, `CarrierModule.order`, `format_help()`.

- [ ] **Step 4: Commit**

Commit `README.md BUILD_PLAN.md SPEC.md docs/superpowers/specs/2026-09-14-carrier-modules-design.md docs/superpowers/plans/2026-09-14-carrier-modules.md` with message `Docs 2.0: carrier modules with hot reload`.
