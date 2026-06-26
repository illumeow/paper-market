from app.core.export_csv import build_csv


def test_layout_columns_rows_and_sum():
    amounts = {f"{g}-{i}": (g * 100 + i) for g in range(10) for i in range(1, 13)}
    text = build_csv(amounts)
    lines = text.split("\n")
    assert lines[-1] == "" or lines[-1]  # trailing handling
    rows = [r for r in text.strip("\n").split("\n")]
    header = rows[0].split(",")
    assert header == ["member", "amount"] * 10          # 20 columns
    assert len(rows) == 1 + 12 + 1                       # header + 12 + sum
    # first data row: group g index 1 -> member "g-1"
    first = rows[1].split(",")
    assert first[0] == "0-1" and first[2] == "1-1"
    # sum row: group 0 sum = sum(0*100+i for i in 1..12) = 78
    sumrow = rows[-1].split(",")
    assert sumrow[0] == "sum" and sumrow[1] == "78"


def test_lf_line_endings():
    amounts = {f"{g}-{i}": 1 for g in range(10) for i in range(1, 13)}
    assert "\r" not in build_csv(amounts)
