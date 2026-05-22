"""
SIC/XE Assembler — Pass 1
Responsibilities:
  - Track Location Counter (LC) per block
  - Populate Symbol Table  → symbTable.txt
  - Populate Pool Table    → PoolTable.txt
  - Populate Block Table   → blockTable.txt
  - Halt + write error.txt on any fatal error
"""

import re
import os
from optab import (
    OPTAB, VALID_BLOCKS, DIRECTIVES_NO_CODE,
    parse_line, byte_size, pool_literal_size, instr_size,
)

# ---------------------------------------------------------------------------
# POOL detector — is this operand a pooled literal?
# ---------------------------------------------------------------------------
POOL_PATTERN = re.compile(r"^&", re.IGNORECASE)

def is_pool_operand(operand: str) -> bool:
    return bool(POOL_PATTERN.match(operand))

def pool_key(operand: str) -> str:
    """Canonical key for a pool entry (strip & and normalise)."""
    return operand.lstrip("&").upper()


# ---------------------------------------------------------------------------
# Error helper — writes error.txt and raises to halt execution
# ---------------------------------------------------------------------------
def fatal_error(message: str, pc: int):
    with open("error.txt", "w") as f:
        f.write(f"ERROR: {message}\n")
        f.write(f"PC: {pc:06X}\n")
    raise SystemExit(f"[FATAL] {message}  (PC={pc:06X}) — see error.txt")


# ---------------------------------------------------------------------------
# Pool value size (kept for backward compat, delegates to optab)
# ---------------------------------------------------------------------------
def _pool_value_size(operand: str) -> int:
    """
    POOL entries store the raw numeric value of &-prefixed operands.
    Size is always one word (3 bytes) for SIC/XE.
    Extend here if your spec differs.
    """
    return pool_literal_size(operand)


# ---------------------------------------------------------------------------
# Pass 1 — main entry point
# ---------------------------------------------------------------------------
def pass1(input_file: str = "in.txt"):
    """
    Reads input_file and produces:
      symbTable.txt   — symbol → (block, LC_in_block)
      PoolTable.txt   — pool_key → (block=POOL, LC_in_POOL)
      blockTable.txt  — block_name → start_address, length
    """

    # ── State ───────────────────────────────────────────────────────────────
    # LC per block (absolute within block, starts at 0)
    block_lc: dict[str, int] = {b: 0 for b in VALID_BLOCKS}

    # Current active block (changed by USE directive)
    current_block = "DEFAULT"

    # Symbol table: symbol → {"block": str, "lc": int}
    symb_table: dict[str, dict] = {}

    # Pool table: pool_key → {"block": "POOL", "lc": int}
    pool_table: dict[str, dict] = {}

    # Track insertion order for POOL
    pool_order: list[str] = []

    # Starting block LCs (we may need them for absolute addresses later)
    # We'll compute final block starts in block_table after pass 1.
    block_start: dict[str, int] = {b: 0 for b in VALID_BLOCKS}

    program_name = ""
    program_start_lc = 0
    found_start = False

    # ── Read & process ───────────────────────────────────────────────────────
    try:
        with open(input_file, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        fatal_error(f"Input file '{input_file}' not found.", 0)

    for lineno, raw in enumerate(lines, start=1):
        parsed = parse_line(raw)
        if parsed is None:
            continue

        label, opcode, operand = parsed

        # Current LC for this line (before advancing)
        lc_now = block_lc[current_block]

        # ── Handle directives ────────────────────────────────────────────────

        # START
        if opcode == "START":
            program_name = label
            try:
                start_addr = int(operand, 16) if operand else 0
            except ValueError:
                fatal_error(f"Invalid START address '{operand}'", lc_now)
            block_lc["DEFAULT"] = start_addr
            block_start["DEFAULT"] = start_addr
            program_start_lc = start_addr
            found_start = True
            continue

        # END — stop Pass 1
        if opcode == "END":
            break

        # USE — switch active block
        if opcode == "USE":
            new_block = operand if operand else "DEFAULT"
            if new_block not in VALID_BLOCKS:
                fatal_error(f"Unidentified block name: '{new_block}'", lc_now)
            current_block = new_block
            continue

        # EQU — symbol defined as expression (simplified: numeric only)
        if opcode == "EQU":
            if label:
                if operand == "*":
                    value = lc_now
                else:
                    try:
                        value = int(operand, 16)
                    except ValueError:
                        # Could be a symbol expression — store as-is for Pass 2
                        value = operand
                symb_table[label] = {"block": current_block, "lc": value, "equ": True}
            continue

        # ── Register label (if any) ─────────────────────────────────────────
        if label:
            if label in symb_table:
                fatal_error(f"Duplicate symbol: '{label}'", lc_now)
            symb_table[label] = {"block": current_block, "lc": lc_now}

        # ── Detect POOL operand ─────────────────────────────────────────────
        if operand and is_pool_operand(operand):
            key = pool_key(operand)
            if key not in pool_table:
                pool_lc = block_lc["POOL"]
                pool_table[key] = {"block": "POOL", "lc": pool_lc, "raw": operand}
                pool_order.append(key)
                block_lc["POOL"] += _pool_value_size(operand)

        # ── Advance LC by instruction/directive size ─────────────────────────
        size = instr_size(opcode, operand)
        block_lc[current_block] += size

    # ── Build block lengths ──────────────────────────────────────────────────
    block_lengths = {b: block_lc[b] - block_start.get(b, 0) for b in VALID_BLOCKS}

    # ── Write output files ───────────────────────────────────────────────────
    _write_symb_table(symb_table)
    _write_pool_table(pool_table, pool_order)
    _write_block_table(block_start, block_lengths)

    print("Pass 1 complete.")
    print(f"  Symbols : {len(symb_table)}")
    print(f"  Pool    : {len(pool_table)} entries")
    for b in VALID_BLOCKS:
        print(f"  {b:<10} LC={block_lc[b]:06X}  len={block_lengths[b]:06X}")

    return symb_table, pool_table, block_lc, block_start


# ---------------------------------------------------------------------------
# File writers
# ---------------------------------------------------------------------------
def _write_symb_table(symb_table: dict):
    with open("symbTable.txt", "w") as f:
        f.write(f"{'SYMBOL':<12} {'BLOCK':<12} {'LC (hex)'}\n")
        f.write("-" * 36 + "\n")
        for sym, info in symb_table.items():
            lc_val = info["lc"]
            lc_str = f"{lc_val:06X}" if isinstance(lc_val, int) else str(lc_val)
            equ_marker = " (EQU)" if info.get("equ") else ""
            f.write(f"{sym:<12} {info['block']:<12} {lc_str}{equ_marker}\n")


def _write_pool_table(pool_table: dict, pool_order: list):
    with open("PoolTable.txt", "w") as f:
        f.write(f"{'POOL KEY':<16} {'BLOCK':<8} {'LC (hex)'}\n")
        f.write("-" * 36 + "\n")
        for key in pool_order:
            info = pool_table[key]
            f.write(f"{key:<16} {info['block']:<8} {info['lc']:06X}\n")


def _write_block_table(block_start: dict, block_lengths: dict):
    with open("blockTable.txt", "w") as f:
        f.write(f"{'BLOCK':<12} {'START (hex)':<14} {'LENGTH (hex)'}\n")
        f.write("-" * 40 + "\n")
        for block in ("DEFAULT", "DEFAULTB", "CDATA", "CBLKS", "POOL"):
            f.write(
                f"{block:<12} {block_start.get(block, 0):06X}         "
                f"{block_lengths.get(block, 0):06X}\n"
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    pass1("in.txt")