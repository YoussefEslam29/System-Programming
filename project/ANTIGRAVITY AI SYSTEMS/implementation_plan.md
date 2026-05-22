# Pass 2 — Modified SIC/XE Assembler

Implement `pass2()` and `generate_htme_records()` inside the existing `assembler.py` skeleton. The code must read every Pass 1 artifact, compute object code for every instruction line, and emit HTME records matching the expected outputs already provided in the project.

## Inputs & Expected Outputs (Reference)

| File | Role |
|---|---|
| `in.txt` | Original source |
| `intermediate.txt` | Parsed lines from Pass 1 (relative LCs, block context) |
| `symbTable.txt` | Symbols with **absolute** addresses |
| `blockTable.txt` | Block start addresses & lengths |
| **Expected** `out_pass2.txt` | Intermediate + object code column |
| **Expected** `HTME.txt` | Final loader records |

### Key Data Already Available

**Block table** (from `blockTable.txt`):

| Block | Start | Length |
|---|---|---|
| DEFAULT | 0x0000 | 0x0004 |
| DEFAULTB | 0x0004 | 0x001F |
| POOL | 0x0023 | 0x0004 |
| CDATA | 0x0027 | 0x0009 |
| CBLKS | 0x0030 | 0x1500 |

**Symbol table** (absolute addresses):

| Symbol | Address |
|---|---|
| FIRST | 0x0000 |
| ALPHA | 0x0027 |
| BETA | 0x002A |
| BASEVAL | 0x002D |
| GAMMA | 0x0030 |

**Total program length**: 0x1530

---

## Proposed Changes

### [MODIFY] [assembler.py](file:///d:/1%29%20colloge/3%29%20TERM%206/SYSTEM%20PRO/System%20Programming/project/assembler.py)

Rewrite the file to contain a full, complete OPTAB, all helper functions, `pass2()`, `generate_htme_records()`, and a `__main__` entry point.

#### 1. Complete OPTAB
Copy the full 59-entry OPTAB from `pass 1.py` into `assembler.py`.

#### 2. Register Table
```python
REGTAB = {"A":0, "X":1, "L":2, "B":3, "S":4, "T":5, "F":6, "PC":8, "SW":9}
```

#### 3. File Parsers

- `load_block_table("blockTable.txt")` → `dict[str, {"start": int, "length": int}]`
- `load_symbol_table("symbTable.txt")` → `dict[str, int]` (absolute addresses)
- `parse_intermediate("intermediate.txt")` → list of `(lc_str, label, opcode, operand)` tuples

#### 4. Address Resolution

```
absolute_address(symbol) = symb_table[symbol]   # already absolute in symbTable.txt
pool_address(key)        = POOL_start + pool_relative_lc
```

For pool literals (`&C'EOF'`, `&X'0F'`), we generate the pool table ourselves from `in.txt` or the intermediate, computing their absolute addresses as `POOL_block_start + offset`.

#### 5. Object Code Generation — `generate_object_code()`

| Format | Size | Logic |
|---|---|---|
| **Format 1** | 1 byte | Just the opcode byte |
| **Format 2** | 2 bytes | `opcode_byte ∥ r1<<4 ∥ r2` |
| **Format 3** | 3 bytes | 6-bit opcode (top 6 bits) + nixbpe(6 bits) + disp(12 bits) |
| **Format 4** | 4 bytes | 6-bit opcode + nixbpe(6 bits, e=1) + address(20 bits) |

**nixbpe flag rules:**
- `#operand` → immediate: n=0, i=1
- `@operand` → indirect: n=1, i=0
- `operand,X` → indexed: x=1 (combined with n=1,i=1)
- plain → simple: n=1, i=1
- Format 4 (`+` prefix) → e=1
- Format 3 PC-relative (default) → p=1, disp = TA - (PC)
- Format 3 Base-relative (fallback) → b=1, disp = TA - (B)
- `RSUB` → special case: `4F0000`

**Displacement calculation (Format 3):**
```
PC = current_absolute_address + 3
disp = target_absolute_address - PC
if -2048 <= disp <= 2047 → PC-relative (p=1)
else → base-relative (b=1), disp = target - base_register_value
```

#### 6. Directives

| Directive | Object Code |
|---|---|
| `WORD value` | 3-byte hex of the integer value |
| `BYTE C'...'` | ASCII hex of each character |
| `BYTE X'...'` | Literal hex digits |
| `RESW`, `RESB` | No object code (reserve space) |
| `START`, `END`, `USE`, `BASE`, `NOBASE`, `EQU` | No object code |

`BASE BASEVAL` → sets `base_register = symb_table["BASEVAL"]` for future base-relative calculations.

#### 7. `pass2()` Function Flow

```
1. Load block_table, symb_table
2. Build pool_table from intermediate (track &-prefixed operands)
3. Parse intermediate.txt line by line
4. For each line:
   a. Track current_block via USE directives
   b. Compute absolute address = block_start + relative_lc
   c. Generate object code (or "No object code")
   d. Append to output list
5. Write out_pass2.txt
6. Call generate_htme_records()
```

#### 8. `generate_htme_records()` Function

**H record**: `H.{name:6}.{start:06X}.{length:06X}`
- Name: `COPY` → padded to 6 chars: `COPYXX` (pad with `X` as shown in expected output)

**T records** — one per contiguous block of object code:
- Group consecutive object codes by absolute address continuity
- Start a new T record when:
  - A `USE` block switch occurs
  - A `RESW`/`RESB` gap occurs
  - The record exceeds 30 bytes (0x1E)
- Format: `T.{start:06X}.{length:02X}.{obj_codes joined by .}`

**M records** — for each Format 4 instruction referencing a relocatable symbol:
- Format: `M.{address+1:06X}.05`
- The `+1` offsets past the opcode/flags byte to the 20-bit address field

**E record**: `E.{first_executable_address:06X}`
- From `END FIRST` → address of `FIRST` = `000000`

---

## Verification Plan

### Automated Tests

1. Run `python assembler.py in.txt` and diff the outputs:
   - `out_pass2.txt` must match the expected file character-by-character
   - `HTME.txt` must match the expected file character-by-character

2. Spot-check critical object codes:
   - `CLEAR X` → `B410` (Format 2: B4 opcode, reg X=1, r2=0)
   - `LDA #0` → `010000` (immediate, n=0 i=1, disp=0)
   - `LDB #BASEVAL` → `692023` (immediate, n=0 i=1, PC-relative to BASEVAL)
   - `+LDX ALPHA` → `07100027` (Format 4, simple, e=1, absolute addr=0x0027)
   - `RSUB` → `4F0000`
   - `WORD 4096` → `001000`

### Manual Verification
- Visually inspect each object code against hand-computed values
- Verify M record addresses point to the correct Format 4 displacement field
