import unittest

from kit.fuentes_academicas import (
    _nested_doi,
    _nested_urls,
    _split_endpoints,
    parsear_resultados_lareferencia,
)


class FuentesAcademicasTests(unittest.TestCase):
    def test_split_oai_endpoints(self):
        self.assertEqual(
            _split_endpoints(" https://repo-a/oai ;https://repo-b/oai;https://repo-a/oai "),
            ["https://repo-a/oai", "https://repo-b/oai"],
        )

    def test_parse_lareferencia_vufind_records(self):
        markup = """
        <div class="result">
          <h2><a href="/vufind/Record/abc">Tesis de políticas públicas</a></h2>
          <div class="summary">Investigación sobre gestión pública en América Latina.</div>
          <a href="/files/tesis.pdf">PDF</a>
        </div>
        """
        records = parsear_resultados_lareferencia(markup)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "Tesis de políticas públicas")
        self.assertIn("/vufind/Record/abc", records[0]["url"])
        self.assertIn("gestión pública", records[0]["abstract"])
        self.assertTrue(records[0]["fulltext_url"].endswith("tesis.pdf"))

    def test_extract_openaire_urls_and_doi(self):
        sample = {
            "instances": [{"webresources": [{"url": "https://repo.example/documento.pdf"}]}],
            "pids": [{"type": "doi", "value": "10.1234/abc"}],
        }
        self.assertEqual(_nested_urls(sample["instances"]), ["https://repo.example/documento.pdf"])
        self.assertEqual(_nested_doi(sample["pids"]), "10.1234/abc")


if __name__ == "__main__":
    unittest.main()
