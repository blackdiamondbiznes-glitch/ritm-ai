"""Spreadsheet cells that look like formulas are prefixed, not executed."""

import csv
import io

from app.services.csv_export import _csv


def test_formula_cells_are_prefixed() -> None:
    body = _csv(
        ["name"],
        [["=1+1"], ["+cmd"], ["-1"], ["@sum"], ["\t=1"], ["\r=1"], ["Ali"], [12]],
    )
    rows = list(csv.reader(io.StringIO(body.decode("utf-8-sig"))))
    assert rows[0] == ["name"]
    assert rows[1:] == [
        ["'=1+1"],
        ["'+cmd"],
        ["'-1"],
        ["'@sum"],
        ["'\t=1"],
        ["'\r=1"],
        ["Ali"],
        ["12"],
    ]
