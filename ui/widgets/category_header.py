"""[LEVEL] badge + plain-English explanation, straight from the registry."""
from textual.widgets import Static

from core import registry

LEVEL_STYLES = {"SAFE": "green", "CAUTION": "yellow", "RISKY": "red"}


def header_markup(category_key: str) -> str:
    cat = registry.get(category_key)
    style = LEVEL_STYLES[cat.level.value]
    suffix = (" [dim](cleared directly - not recoverable via Trash)[/dim]"
              if not cat.via_trash else "")
    return f"[{style}]\\[{cat.level.value}][/{style}] {cat.explanation}{suffix}"


class CategoryHeader(Static):
    def __init__(self, category_key: str, **kwargs) -> None:
        super().__init__(header_markup(category_key), **kwargs)
        self.category_key = category_key
