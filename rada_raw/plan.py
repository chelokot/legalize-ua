from rada_raw.dumps import Document, Edition
from rada_raw.manifest import Manifest

CORE_KINDS = frozenset({"100", "216", "21", "124", "1"})
NORMATIVE_KINDS = CORE_KINDS | {"2", "3", "6", "8", "9", "16", "17", "20", "22", "29", "64"}
NON_NORMATIVE_KINDS = frozenset({"15", "95", "96", "175", "184", "215"})
UNDEFINED_STATUS = "0"


def in_scope(document: Document) -> bool:
    return (
        document.status != UNDEFINED_STATUS
        and bool(document.kinds & NORMATIVE_KINDS)
        and not document.kinds & NON_NORMATIVE_KINDS
    )


def plan(documents: dict[str, Document], editions: list[Edition], manifest: Manifest, today: str) -> list[Edition]:
    scoped = [edition for edition in editions if edition.nreg in documents and in_scope(documents[edition.nreg])]
    current: dict[str, str] = {}
    for edition in scoped:
        if edition.date <= today and edition.date > current.get(edition.nreg, ""):
            current[edition.nreg] = edition.date

    def priority(edition: Edition) -> tuple[int, str, str]:
        if documents[edition.nreg].kinds & CORE_KINDS:
            tier = 0
        elif current.get(edition.nreg) == edition.date:
            tier = 1
        else:
            tier = 2
        return tier, edition.nreg, edition.date

    stale = [edition for edition in scoped if is_stale(edition, manifest)]
    return sorted(stale, key=priority)


def is_stale(edition: Edition, manifest: Manifest) -> bool:
    record = manifest.get(edition.nreg, edition.date)
    return record is None or record.modified != edition.modified
