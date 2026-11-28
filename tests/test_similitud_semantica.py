import unittest

from kit.similitud_semantica import segmentar, _sample_evenly


class SimilitudSemanticaTests(unittest.TestCase):
    def test_segmentar_creates_overlapping_chunks(self):
        words = [f"palabra{index}" for index in range(230)]
        chunks = segmentar(" ".join(words), words_per_chunk=90, overlap=40)
        self.assertGreaterEqual(len(chunks), 3)
        self.assertGreater(len(set(chunks)), 1)
        self.assertGreaterEqual(len(chunks[0].split()), 35)

    def test_sample_evenly_keeps_document_coverage(self):
        values = [str(index) for index in range(100)]
        sampled = _sample_evenly(values, 10)
        self.assertEqual(len(sampled), 10)
        self.assertEqual(sampled[0], "0")
        self.assertEqual(sampled[-1], "99")


if __name__ == "__main__":
    unittest.main()
