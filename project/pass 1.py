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

# ---------------------------------------------------------------------------
# OPTAB — (opcode_hex, default_format_size_in_bytes)
# ---------------------------------------------------------------------------
OPTAB = {
    "ADD":    ("18", 3), "ADDF":   ("58", 3), "ADDR":   ("90", 2),
    "AND":    ("40", 3), "CLEAR":  ("B4", 2), "COMP":   ("28", 3),
    "COMPF":  ("88", 3), "COMPR":  ("A0", 2), "DIV":    ("24", 3),
    "DIVF":   ("64", 3), "DIVR":   ("9C", 2), "FIX":    ("C4", 1),
    "FLOAT":  ("C0", 1), "HIO":    ("F4", 1), "J":      ("3C", 3),
    "JEQ":    ("30", 3), "JGT":    ("34", 3), "JLT":    ("38", 3),
    "JSUB":   ("48", 3), "LDA":    ("00", 3), "LDB":    ("68", 3),
    "LDCH":   ("50", 3), "LDF":    ("70", 3), "LDL":    ("08", 3),
    "LDS":    ("6C", 3), "LDT":    ("74", 3), "LDX":    ("04", 3),
    "LPS":    ("D0", 3), "MUL":    ("20", 3), "MULF":   ("60", 3),
    "MULR":   ("98", 2), "NORM":   ("C8", 1), "OR":     ("44", 3),
    "RD":     ("D8", 3), "RMO":    ("AC", 2), "RSUB":   ("4C", 3),
    "SHIFTL": ("A4", 2), "SHIFTR": ("A8", 2), "SIO":    ("F0", 1),
    "SSK":    ("EC", 3), "STA":    ("0C", 3), "STB":    ("78", 3),
    "STCH":   ("54", 3), "STF":    ("80", 3), "STI":    ("D4", 3),
    "STL":    ("14", 3), "STS":    ("7C", 3), "STSW":   ("E8", 3),
    "STT":    ("84", 3), "STX":    ("10", 3), "SUB":    ("1C", 3),
    "SUBF":   ("5C", 3), "SUBR":   ("94", 2), "SVC":    ("B0", 2),
    "TD":     ("E0", 3), "TIO":    ("F8", 1), "TIX":    ("2C", 3),
    "TIXR":   ("B8", 2), "WD":     ("DC", 3),
}

# Valid memory block names
VALID_BLOCKS = {"DEFAULT", "DEFAULTB", "CDATA", "CBLKS", "POOL"}

# ---------------------------------------------------------------------------
# Error helper — writes error.txt and raises to halt execution
# ---------------------------------------------------------------------------
def fatal_error(message: str, pc: int):
    with open("error.txt", "w") as f:
        f.write(f"ERROR: {message}\n")
        f.write(f"PC: {pc:06X}\n")
    raise SystemExit(f"[FATAL] {message}  (PC={pc:06X}) — see error.txt")


# ---------------------------------------------------------------------------
# Line parser — returns (label, opcode, operand) or None for blank/comment
# ---------------------------------------------------------------------------
def parse_line(raw: str):
    # Strip inline comments (anything after '.')
    line = raw.split(".")[0].rstrip()
    if not line.strip():
        return None

    # Fixed-field or free-format: split on whitespace
    parts = line.split()
    if not parts:
        return None

    # Detect if first token is a label (no leading space in original = label present)
    # Use original line: if col 0 is non-space → label exists
    if raw[0] not in (" ", "\t"):
        label  = parts[0] if len(parts) > 0 else ""
        opcode = parts[1] if len(parts) > 1 else ""
        operand= parts[2] if len(parts) > 2 else ""
    else:
        label  = ""
        opcode = parts[0] if len(parts) > 0 else ""
        operand= parts[1] if len(parts) > 1 else ""

    return label.upper(), opcode.upper(), operand.upper()


# ---------------------------------------------------------------------------
# Operand size helpers
# ---------------------------------------------------------------------------
def _byte_size(operand: str) -> int:
    """Return byte count for a BYTE directive operand."""
    operand = operand.strip()
    if operand.startswith("C'") and operand.endswith("'"):
        return len(operand[2:-1])           # one byte per character
    if operand.startswith("X'") and operand.endswith("'"):
        return len(operand[2:-1]) // 2      # one byte per two hex digits
    return 1                                # fallback

def _pool_value_size(operand: str) -> int:
    """
    POOL entries store the raw numeric value of &-prefixed operands.
    Size is always one word (3 bytes) for SIC/XE.
    Extend here if your spec differs.
    """
    return 3


def _get_instruction_size(opcode: str, operand: str) -> int:
    """Return byte size for an instruction, honouring the '+' Format-4 prefix."""
    if opcode.startswith("+"):
        return 4                            # Format 4
    base = opcode.lstrip("+")
    if base in OPTAB:
        return OPTAB[base][1]
    return 3                                # safe default


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
        size = _instruction_size(opcode, operand, lc_now)
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
# Instruction/directive size dispatcher
# ---------------------------------------------------------------------------
def _instruction_size(opcode: str, operand: str, lc: int) -> int:
    stripped = opcode.lstrip("+")

    if stripped == "WORD":   return 3
    if stripped == "RESW":
        try: return 3 * int(operand)
        except ValueError: return 3
    if stripped == "RESB":
        try: return int(operand)
        except ValueError: return 1
    if stripped == "BYTE":   return _byte_size(operand)
    if stripped in ("START", "END", "USE", "EQU", "BASE", "NOBASE"):
        return 0

    return _get_instruction_size(opcode, operand)


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