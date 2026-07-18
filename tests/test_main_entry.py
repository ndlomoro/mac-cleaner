import ast
from pathlib import Path


def test_main_is_a_thin_entry_point():
    src = Path("main.py").read_text()
    tree = ast.parse(src)
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert names == {"main"}, f"menu-loop functions still present: {names - {'main'}}"
    assert "CleanerApp" in src
    assert "Prompt.ask" not in src and "console.print" not in src


def test_main_imports():
    import main  # must import cleanly without side effects
    assert callable(main.main)
