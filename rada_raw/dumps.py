import io
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rada_raw.client import RadaClient

DUMPS_PATH = "/ogd/zak/laws/data/csv/"
ARCHIVES = ("doc.zip", "doc-update.zip")
DICTIONARIES = (
    "country.txt", "klasname.txt", "klastree.txt", "koms.txt", "org.txt", "organs.txt", "orgcomp.txt",
    "orggrp.txt", "orggrps.txt", "orgname.txt", "orgvlad.txt", "podia.txt", "pubs.txt", "stan.txt",
    "tags.txt", "temy.txt", "typ.txt", "vidnosh.txt", "vydania.txt",
)
ENCODING = "cp1251"


@dataclass(frozen=True)
class Document:
    nreg: str
    kinds: frozenset[str]
    status: str


@dataclass(frozen=True)
class Edition:
    nreg: str
    date: str
    modified: str


def download(client: RadaClient, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for archive in ARCHIVES:
        with zipfile.ZipFile(io.BytesIO(client.get_ok(DUMPS_PATH + archive))) as bundle:
            for member in bundle.infolist():
                (directory / member.filename).write_bytes(bundle.read(member))
    for dictionary in DICTIONARIES:
        (directory / dictionary).write_bytes(client.get_ok(DUMPS_PATH + dictionary))


def read_documents(directory: Path) -> dict[str, Document]:
    documents = {}
    for line in (directory / "doc.txt").read_bytes().decode(ENCODING).splitlines():
        fields = line.split("\t")
        documents[fields[1]] = Document(nreg=fields[1], kinds=frozenset(fields[4].split("|")), status=fields[3])
    return documents


def read_editions(directory: Path) -> tuple[list[Edition], list[str]]:
    editions = []
    malformed = []
    for line in (directory / "doc-update.txt").read_bytes().decode(ENCODING).splitlines()[1:]:
        fields = line.split("\t")
        if len(fields) == 3 and is_edition_date(fields[2]):
            editions.append(Edition(nreg=fields[1], date=fields[2], modified=fields[0]))
        else:
            malformed.append(line)
    return editions, malformed


def is_edition_date(value: str) -> bool:
    try:
        return datetime.strptime(value, "%Y%m%d").strftime("%Y%m%d") == value
    except ValueError:
        return False
