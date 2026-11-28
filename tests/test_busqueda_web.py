import unittest
from unittest.mock import patch

from kit.busqueda_web import (
    _canonical_url,
    _consultar,
    _normalizar_resultado,
    generar_consultas,
    url_publica_segura,
)


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

    def test_fallback_query_uses_distinctive_terms(self):
        paragraph = (
            "La arquitectura distribuida permite gestionar trazabilidad de materiales mediante "
            "indicadores específicos de circularidad y reglas de intercambio entre participantes "
            "institucionales durante procedimientos técnicos verificables."
        )
        query = generar_consultas([paragraph], max_queries=1)[0]
        self.assertFalse(query["fallback_query"].startswith('"'))
        self.assertGreaterEqual(len(query["fallback_query"].split()), 4)
        self.assertLessEqual(len(query["fallback_query"].split()), 7)

    def test_large_document_gets_adaptive_query_count(self):
        paragraphs = []
        for index in range(1500):
            words = [f"dato{index}campo{n}" for n in range(30)]
            paragraphs.append(" ".join(words) + ".")
        queries = generar_consultas(paragraphs)
        self.assertGreaterEqual(len(queries), 90)
        self.assertLessEqual(len(queries), 120)

    def test_searxng_falls_back_when_exact_phrase_has_no_results(self):
        queries = [{
            "phrase": "frase original",
            "query": '"frase original"',
            "fallback_query": "terminos distintivos busqueda abierta",
        }]
        fallback_result = [{"url": "https://example.org/documento", "title": "Documento"}]
        with patch("kit.busqueda_web._buscar_searxng", side_effect=[
            ([], []),
            (fallback_result, []),
        ]) as mocked:
            rows, stats = _consultar("SearXNG", queries, base="http://localhost:8888")
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(stats["consultas_fallback"], 1)
        self.assertEqual(stats["estado"], "activo")

    def test_zero_results_are_not_reported_as_active(self):
        queries = [{
            "phrase": "frase original",
            "query": '"frase original"',
            "fallback_query": "terminos distintivos busqueda abierta",
        }]
        with patch("kit.busqueda_web._buscar_searxng", return_value=([], [])):
            rows, stats = _consultar("SearXNG", queries, base="http://localhost:8888")
        self.assertEqual(rows, [])
        self.assertEqual(stats["estado"], "sin_resultados")
        self.assertEqual(stats["consultas_sin_resultados"], 1)

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
