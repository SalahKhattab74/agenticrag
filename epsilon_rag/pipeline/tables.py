"""Table helpers for the PDF extraction pipeline.

Docling's TableFormer stage gives the layout layer a row-major cell grid:

    [["Name", "Score"], ["Omar", "98"]]

The ingest orchestrator embeds table content as GitHub-flavoured Markdown so
the table survives chunking and retrieval as readable text:

    | Name | Score |
    | --- | --- |
    | Omar | 98 |

This module deliberately has no database or model dependencies; it is called
inside per-region processing, so failures here should be rare, predictable,
and easy to reason about.
"""
from __future__ import annotations

from collections.abc import Iterable


def grid_to_markdown(rows: list[list[str]] | Iterable[Iterable[object]] | None) -> str:
    """Convert a row-major table grid to GitHub-flavoured Markdown.

    Args:
        rows: Iterable of table rows. Cells may be any object; they are coerced
            to strings. Ragged rows are padded to the widest row.

    Returns:
        A Markdown table string, or "" when there are no non-empty cells.

    Notes:
        - Markdown pipes inside cells are escaped.
        - Newlines inside cells are collapsed to spaces.
        - A one-row table is treated as a header-only table, which is valid GFM
          and keeps the extracted content searchable.
    """
    normalised = _normalise_rows(rows)
    if not normalised:
        return ""

    width = max(len(row) for row in normalised)
    if width == 0:
        return ""

    padded = [row + [""] * (width - len(row)) for row in normalised]
    if not any(cell.strip() for row in padded for cell in row):
        return ""

    header = padded[0]
    body = padded[1:]

    lines = [
        _format_row(header),
        _format_row(["---"] * width),
    ]
    lines.extend(_format_row(row) for row in body)
    return "\n".join(lines)


def _normalise_rows(rows: list[list[str]] | Iterable[Iterable[object]] | None) -> list[list[str]]:
    if rows is None:
        return []

    out: list[list[str]] = []
    for row in rows:
        cells = [_clean_cell(cell) for cell in row] if row is not None else []
        # Keep empty rows only if they are part of a non-empty table; they can
        # represent deliberate spacing or missing values in extracted grids.
        out.append(cells)

    # Trim leading/trailing rows that are completely empty. Interior empty rows
    # are retained because they may map to blank rows in the source table.
    while out and not any(cell.strip() for cell in out[0]):
        out.pop(0)
    while out and not any(cell.strip() for cell in out[-1]):
        out.pop()
    return out


def _clean_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    text = " ".join(text.replace("\r", "\n").split())
    return text.replace("\\", "\\\\").replace("|", "\\|")


def _format_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


__all__ = ["grid_to_markdown"]
