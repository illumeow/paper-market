#!/usr/bin/env python3
"""One-time generator: assign a unique 4-digit PIN to each of the 120 members.

Members: group 0-9, index 1-12 -> "{group}-{index}" (120 total).
PINs: unique, 4-digit (0000-9999), excluding "obvious" patterns.
Output: CSV with columns member_id,pin (pin zero-padded to 4 chars).

Run once, freeze the output, keep it private (master credential list).
"""
import argparse
import csv
import os
import random

GROUPS = range(10)      # 0..9
INDICES = range(1, 13)  # 1..12


def member_ids():
    return [f"{g}-{i}" for g in GROUPS for i in INDICES]


def is_obvious(n: int) -> bool:
    s = f"{n:04d}"
    if len(set(s)) == 1:                                      # 0000, 1111, ...
        return True
    if all(int(s[i + 1]) - int(s[i]) == 1 for i in range(3)):  # 0123 .. 6789
        return True
    if all(int(s[i]) - int(s[i + 1]) == 1 for i in range(3)):  # 9876 .. 3210
        return True
    if s[0:2] == s[2:4]:                                      # 1212, 3434, ...
        return True
    if s in {"2580", "0852", "1379", "9731"}:                 # keypad lines
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="config/pins.csv")
    ap.add_argument("--seed", type=int, default=None,
                    help="optional RNG seed for reproducible output")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    pool = [n for n in range(10000) if not is_obvious(n)]
    members = member_ids()
    assert len(members) == 120, members
    pins = rng.sample(pool, len(members))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["member_id", "pin"])
        for mid, pin in zip(members, pins):
            w.writerow([mid, f"{pin:04d}"])

    print(f"wrote {len(members)} unique PINs -> {args.out} (pool size {len(pool)})")


if __name__ == "__main__":
    main()
