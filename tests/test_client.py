import unittest
from pathlib import Path

from rada_raw.client import is_block_page

FIXTURES = Path(__file__).parent / "fixtures"


class BlockPageTest(unittest.TestCase):
    def test_ddos_shield_page_blocks_the_whole_ip(self) -> None:
        self.assertTrue(is_block_page(403, (FIXTURES / "ddos-block-403.html").read_bytes()))

    def test_forbidden_single_document_is_not_a_block(self) -> None:
        self.assertFalse(is_block_page(403, b""))

    def test_ordinary_document_mentioning_ddos_is_not_a_block(self) -> None:
        self.assertFalse(is_block_page(200, "Закон про захист від DDoS-атак".encode()))


if __name__ == "__main__":
    unittest.main()
