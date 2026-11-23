"""Ejecuta copy-spotter sin abrir el navegador."""
import sys
import webbrowser

webbrowser.open = lambda *a, **k: True
webbrowser.open_new_tab = lambda *a, **k: True

from scripts.main import main  # noqa: E402

sys.argv = ["copy-spotter"] + sys.argv[1:]
main()
