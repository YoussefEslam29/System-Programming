"""
SIC/XE Assembler — Pass 2
Reads Pass 1 outputs (symbTable.txt, blockTable.txt) and the original
source (in.txt) to generate object code and HTME records.

Outputs:
  out_pass2.txt  — intermediate listing with object code column
  HTME.txt       — Header, Text, Modification, End records
"""

import re
from optab import (
    OPTAB, REGTAB, VALID_BLOCKS, DIRECTIVES_NO_CODE,
    parse_line, byte_size, pool_literal_size, instr_size,
)


# ───────────────────────────────────────────────────────────────────────────
# File loaders
# ───────────────────────────────────────────────────────────────────────────
def load_symbol_table(filename="symbTable.txt"):
    """Load symbol table → {name: absolute_address}."""
    symb = {}
    with open(filename, "r") as f:
        for line in f.readlines()[1:]:          # skip header
            parts = line.split()
            if len(parts) >= 2:
                symb[parts[0].upper()] = int(parts[1], 16)
    return symb


def load_block_table(filename="blockTable.txt"):
    """Load block table → {name: {start, length}}, total_length."""
    blocks = {}
    total_length = 0
    with open(filename, "r") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 4 and parts[0] in VALID_BLOCKS:
                blocks[parts[0]] = {
                    "start":  int(parts[2], 16),
                    "length": int(parts[3], 16),
                }
            if "Total program length" in line:
                m = re.search(r":\s*([0-9A-Fa-f]+)", line)
                if m:
                    total_length = int(m.group(1), 16)
    return blocks, total_length


# ───────────────────────────────────────────────────────────────────────────
# Pool literal value → hex string
# ───────────────────────────────────────────────────────────────────────────
def pool_literal_hex(operand):
    """Return the hex object code string for a pool literal value."""
    inner = operand.lstrip("&")
    if inner.startswith("C'") and inner.endswith("'"):
        chars = inner[2:-1]
        return "".join(f"{ord(c):02X}" for c in chars)
    if inner.startswith("X'") and inner.endswith("'"):
        return inner[2:-1].upper()
    # Numeric fallback
    try:
        v = int(inner)
        return f"{v:06X}"
    except ValueError:
        return "000000"


# ───────────────────────────────────────────────────────────────────────────
# Object-code generation for a single instruction
# ───────────────────────────────────────────────────────────────────────────
def generate_object_code(opcode, operand, abs_addr, pc_after, base_val,
                         symb_table, pool_table):
    """
    Return (obj_code_hex_string, is_format4).
    obj_code_hex_string is "" for directives that produce no code.
    """
    stripped = opcode.lstrip("+")
    is_fmt4 = opcode.startswith("+")

    # ── Directives ────────────────────────────────────────────────────────
    if stripped in DIRECTIVES_NO_CODE:
        return "", False

    if stripped == "RESW" or stripped == "RESB":
        return "", False

    if stripped == "WORD":
        try:
            val = int(operand)
        except ValueError:
            val = 0
        return f"{val & 0xFFFFFF:06X}", False

    if stripped == "BYTE":
        if operand.startswith("C'") and operand.endswith("'"):
            chars = operand[2:-1]
            return "".join(f"{ord(c):02X}" for c in chars), False
        if operand.startswith("X'") and operand.endswith("'"):
            return operand[2:-1].upper(), False
        return "", False

    # ── Must be an instruction in OPTAB ───────────────────────────────────
    if stripped not in OPTAB:
        return "", False

    op_hex, default_fmt = OPTAB[stripped]
    op_int = int(op_hex, 16)

    # ── Format 1 ──────────────────────────────────────────────────────────
    if default_fmt == 1:
        return f"{op_int:02X}", False

    # ── Format 2 ──────────────────────────────────────────────────────────
    if default_fmt == 2:
        r1, r2 = 0, 0
        regs = operand.replace(" ", "").split(",") if operand else [""]
        if regs[0] in REGTAB:
            r1 = REGTAB[regs[0]]
        if len(regs) > 1 and regs[1] in REGTAB:
            r2 = REGTAB[regs[1]]
        return f"{op_int:02X}{r1:01X}{r2:01X}", False

    # ── Format 3 / 4 ─────────────────────────────────────────────────────
    n, i, x, b, p, e = 1, 1, 0, 0, 0, 0

    if is_fmt4:
        e = 1

    # Parse addressing mode from operand
    clean_operand = operand
    if not clean_operand:
        # RSUB or similar — no operand
        first_byte = (op_int & 0xFC) | (n << 1) | i
        return f"{first_byte:02X}{0:04X}", False

    # Immediate
    if clean_operand.startswith("#"):
        n, i = 0, 1
        clean_operand = clean_operand[1:]
    # Indirect
    elif clean_operand.startswith("@"):
        n, i = 1, 0
        clean_operand = clean_operand[1:]

    # Indexed
    if ",X" in clean_operand:
        x = 1
        clean_operand = clean_operand.replace(",X", "")

    # ── Resolve target address ────────────────────────────────────────────
    ta = None

    # Pool literal (&-prefixed)
    if clean_operand.startswith("&") or operand.startswith("&"):
        pool_key = operand.lstrip("&").upper()       # e.g. C'EOF'
        if pool_key in pool_table:
            ta = pool_table[pool_key]
    # Immediate numeric literal
    elif n == 0 and i == 1:
        try:
            ta = int(clean_operand)
            # For immediate numeric, disp/addr IS the value itself
            first_byte = (op_int & 0xFC) | (n << 1) | i
            if is_fmt4:
                xbpe = (x << 3) | (b << 2) | (p << 1) | e
                return f"{first_byte:02X}{xbpe:01X}{ta & 0xFFFFF:05X}", True
            else:
                xbpe = (x << 3) | (b << 2) | (p << 1) | e
                return f"{first_byte:02X}{xbpe:01X}{ta & 0xFFF:03X}", False
        except ValueError:
            # Symbol in immediate mode — resolve and use displacement
            if clean_operand in symb_table:
                ta = symb_table[clean_operand]
            else:
                ta = 0
    # Symbol
    elif clean_operand in symb_table:
        ta = symb_table[clean_operand]
    else:
        ta = 0

    # ── Compute displacement / address ────────────────────────────────────
    first_byte = (op_int & 0xFC) | (n << 1) | i

    if is_fmt4:
        # Format 4: 20-bit absolute address, e=1
        xbpe = (x << 3) | (b << 2) | (p << 1) | e
        return f"{first_byte:02X}{xbpe:01X}{ta & 0xFFFFF:05X}", True

    # Format 3: try PC-relative, then Base-relative
    disp = ta - pc_after
    if -2048 <= disp <= 2047:
        p = 1
        xbpe = (x << 3) | (b << 2) | (p << 1) | e
        return f"{first_byte:02X}{xbpe:01X}{disp & 0xFFF:03X}", False

    # Base-relative
    if base_val is not None:
        disp = ta - base_val
        if 0 <= disp <= 4095:
            b = 1
            xbpe = (x << 3) | (b << 2) | (p << 1) | e
            return f"{first_byte:02X}{xbpe:01X}{disp & 0xFFF:03X}", False

    # Direct (no displacement mode — shouldn't happen in well-formed code)
    xbpe = (x << 3) | (b << 2) | (p << 1) | e
    return f"{first_byte:02X}{xbpe:01X}{ta & 0xFFF:03X}", False


# ───────────────────────────────────────────────────────────────────────────
# Pass 2 — main driver
# ───────────────────────────────────────────────────────────────────────────
def pass2(input_file="in.txt"):
    """
    Main Pass 2 driver.
    Reads in.txt, symbTable.txt, blockTable.txt.
    Produces out_pass2.txt and HTME.txt.
    """
    # ── Load Pass 1 artifacts ─────────────────────────────────────────────
    symb_table = load_symbol_table("symbTable.txt")
    block_table, total_length = load_block_table("blockTable.txt")

    # ── Read source ───────────────────────────────────────────────────────
    with open(input_file, "r") as f:
        lines = f.readlines()

    # ── First scan: build pool table with absolute addresses ──────────────
    pool_table = {}        # key (e.g. "C'EOF'") → absolute address
    pool_entries = []      # ordered list of (key, hex_value, size)
    pool_offset = 0
    pool_start = block_table.get("POOL", {}).get("start", 0)

    for raw in lines:
        parsed = parse_line(raw)
        if parsed is None:
            continue
        _, opcode, operand = parsed
        if opcode in ("START", "END"):
            continue
        if operand and operand.startswith("&"):
            key = operand[1:].upper()
            if key not in pool_table:
                size = pool_literal_size(operand)
                pool_table[key] = pool_start + pool_offset
                pool_entries.append((key, pool_literal_hex(operand), size))
                pool_offset += size

    # ── Main pass: generate object code per line ──────────────────────────
    current_block = "DEFAULT"
    block_lc = {b: 0 for b in VALID_BLOCKS}
    base_val = None
    program_name = ""
    program_start = 0
    end_operand = ""

    output_lines = []       # (lc_str, label, opcode, operand, obj_code)
    code_entries = []       # (abs_addr, obj_code, is_fmt4, opcode, block) for HTME
    modification_addrs = [] # absolute addresses needing M records

    for raw in lines:
        parsed = parse_line(raw)
        if parsed is None:
            continue

        label, opcode, operand = parsed
        stripped = opcode.lstrip("+")

        # ── START ─────────────────────────────────────────────────────────
        if stripped == "START":
            program_name = label
            try:
                program_start = int(operand, 16) if operand else 0
            except ValueError:
                program_start = 0
            output_lines.append(("0000", label, opcode, operand, "No object code"))
            continue

        # ── END ───────────────────────────────────────────────────────────
        if stripped == "END":
            end_operand = operand
            lc_hex = f"{block_lc[current_block]:04X}"
            output_lines.append((lc_hex, "", opcode, operand, "No object code"))
            break

        # ── USE ───────────────────────────────────────────────────────────
        if stripped == "USE":
            new_block = operand if operand else "DEFAULT"
            current_block = new_block
            output_lines.append(("", "", opcode, operand, "No object code"))
            continue

        # ── BASE / NOBASE ─────────────────────────────────────────────────
        if stripped == "BASE":
            if operand in symb_table:
                base_val = symb_table[operand]
            lc_hex = f"{block_lc[current_block]:04X}"
            output_lines.append((lc_hex, "", opcode, operand, "No object code"))
            continue
        if stripped == "NOBASE":
            base_val = None
            lc_hex = f"{block_lc[current_block]:04X}"
            output_lines.append((lc_hex, "", opcode, operand, "No object code"))
            continue

        # ── EQU ───────────────────────────────────────────────────────────
        if stripped == "EQU":
            output_lines.append(("", label, opcode, operand, "No object code"))
            continue

        # ── Normal instruction / directive ────────────────────────────────
        rel_lc = block_lc[current_block]
        blk_start = block_table.get(current_block, {}).get("start", 0)
        abs_addr = blk_start + rel_lc
        size = instr_size(opcode, operand)

        # PC after this instruction (for PC-relative)
        pc_after = abs_addr + size if size <= 4 else abs_addr + size

        # For Format 3, pc_after = abs_addr + 3
        # For Format 4, pc_after = abs_addr + 4  (but Format 4 uses absolute)
        if opcode.startswith("+"):
            pc_after = abs_addr + 4
        elif stripped in OPTAB and OPTAB[stripped][1] == 3:
            pc_after = abs_addr + 3
        elif stripped in OPTAB and OPTAB[stripped][1] == 2:
            pc_after = abs_addr + 2
        elif stripped in OPTAB and OPTAB[stripped][1] == 1:
            pc_after = abs_addr + 1

        obj_code, is_fmt4 = generate_object_code(
            opcode, operand, abs_addr, pc_after, base_val,
            symb_table, pool_table
        )

        lc_hex = f"{rel_lc:04X}"
        display_code = obj_code if obj_code else "No object code"
        output_lines.append((lc_hex, label, opcode, operand, display_code))

        if obj_code:
            code_entries.append((abs_addr, obj_code, is_fmt4, opcode, current_block))

        # Track Format 4 for Modification records
        if is_fmt4:
            # Check if operand is a relocatable symbol (not immediate numeric)
            test_op = operand.lstrip("#+@").replace(",X", "")
            try:
                int(test_op)
            except ValueError:
                # It's a symbol reference → needs modification
                modification_addrs.append(abs_addr + 1)

        block_lc[current_block] += size

    # ── Add pool literal entries to code_entries ──────────────────────────
    for key, hex_val, size in pool_entries:
        addr = pool_table[key]
        code_entries.append((addr, hex_val, False, "POOL_LIT", "POOL"))

    # ── Write out_pass2.txt ───────────────────────────────────────────────
    write_pass2_output(output_lines)

    # ── Generate HTME records ─────────────────────────────────────────────
    generate_htme_records(
        program_name, program_start, total_length,
        code_entries, modification_addrs, end_operand, symb_table,
        block_table
    )

    print("Pass 2 complete.")
    print(f"  Object codes generated: {sum(1 for e in code_entries)}")
    print(f"  Modification records:   {len(modification_addrs)}")


# ───────────────────────────────────────────────────────────────────────────
# Write out_pass2.txt
# ───────────────────────────────────────────────────────────────────────────
def write_pass2_output(output_lines):
    """Write the intermediate listing with object code column."""
    with open("out_pass2.txt", "w") as f:
        f.write(
            f"{'Location counter':<18}{'Symbol':<9}"
            f"{'Instructions':<14}{'Reference':<12}{'Obj. code'}\n"
        )
        f.write(
            f"{'----------------':<18}{'-------':<9}"
            f"{'------------':<14}{'----------':<12}{'----------' + '----'}\n"
        )
        for lc_str, label, opcode, operand, obj_code in output_lines:
            f.write(
                f"{lc_str:<18}{label:<9}{opcode:<14}{operand:<12}{obj_code}\n"
            )


# ───────────────────────────────────────────────────────────────────────────
# Generate HTME records
# ───────────────────────────────────────────────────────────────────────────
def generate_htme_records(prog_name, start_addr, total_length,
                          code_entries, mod_addrs, end_operand, symb_table,
                          block_table):
    """
    Produce Header, Text, Modification, and End records → HTME.txt

    Text records are grouped per memory block in block order.
    Within each block, a new T record starts when:
      - There is an address gap (non-contiguous, e.g. RESW/RESB)
      - Accumulated bytes would exceed 30 (0x1E)
    """
    records = []

    # ── Header ────────────────────────────────────────────────────────────
    padded_name = prog_name.ljust(6, "X")[:6]
    records.append(f"H.{padded_name}.{start_addr:06X}.{total_length:06X}")

    # ── Group code entries by block, preserving insertion order ───────────
    block_order = ["DEFAULT", "DEFAULTB", "CDATA", "CBLKS", "POOL"]
    block_codes = {b: [] for b in block_order}
    for entry in code_entries:
        blk = entry[4]   # block name
        block_codes[blk].append(entry)

    # Sort entries within each block by absolute address
    for blk in block_order:
        block_codes[blk].sort(key=lambda e: e[0])

    # ── Build Text records per block ──────────────────────────────────────
    t_start = None
    t_codes = []
    t_bytes = 0

    def flush_t():
        nonlocal t_start, t_codes, t_bytes
        if t_codes:
            records.append(
                f"T.{t_start:06X}.{t_bytes:02X}.{'.'.join(t_codes)}"
            )
        t_codes = []
        t_bytes = 0
        t_start = None

    for blk in block_order:
        # Each block starts a fresh T record
        flush_t()
        for abs_addr, obj_hex, is_fmt4, opcode, _blk in block_codes[blk]:
            obj_bytes = len(obj_hex) // 2
            expected_next = (t_start + t_bytes) if t_start is not None else None

            # Start new record if gap or would exceed 30 bytes
            if t_start is None:
                t_start = abs_addr
            elif abs_addr != expected_next or t_bytes + obj_bytes > 0x1E:
                flush_t()
                t_start = abs_addr

            t_codes.append(obj_hex)
            t_bytes += obj_bytes

    flush_t()

    # ── Modification ──────────────────────────────────────────────────────
    for addr in sorted(mod_addrs):
        records.append(f"M.{addr:06X}.05")

    # ── End ───────────────────────────────────────────────────────────────
    first_exec = 0
    if end_operand and end_operand in symb_table:
        first_exec = symb_table[end_operand]
    records.append(f"E.{first_exec:06X}")

    # ── Write ─────────────────────────────────────────────────────────────
    with open("HTME.txt", "w") as f:
        for r in records:
            f.write(r + "\n")

    return records
