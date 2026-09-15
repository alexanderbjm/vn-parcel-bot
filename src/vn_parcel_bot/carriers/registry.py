import hashlib
import logging
import re
import sys
import traceback
import urllib.parse
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from vn_parcel_bot.carriers.api import CarrierModule
from vn_parcel_bot.carriers.models import Carrier, TrackingResult

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


@dataclass
class RefreshReport:
    reloaded: list[str] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)


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
        return module.link_template.replace("{code}", urllib.parse.quote(tracking_number, safe=""))

    def progress(self, carrier: str, result: TrackingResult) -> int | None:
        module = self.get(carrier)
        if module is None or not result.found or result.returned:
            return None
        if result.delivered:
            return 100
        try:
            value = module.progress(result)
        except Exception as exc:
            log.warning("carrier progress failed carrier=%s type=%s", carrier, type(exc).__name__)
            return None
        return None if value is None else max(0, min(100, int(value)))

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
            if expected and module.code_lengths and len(example) not in module.code_lengths:
                raise ModuleLoadError(
                    f"{module.code}: example {example} has length {len(example)}, "
                    "not one of code_lengths"
                )


class CarrierRegistry:
    def __init__(self, snapshot: CarrierSnapshot, directory: Path | None = None) -> None:
        self._current = snapshot
        self._directory = directory
        self._rejected: dict[str, str] = {}
        self.startup_rejections: list[Rejection] = []
        self._seen: dict[str, str] = {}
        self._missing: set[str] = set()

    @property
    def current(self) -> CarrierSnapshot:
        return self._current

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
            if (live is not None and live.file_hash == digest) or self._rejected.get(
                code
            ) == digest:
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
