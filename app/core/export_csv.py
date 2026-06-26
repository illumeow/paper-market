GROUPS = range(10)
INDICES = range(1, 13)


def build_csv(amounts: dict) -> str:
    lines = [",".join(["member", "amount"] * len(GROUPS))]
    for i in INDICES:
        cells = []
        for g in GROUPS:
            mid = f"{g}-{i}"
            cells += [mid, str(amounts[mid])]
        lines.append(",".join(cells))
    sums = []
    for g in GROUPS:
        total = sum(amounts[f"{g}-{i}"] for i in INDICES)
        sums += ["sum", str(total)]
    lines.append(",".join(sums))
    return "\n".join(lines) + "\n"
