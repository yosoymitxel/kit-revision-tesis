import unittest

from kit.busqueda_web import _canonical_url, _normalizar_resultado, generar_consultas, url_publica_segura


class BusquedaWebTests(unittest.TestCase):
    def test_phrases_are_quoted(self):
        paragraphs = [
            "La arquitectura propuesta establece un mecanismo distribuido para gestionar la trazabilidad de materiales mediante indicadores específicos de circularidad y reglas de intercambio entre los participantes.",
            "El procedimiento incorpora criterios técnicos para evaluar el desempeño ambiental de cada proceso y registrar los cambios en las etapas operativas conforme a las políticas de control y auditoría institucional.",
        ]
        queries = generar_consultas(paragraphs, max_queries=2)
        self.assertGreaterEqual(len(queries), 1)
        self.assertLessEqual(len(queries), 2)
        self.assertTrue(all(item["query"].startswith('"') and item["query"].endswith('"') for item in queries))

    def test_ignores_bibliography_paragraphs(self):
        text = (
            "Referencias bibliográficas con información de fuentes y documentos que no deben "
            "transformarse en consultas públicas porque representan la sección de referencias "
            "del documento académico."
        )
        self.assertEqual(generar_consultas([text]), [])

    def test_canonical_url_removes_tracking(self):
        row = _normalizar_resultado(
            {"url": "https://example.org/paper?utm_source=search#section"},
            "Brave Search",
            "phrase",
        )
        self.assertEqual(row["url"], "https://example.org/paper")

    def test_rejects_private_targets(self):
        self.assertFalse(url_publica_segura("file:///etc/passwd"))
        self.assertFalse(url_publica_segura("http://127.0.0.1:8010/"))
        self.assertFalse(url_publica_segura("http://localhost/"))

    def test_canonical_url(self):
        self.assertEqual(
            _canonical_url("HTTPS://Example.org/path/?fbclid=abc"),
            "https://example.org/path/",
        )


if __name__ == "__main__":
    unittest.main()
