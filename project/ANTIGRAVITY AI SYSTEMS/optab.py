"""
SIC/XE Assembler — Shared Constants
Operation Code Table, Register Table, Block definitions, and common utilities
shared between Pass 1 and Pass 2.
"""

# ───────────────────────────────────────────────────────────────────────────
# OPTAB — (opcode_hex, default_format)
# ───────────────────────────────────────────────────────────────────────────
OPTAB = {
    "ADD":  ("18",3), "ADDF": ("58",3), "ADDR": ("90",2),
    "AND":  ("40",3), "CLEAR":("B4",2), "COMP": ("28",3),
    "COMPF":("88",3), "COMPR":("A0",2), "DIV":  ("24",3),
    "DIVF": ("64",3), "DIVR": ("9C",2), "FIX":  ("C4",1),
    "FLOAT":("C0",1), "HIO":  ("F4",1), "J":    ("3C",3),
    "JEQ":  ("30",3), "JGT":  ("34",3), "JLT":  ("38",3),
    "JSUB": ("48",3), "LDA":  ("00",3), "LDB":  ("68",3),
    "LDCH": ("50",3), "LDF":  ("70",3), "LDL":  ("08",3),
    "LDS":  ("6C",3), "LDT":  ("74",3), "LDX":  ("04",3),
    "LPS":  ("D0",3), "MUL":  ("20",3), "MULF": ("60",3),
    "MULR": ("98",2), "NORM": ("C8",1), "OR":   ("44",3),
    "RD":   ("D8",3), "RMO":  ("AC",2), "RSUB": ("4C",3),
    "SHIFTL":("A4",2),"SHIFTR":("A8",2),"SIO":  ("F0",1),
    "SSK":  ("EC",3), "STA":  ("0C",3), "STB":  ("78",3),
    "STCH": ("54",3), "STF":  ("80",3), "STI":  ("D4",3),
    "STL":  ("14",3), "STS":  ("7C",3), "STSW": ("E8",3),
    "STT":  ("84",3), "STX":  ("10",3), "SUB":  ("1C",3),
    "SUBF": ("5C",3), "SUBR": ("94",2), "SVC":  ("B0",2),
    "TD":   ("E0",3), "TIO":  ("F8",1), "TIX":  ("2C",3),
    "TIXR": ("B8",2), "WD":   ("DC",3),
}

# ───────────────────────────────────────────────────────────────────────────
# Register table  (register_name → numeric_code)
# ───────────────────────────────────────────────────────────────────────────
REGTAB = {"A":0, "X":1, "L":2, "B":3, "S":4, "T":5, "F":6, "PC":8, "SW":9}

# ───────────────────────────────────────────────────────────────────────────
# Block & directive constants
# ───────────────────────────────────────────────────────────────────────────
VALID_BLOCKS = {"DEFAULT", "DEFAULTB", "CDATA", "CBLKS", "POOL"}
DIRECTIVES_NO_CODE = {"START", "END", "USE", "BASE", "NOBASE", "EQU"}

# ───────────────────────────────────────────────────────────────────────────
# Source-line parser
# ───────────────────────────────────────────────────────────────────────────
def parse_line(raw):
    """Return (label, opcode, operand) or None for blank/comment lines."""
    line = raw.split(".")[0].rstrip()
    if not line.strip():
        return None
    parts = line.split()
    if not parts:
        return None
    if raw[0] not in (" ", "\t"):
        label   = parts[0] if len(parts) > 0 else ""
        opcode  = parts[1] if len(parts) > 1 else ""
        operand = parts[2] if len(parts) > 2 else ""
    else:
        label   = ""
        opcode  = parts[0] if len(parts) > 0 else ""
        operand = parts[1] if len(parts) > 1 else ""
    return label.upper(), opcode.upper(), operand.upper()


# ───────────────────────────────────────────────────────────────────────────
# Size helpers
# ───────────────────────────────────────────────────────────────────────────
def byte_size(operand):
    """Return byte count for a BYTE directive operand."""
    operand = operand.strip()
    if operand.startswith("C'") and operand.endswith("'"):
        return len(operand[2:-1])
    if operand.startswith("X'") and operand.endswith("'"):
        return len(operand[2:-1]) // 2
    return 1


def pool_literal_size(operand):
    """Size in bytes of a pool literal (strip leading &)."""
    inner = operand.lstrip("&")
    if inner.startswith("C'") and inner.endswith("'"):
        return len(inner[2:-1])
    if inner.startswith("X'") and inner.endswith("'"):
        return len(inner[2:-1]) // 2
    return 3                                    # default: 1 word


def instr_size(opcode, operand):
    """Return byte size for an instruction or directive."""
    stripped = opcode.lstrip("+")
    if stripped == "WORD":   return 3
    if stripped == "RESW":
        try: return 3 * int(operand)
        except ValueError: return 3
    if stripped == "RESB":
        try: return int(operand)
        except ValueError: return 1
    if stripped == "BYTE":   return byte_size(operand)
    if stripped in DIRECTIVES_NO_CODE:
        return 0
    if opcode.startswith("+"):
        return 4
    if stripped in OPTAB:
        return OPTAB[stripped][1]
    return 3
