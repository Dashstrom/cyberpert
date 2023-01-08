import os
import sys
import zipfile
from hashlib import md5
from io import BytesIO
from pathlib import Path, PurePath
from time import sleep
from types import TracebackType
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

import orjson
import requests
from packaging.version import Version
from requests import Response
from tqdm import tqdm
from typing_extensions import Literal, ParamSpec, Protocol

Facts = Dict[str, Union[str, bool, float]]
Condition = Tuple[Any, ...]
Rule = Tuple[Condition, Facts]
R = TypeVar("R")
P = ParamSpec("P")
BLOCK_SIZE = 1 << 20

FMT = "{l_bar}{bar:10}{r_bar}{bar:-10b}"
DATA_PATH = Path(__file__).parent / "data"
CACHE_PATH = DATA_PATH / "cache"
CACHE_DOWNLOAD_PATH = CACHE_PATH / "download"
CACHE_FUNCTION_PATH = CACHE_PATH / "function"
RULES_PATH = DATA_PATH / "rules"
try:
    os.get_terminal_size()
    PIPED = False
except OSError:
    PIPED = True


def ftqdm(
    obj: Optional[R] = None,
    desc: Optional[str] = None,
    total: Optional[float] = None,
    smoothing: float = 0.1,
    unit_scale: bool = False,
    position: int = 0,
    unit: str = "it",
) -> R:
    return tqdm(  # type: ignore
        obj,  # type: ignore
        desc=desc,
        file=sys.stdout,
        bar_format=FMT,
        total=total,
        unit=unit,
        unit_scale=unit_scale,
        smoothing=smoothing,
        position=position,
        disable=PIPED,
    )


class SupportRead(Protocol):
    def read(self, n: int) -> bytes:
        ...


class SupportWrite(Protocol):
    def write(self, buffer: Any) -> Any:
        ...


class TqdmIO:
    """Writer and Reader with tqdm."""

    def __init__(self, name: str = "stream") -> None:
        self.progressbar: Any = ftqdm(unit="B", unit_scale=True)
        self._text = "Inithialize"
        self.name(name)

    def _update(self) -> None:
        self.progressbar.set_description(f"{self._text} ({self._name})")
        self.progressbar.refresh()

    def desc(self, text: str) -> None:
        """Set description"""
        self._text = text
        self._update()

    def name(self, name: str) -> None:
        """Set name."""
        self._name = name
        self._update()

    def close(self) -> None:
        """Close the progress bar."""
        self.desc("Complete")
        sleep(0.05)
        self.progressbar.close()

    def __enter__(self) -> "TqdmIO":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Literal[False]:
        self.close()
        return False

    def write_io(
        self,
        io: SupportWrite,
        data: bytes,
        action: str = "Write",
    ) -> None:
        """Write to a stream."""
        self.progressbar.reset(total=len(data))
        self.desc(action)
        view = memoryview(data)
        for i in range(0, len(view), BLOCK_SIZE):
            block = view[i : i + BLOCK_SIZE]  # noqa
            self.progressbar.update(len(block))
            io.write(block)
        self.progressbar.close()

    def write_zip(
        self, path: Path, data: bytes, compression: int = zipfile.ZIP_DEFLATED
    ) -> None:
        self.desc("Create dir")
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression) as archive:
            with archive.open(path.stem, mode="w") as file:
                self.write_io(file, data)

    def write_jsonzip(
        self, path: Path, obj: Any, compression: int = zipfile.ZIP_DEFLATED
    ) -> None:
        self.desc("Serialize")
        data = orjson.dumps(obj)
        return self.write_zip(path, data, compression)

    def read_io(
        self,
        io: Union[SupportRead, Response],
        size: Optional[float] = None,
        action: str = "Read",
    ) -> bytes:
        """Read from a stream."""
        self.progressbar.reset(total=size)
        self.desc(action)
        morsels = []
        if isinstance(io, Response):
            for block in io.iter_content(BLOCK_SIZE):
                morsels.append(block)
                self.progressbar.update(len(block))
        else:
            while True:
                block = io.read(BLOCK_SIZE)
                if not block:
                    break
                morsels.append(block)
                self.progressbar.update(len(block))
        data = b"".join(morsels)
        return data

    def read_zip(self, path: Union[PurePath, SupportRead]) -> bytes:
        if isinstance(path, PurePath):
            archive_size: Optional[int] = os.stat(path).st_size
            archive_file: SupportRead = open(path, "rb")
        else:
            try:
                archive_size = path.getbuffer().nbytes  # type: ignore
            except AttributeError:
                archive_size = None
            archive_file = path
        try:
            archive_bytes = self.read_io(archive_file, size=archive_size)
            archive_data = BytesIO(archive_bytes)
            self.desc("Uncompress")
            with zipfile.ZipFile(archive_data, "r") as archive:
                zipinfo = archive.infolist()[0]
                name = zipinfo.filename
                size = zipinfo.file_size
                with archive.open(name) as jsonfile:
                    return self.read_io(
                        jsonfile, size=size, action="Read file"
                    )
        finally:
            if isinstance(path, PurePath):
                archive_file.close()  # type: ignore

    def read_jsonzip(self, path: Union[PurePath, SupportRead]) -> Any:
        data = self.read_zip(path)
        self.desc("Deserialize")
        return orjson.loads(data)

    def download_file(self, url: str) -> bytes:
        name = url.rsplit("/", 1)[-1]
        self.name(name)
        path = CACHE_DOWNLOAD_PATH / md5(url.encode("utf8")).hexdigest()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            total_size_in_bytes = path.stat().st_size
            with path.open("rb") as file:
                data = self.read_io(file, size=total_size_in_bytes)
        except FileNotFoundError:
            r_file = requests.get(url=url, stream=True, timeout=10)
            r_file.raise_for_status()
            total_size_in_bytes = int(r_file.headers.get("content-length", 0))
            data = self.read_io(r_file, size=total_size_in_bytes)
            with path.open("wb") as file:
                self.write_io(file, data)
        return data

    def download_zip(self, url: str) -> bytes:
        result = self.download_file(url)
        data = BytesIO(result)
        return self.read_zip(data)


_cach_path: Dict[Path, Any] = {}


def cache_json_zip(func: Callable[[], R]) -> Callable[[], R]:
    """Use zipped json for cache function."""

    def wrapper() -> R:
        name = func.__name__ + ".json.zip"
        name = name.replace("_", "-")
        path = CACHE_FUNCTION_PATH / name
        try:
            obj = _cach_path[path]
        except KeyError:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                with TqdmIO(path.name) as io:
                    obj = _cach_path[path] = io.read_jsonzip(path)
            else:
                obj = _cach_path[path] = func()
                with TqdmIO(path.name) as io:
                    io.write_jsonzip(path, obj)
        return cast(R, obj)

    return wrapper


_version_cache: Dict[str, Version] = {}


def ver(version: str) -> Version:
    """Make best effort for return a comparable version."""
    try:
        _ver = _version_cache[version]
    except KeyError:
        _ver = Version(version)
        _version_cache[version] = _ver
    return _ver


def ranges_versions(
    name: str, match_versions: Iterable[str], all_versions: Iterable[str]
) -> Condition:
    """Convert two set of versions into range conditions."""
    package_versions = sorted(all_versions, key=ver)
    set_vulnerable_versions = set(match_versions)
    ranges: List[Any] = []
    bottom: Optional[str] = None
    for package_version in package_versions:
        if package_version in set_vulnerable_versions:
            if not bottom:
                bottom = package_version
        else:
            if bottom:
                if ranges:
                    ranges.append("or")
                ranges.append(
                    (
                        (name, ">=~", bottom),
                        "and",
                        (name, "<~", package_version),
                    )
                )
                bottom = None
    if bottom:
        if ranges:
            ranges.append("or")
        ranges.append((name, ">=~", bottom))
    if len(ranges) == 1:
        ranges = ranges[0]
    return tuple(ranges)
