import unittest
from toolvh.oodle import decompress


class OodleTests(unittest.TestCase):
    def test_literal_and_multiple_kraken_blocks(self):
        self.assertEqual(decompress(b'\x4c\x06Hello game', 10), b'Hello game')
        block = 0x40000
        self.assertEqual(decompress(b'\x4c\x06' + b'A' * block + b'\x4c\x06' + b'B' * 10, block + 10), b'A' * block + b'B' * 10)

    def test_invalid_truncated_and_oversized_input(self):
        for data, size in [(b'', 5), (b'bad', 5), (b'\x4c\x06A', 2), (b'\x4c\x06A', 0), (b'x', 64 * 1024 * 1024 + 1)]:
            with self.subTest(data=data, size=size):
                with self.assertRaisesRegex(ValueError, 'Oodle'):
                    decompress(data, size)
