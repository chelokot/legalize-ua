import hashlib
from dataclasses import astuple, dataclass
from pathlib import Path
from urllib.parse import quote

HEADER = "nreg\tdate\tmodified\tstatus\tsha256\tsize\tfetched_at"


@dataclass(frozen=True)
class Record:
    nreg: str
    date: str
    modified: str
    status: int
    sha256: str
    size: int
    fetched_at: str

    @classmethod
    def parse(cls, line: str) -> "Record":
        nreg, date, modified, status, sha256, size, fetched_at = line.split("\t")
        return cls(nreg, date, modified, int(status), sha256, int(size), fetched_at)

    def line(self) -> str:
        return "\t".join(str(value) for value in astuple(self))


def shard(nreg: str) -> str:
    return hashlib.sha1(nreg.encode()).hexdigest()[:2]


def edition_path(root: Path, nreg: str, date: str) -> Path:
    return root / "docs" / shard(nreg) / quote(nreg, safe="") / f"{date}.html"


class Manifest:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._shards: dict[str, dict[tuple[str, str], Record]] = {}
        self._dirty: set[str] = set()
        for path in sorted(directory.glob("*.tsv")):
            records = (Record.parse(line) for line in path.read_text(encoding="utf-8").splitlines()[1:])
            self._shards[path.stem] = {(record.nreg, record.date): record for record in records}

    def get(self, nreg: str, date: str) -> Record | None:
        return self._shards.get(shard(nreg), {}).get((nreg, date))

    def put(self, record: Record) -> None:
        key = shard(record.nreg)
        self._shards.setdefault(key, {})[(record.nreg, record.date)] = record
        self._dirty.add(key)

    def save(self) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        for key in sorted(self._dirty):
            records = sorted(self._shards[key].values(), key=lambda record: (record.nreg, record.date))
            lines = [HEADER, *(record.line() for record in records)]
            (self._directory / f"{key}.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._dirty.clear()
