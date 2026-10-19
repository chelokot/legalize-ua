import tempfile
import unittest
from pathlib import Path

from rada_raw.dumps import Document, Edition, read_documents, read_editions
from rada_raw.manifest import Manifest, Record, edition_path
from rada_raw.plan import plan

CONSTITUTION = "254к/96-вр"
CABINET_RESOLUTION = "1236-2020-п"
NBU_NOTICE = "n0414500-26"
UNDEFINED_LAW = "1-91"


def write_dumps(directory: Path) -> None:
    documents = [
        f"557794\t{NBU_NOTICE}\tПро облікову ціну банківських металів\t0\t95\t70:20261016:\t\t2\t20261016",
        f"1\t{CONSTITUTION}\tКонституція України\t5\t216|100|1\t1:19960628:254к/96-ВР\t\t2\t19960628",
        f"2\t{CABINET_RESOLUTION}\tПро встановлення карантину\t5\t2|25\t3:20201209:1236\t\t2\t20201209",
        f"3\t{UNDEFINED_LAW}\tЗакон без стану\t0\t1\t1:19910101:1\t\t2\t19910101",
    ]
    editions = [
        "modified\tnreg\ted",
        f"2026-10-01T00:00:00\t{CABINET_RESOLUTION}\t20201209",
        f"2026-10-01T00:00:00\t{CABINET_RESOLUTION}\t20220101",
        f"2026-10-01T00:00:00\t{CABINET_RESOLUTION}\t20270101",
        f"2026-10-01T00:00:00\t{CONSTITUTION}\t20190221",
        f"2026-10-01T00:00:00\t{CONSTITUTION}\t20200101",
        f"2026-10-16T00:00:00\t{NBU_NOTICE}\t20261016",
        f"2026-10-01T00:00:00\t{UNDEFINED_LAW}\t19910101",
        "2026-09-14T11:05:05\t994_049\t1985062322",
        "2026-09-14T11:05:05\t994_050\t20230230",
    ]
    (directory / "doc.txt").write_bytes("\n".join(documents).encode("cp1251"))
    (directory / "doc-update.txt").write_bytes("\n".join(editions).encode("cp1251"))


class DumpsTest(unittest.TestCase):
    def test_reads_documents_and_quarantines_malformed_edition_dates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            write_dumps(Path(directory))
            documents = read_documents(Path(directory))
            editions, malformed = read_editions(Path(directory))
        self.assertEqual(documents[CONSTITUTION], Document(CONSTITUTION, frozenset({"216", "100", "1"}), "5"))
        self.assertEqual(len(editions), 7)
        self.assertEqual([line.split("\t")[2] for line in malformed], ["1985062322", "20230230"])


class PlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        write_dumps(root)
        self.documents = read_documents(root)
        self.editions, _ = read_editions(root)
        self.manifest = Manifest(root / "manifest")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def planned(self) -> list[tuple[str, str]]:
        return [(edition.nreg, edition.date) for edition in plan(self.documents, self.editions, self.manifest, "20261020")]

    def test_core_acts_first_then_current_editions_then_history_and_future(self) -> None:
        self.assertEqual(
            self.planned(),
            [
                (CONSTITUTION, "20190221"),
                (CONSTITUTION, "20200101"),
                (CABINET_RESOLUTION, "20220101"),
                (CABINET_RESOLUTION, "20201209"),
                (CABINET_RESOLUTION, "20270101"),
            ],
        )

    def test_skips_fetched_editions_until_rada_modifies_them(self) -> None:
        self.manifest.put(Record(CONSTITUTION, "20190221", "2026-10-01T00:00:00", 200, "abc", 3, "2026-10-02T00:00:00Z"))
        self.manifest.put(Record(CONSTITUTION, "20200101", "2026-09-01T00:00:00", 200, "def", 3, "2026-09-02T00:00:00Z"))
        self.assertNotIn((CONSTITUTION, "20190221"), self.planned())
        self.assertIn((CONSTITUTION, "20200101"), self.planned())


class ManifestTest(unittest.TestCase):
    def test_round_trips_records_through_sharded_files(self) -> None:
        record = Record(CONSTITUTION, "20200101", "2026-10-01T00:00:00", 200, "abc", 3, "2026-10-02T00:00:00Z")
        with tempfile.TemporaryDirectory() as directory:
            manifest = Manifest(Path(directory))
            manifest.put(record)
            manifest.save()
            self.assertEqual(Manifest(Path(directory)).get(CONSTITUTION, "20200101"), record)

    def test_edition_path_is_ascii_and_reversible(self) -> None:
        path = edition_path(Path("raw"), CONSTITUTION, "20200101")
        self.assertTrue(str(path).isascii())
        self.assertEqual(path.parent.name, "254%D0%BA%2F96-%D0%B2%D1%80")
        self.assertEqual(path.name, "20200101.html")


if __name__ == "__main__":
    unittest.main()
