from typing import Optional, cast

from instruction_set import (
    MemoryBlock,
    InstructionFormat,
    is_directive,
    is_supported,
    is_format4,
    lookup_opcode,
)
from preprocessor import ParsedLine
from assembler_errors import (
    DuplicateSymbolError,
    InvalidDirectiveOperandError,
    InvalidMnemonicOrDirective,
    UnidentifiedBlockNameError,
)

from . import (
    AssemblyInstruction,
    DirectiveInstruction,
    Format1Instruction,
    Format2Instruction,
    Format3Instruction,
    Format4Instruction,
)

# ── All valid memory blocks and their string names ──────────────────────
ALL_BLOCKS = (
    MemoryBlock.DEFAULT,
    MemoryBlock.DEFAULTB,
    MemoryBlock.CDATA,
    MemoryBlock.CBLKS,
    MemoryBlock.POOL,
)
USER_BLOCKS = ALL_BLOCKS[:-1]                        # everything except POOL
USE_BLOCK_MAP = {b.value: b for b in USER_BLOCKS}   # "DEFAULT" -> MemoryBlock.DEFAULT …


class AssemblerPassOne:
    """Pass 1 of the SIC/XE assembler:
       - assigns addresses (location counters) to every instruction
       - builds the symbol table
       - collects literals and creates the literal pool
    """

    def __init__(self) -> None:
        # One dict holds *all* location counters (instead of 5 separate variables)
        self._locs: dict[MemoryBlock, int] = {b: 0 for b in ALL_BLOCKS}

        # One dict holds *all* symbol tables (instead of 5 separate dicts)
        self._symtabs: dict[MemoryBlock, dict[str, int]] = {b: {} for b in ALL_BLOCKS}

        self.instructions: list[AssemblyInstruction] = []
        self.start_address = 0
        self.program_name = ""

        # Literal pool tracking
        self._pending_literals: list[str] = []        # ordered list
        self._pending_literals_set: set[str] = set()  # for fast duplicate check
        self._pool_anchor_block: Optional[MemoryBlock] = None

    # ── Symbol table helpers ────────────────────────────────────────────

    def _lookup_symbol(self, symbol: str) -> Optional[tuple[MemoryBlock, int]]:
        """Search every block's symtab for `symbol`. Return (block, address) or None."""
        for block in ALL_BLOCKS:
            if symbol in self._symtabs[block]:
                return block, self._symtabs[block][symbol]
        return None

    def _add_symbol(self, symbol: str, block: MemoryBlock, value: int,
                    program_counter: int, line_no: int) -> None:
        """Insert a symbol; raise DuplicateSymbolError if it already exists anywhere."""
        if self._lookup_symbol(symbol) is not None:
            raise DuplicateSymbolError(
                f"Duplicate symbol definition for '{symbol}'", program_counter, line_no)
        self._symtabs[block][symbol] = value

    # ── Expression / operand evaluation ─────────────────────────────────

    def _try_parse_int(self, token: str) -> Optional[int]:
        """Try to parse a string as an integer (supports 0x… prefix). Return None on failure."""
        try:
            return int(token.strip(), 0)
        except (ValueError, TypeError):
            return None

    def _resolve_term(self, term: str, current_loc: int, line_no: int) -> int:
        """Resolve a single operand term to an integer value.
           A term can be: a number, the '*' symbol (= current loc), or a defined symbol.
        """
        clean = term.strip().lstrip("#@")          # strip addressing-mode prefixes
        if clean.endswith(",X"):
            clean = clean[:-2]                     # strip indexed-addressing suffix
        if clean == "*":
            return current_loc

        num = self._try_parse_int(clean)
        if num is not None:
            return num

        entry = self._lookup_symbol(clean)
        if entry is not None:
            return entry[1]  # the address

        raise InvalidDirectiveOperandError(
            f"Unable to resolve operand term '{term}'", current_loc, line_no)

    def _evaluate_expression(self, expr: str, current_loc: int, line_no: int) -> int:
        """Evaluate a simple expression like 'BUFEND-BUFFER' or 'LEN+3'.
           Supports at most ONE '+' or '-' operator.
        """
        s = expr.replace(" ", "")
        if not s:
            raise InvalidDirectiveOperandError("Empty directive operand", current_loc, line_no)

        # find the first '+' or '-' that is NOT at position 0 (position 0 could be a sign)
        for i in range(1, len(s)):
            if s[i] in "+-":
                left = self._resolve_term(s[:i], current_loc, line_no)
                right = self._resolve_term(s[i + 1:], current_loc, line_no)
                return left + right if s[i] == "+" else left - right

        # no operator found — the whole thing is a single term
        return self._resolve_term(s, current_loc, line_no)

    def _require_non_negative(self, operand: Optional[str], current_loc: int,
                              line_no: int, directive: str) -> int:
        """Parse an operand that must be present and non-negative."""
        if operand is None:
            raise InvalidDirectiveOperandError(
                f"Directive '{directive}' requires an operand", current_loc, line_no)
        value = self._evaluate_expression(operand, current_loc, line_no)
        if value < 0:
            raise InvalidDirectiveOperandError(
                f"Directive '{directive}' requires a non-negative operand", current_loc, line_no)
        return value

    # ── BYTE / literal size calculation ─────────────────────────────────

    def _data_constant_size(self, operand: str, pc: int, line_no: int,
                            default_num_size: int = 1,
                            error_label: str = "BYTE") -> int:
        """Return the byte-size of a C'…', X'…', or numeric constant.
           `default_num_size` is 1 for BYTE, 3 for WORD-sized literals.
        """
        clean = operand.strip()
        # handle C'abc' or X'0F'
        if len(clean) >= 3 and clean[1] == "'" and clean.endswith("'"):
            kind, payload = clean[0].upper(), clean[2:-1]
            if kind == "C":
                return len(payload)
            if kind == "X":
                if len(payload) % 2 != 0:
                    raise InvalidDirectiveOperandError(
                        f"Hex {error_label} operand must contain an even number of digits", pc, line_no)
                return len(payload) // 2

        if self._try_parse_int(clean) is not None:
            return default_num_size

        raise InvalidDirectiveOperandError(
            f"Unsupported {error_label} operand '{operand}'", pc, line_no)

    def _byte_operand_size(self, operand: Optional[str], pc: int, line_no: int) -> int:
        if operand is None:
            raise InvalidDirectiveOperandError("Directive 'BYTE' requires an operand", pc, line_no)
        return self._data_constant_size(operand, pc, line_no, default_num_size=1, error_label="BYTE")

    def _literal_size(self, literal: str, pc: int, line_no: int) -> int:
        token = literal.lstrip("&").strip()
        return self._data_constant_size(token, pc, line_no, default_num_size=3, error_label="literal")

    # ── Literal pool management ─────────────────────────────────────────

    def _collect_literals(self, operand: Optional[str], block: MemoryBlock) -> None:
        """Scan the operand for '&'-prefixed literals and queue them for the pool."""
        if operand is None:
            return
        for raw in operand.split(","):
            token = raw.strip()
            if not token.startswith("&"):
                continue
            if self._pool_anchor_block is None:
                self._pool_anchor_block = block
            if token not in self._symtabs[MemoryBlock.POOL] and token not in self._pending_literals_set:
                self._pending_literals.append(token)
                self._pending_literals_set.add(token)

    def _flush_literal_pool(self, line_no: int) -> None:
        """Assign addresses to all pending literals and clear the queue."""
        pool_loc = self._locs[MemoryBlock.POOL]
        for lit in self._pending_literals:
            self._symtabs[MemoryBlock.POOL][lit] = pool_loc
            pool_loc += self._literal_size(lit, pool_loc, line_no)
        self._locs[MemoryBlock.POOL] = pool_loc
        self._pending_literals.clear()
        self._pending_literals_set.clear()

    # ── USE directive ───────────────────────────────────────────────────

    def _resolve_use_block(self, operand: Optional[str], pc: int, line_no: int) -> MemoryBlock:
        """Return the MemoryBlock for a USE directive. Default block if operand is None."""
        if operand is None:
            return MemoryBlock.DEFAULT
        block = USE_BLOCK_MAP.get(operand.upper())
        if block is None:
            raise UnidentifiedBlockNameError(
                f"Unidentified Block Name: '{operand}'. Expected one of {', '.join(USE_BLOCK_MAP)}.",
                pc, line_no)
        return block

    # ── Parse a source line into an instruction object ──────────────────

    def _parse_instruction(self, line: ParsedLine, current_loc: int = 0) -> AssemblyInstruction:
        """Turn a ParsedLine (1–3 fields) into the right AssemblyInstruction subclass."""
        label = operand = None

        # figure out which field is the label, mnemonic, operand
        if line.number_of_parts == 1:
            mnemonic = line.first
        elif line.number_of_parts == 2:
            assert line.second is not None
            if is_supported(line.first):
                mnemonic, operand = line.first, line.second
            elif is_supported(line.second):
                label, mnemonic = line.first, line.second
            else:
                raise InvalidMnemonicOrDirective(
                    f"Neither '{line.first}' nor '{line.second}' is a valid opcode or directive",
                    current_loc, line.line_no)
        else:
            assert line.second is not None
            label, mnemonic, operand = line.first, line.second, line.third

        if not mnemonic or not is_supported(mnemonic):
            raise InvalidMnemonicOrDirective(
                f"'{mnemonic}' is not a valid opcode or directive", current_loc, line.line_no)

        # pre-validate USE operand
        if mnemonic.upper() == "USE":
            self._resolve_use_block(operand, current_loc, line.line_no)

        # ── directive ──
        if is_directive(mnemonic):
            return DirectiveInstruction(parsed_line=line, size=0,
                                        label=label, directive=mnemonic, operand=operand)

        # ── machine instruction ──
        info = lookup_opcode(mnemonic)
        if info is not None:
            if is_format4(mnemonic):
                return Format4Instruction(parsed_line=line, size=4,
                                           label=label, mnemonic=mnemonic, operand=operand)
            # map format enum to (class, size, needs_operand)
            fmt_map = {
                InstructionFormat.FORMAT_1: (Format1Instruction, 1, False),
                InstructionFormat.FORMAT_2: (Format2Instruction, 2, True),
                InstructionFormat.FORMAT_3: (Format3Instruction, 3, True),
            }
            cls, size, has_op = fmt_map[info.fmt]
            kwargs = dict(parsed_line=line, size=size, label=label, mnemonic=mnemonic)
            if has_op:
                kwargs["operand"] = operand
            return cls(**kwargs)

        raise InvalidMnemonicOrDirective(
            f"Failed to resolve formatting for '{mnemonic}'", current_loc, line.line_no)

    # ── Handle the START directive (first line) ─────────────────────────

    def _handle_start(self, instr: DirectiveInstruction, line_no: int) -> None:
        """Process the START directive: set program name, starting address, and symbol."""
        self.start_address = int(instr.operand) if instr.operand else 0
        self.program_name = instr.label or ""
        self._locs[MemoryBlock.DEFAULT] = self.start_address
        instr.block = MemoryBlock.DEFAULT
        instr.location_counter = self.start_address
        if instr.label:
            self._add_symbol(instr.label, MemoryBlock.DEFAULT,
                             self.start_address, self.start_address, line_no)

    # ── Process one directive (after START) ─────────────────────────────

    def _process_directive(self, instr: DirectiveInstruction, block: MemoryBlock,
                           loc: int, line_no: int, current_block: MemoryBlock) -> MemoryBlock:
        """Handle a directive, update location counter, return the (possibly changed) block."""
        d = instr.directive.upper()

        # add label to symbol table
        if instr.label:
            self._add_symbol(instr.label, block, loc, loc, line_no)

        self._collect_literals(instr.operand, block)

        if d == "USE":
            return self._resolve_use_block(instr.operand, loc, line_no)
        elif d == "WORD":
            self._locs[block] = loc + 3
        elif d == "RESW":
            self._locs[block] = loc + 3 * self._require_non_negative(instr.operand, loc, line_no, "RESW")
        elif d == "RESB":
            self._locs[block] = loc + self._require_non_negative(instr.operand, loc, line_no, "RESB")
        elif d == "BYTE":
            self._locs[block] = loc + self._byte_operand_size(instr.operand, loc, line_no)
        elif d == "END":
            self._flush_literal_pool(line_no)

        return current_block

    # ── Process one machine instruction ─────────────────────────────────

    def _process_machine(self, instr: AssemblyInstruction, block: MemoryBlock,
                         loc: int, line_no: int) -> None:
        label = getattr(instr, "label", None)
        operand = getattr(instr, "operand", None)
        if label:
            self._add_symbol(label, block, loc, loc, line_no)
        self._collect_literals(operand, block)
        self._locs[block] = loc + instr.size

    # ═══════════════════════════════════════════════════════════════════
    #  MAIN ENTRY POINT
    # ═══════════════════════════════════════════════════════════════════

    def process_pass_one(self, parsed_lines: list[ParsedLine]) -> None:
        """Run pass 1 over all parsed source lines."""
        current_block = MemoryBlock.DEFAULT

        for line in parsed_lines:
            loc = self._locs[current_block]
            instr = self._parse_instruction(line, loc)

            # handle START specially (usually the first line)
            if isinstance(instr, DirectiveInstruction) and instr.directive.upper() == "START":
                self._handle_start(instr, line.line_no)
                self.instructions.append(instr)
                continue

            # set location info on the instruction
            instr.block = current_block
            instr.location_counter = loc

            # dispatch to directive vs. machine processing
            if isinstance(instr, DirectiveInstruction):
                current_block = self._process_directive(instr, current_block, loc, line.line_no, current_block)
            else:
                self._process_machine(instr, current_block, loc, line.line_no)

            self.instructions.append(instr)

        # flush any remaining literals at the end
        if self._pending_literals:
            self._flush_literal_pool(parsed_lines[-1].line_no if parsed_lines else 0)

    # ═══════════════════════════════════════════════════════════════════
    #  EXPORT / OUTPUT METHODS
    # ═══════════════════════════════════════════════════════════════════

    def export_symbol_table(self, output_path: str) -> None:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"{'Symbol':<12}{'Block':<10}{'LC (HEX)':<10}{'LC (DEC)'}\n")
            f.write("-" * 42 + "\n")
            for block in USER_BLOCKS:
                for sym, loc in self._symtabs[block].items():
                    f.write(f"{sym:<12}{block.value:<10}{loc:04X}{loc:>10}\n")

    def export_pool_table(self, output_path: str) -> None:
        if self._pending_literals:
            self._flush_literal_pool(0)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"{'Literal':<12}{'LC (HEX)':<10}{'LC (DEC)'}\n")
            f.write("-" * 34 + "\n")
            for lit, loc in self._symtabs[MemoryBlock.POOL].items():
                f.write(f"{lit:<12}{loc:04X}{loc:>10}\n")

    def export_intermediate_table(self, output_path: str) -> None:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("Location counter  Symbol   Instructions  Reference\n")
            f.write("----------------  -------  ------------  ----------\n")
            for instr in self.instructions:
                label = getattr(instr, "label", None) or ""
                operand = getattr(instr, "operand", None) or ""
                if isinstance(instr, DirectiveInstruction):
                    mnem = instr.directive
                    hide = instr.directive.upper() == "USE"
                else:
                    mnem = getattr(instr, "mnemonic", "")
                    hide = False

                loc_str = "" if instr.location_counter is None or hide else f"{instr.location_counter:04X}"
                f.write(f"{loc_str:<16}  {label:<9}{mnem:<14}{operand}".rstrip() + "\n")

    # ── Properties (used by pass 2 and the Assembler class) ─────────────

    @property
    def block_locs(self) -> dict[MemoryBlock, int]:
        return dict(self._locs)

    @property
    def symbol_tables(self) -> dict[MemoryBlock, dict[str, int]]:
        return {b: dict(st) for b, st in self._symtabs.items()}

    @property
    def pool_anchor_block(self) -> Optional[MemoryBlock]:
        return self._pool_anchor_block
