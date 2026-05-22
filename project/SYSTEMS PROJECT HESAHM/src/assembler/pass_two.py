from typing import Optional

from instruction_set import MemoryBlock, REGISTER_TABLE, lookup_opcode
from assembler_errors import (
    InvalidDirectiveOperandError,
    InvalidInstructionOperandError,
    InvalidMnemonicOrDirective,
    POOLVARError,
    UnidentifiedSymbolError,
)

from . import (
    AssemblyInstruction,
    DirectiveInstruction,
    Format1Instruction,
    Format2Instruction,
    Format3Instruction,
    Format4Instruction,
    HTMEData,
)


class AssemblerPassTwo:
    _USER_BLOCKS: tuple[MemoryBlock, ...] = (
        MemoryBlock.DEFAULT,
        MemoryBlock.DEFAULTB,
        MemoryBlock.CDATA,
        MemoryBlock.CBLKS,
    )

    def __init__(self) -> None:
        self.instructions: list[AssemblyInstruction] = []
        self.start_address = 0
        self.program_name = ""
        self._block_locs: dict[MemoryBlock, int] = {}
        self._symbol_tables: dict[MemoryBlock, dict[str, int]] = {}
        self._pool_anchor_block: Optional[MemoryBlock] = None
        self._block_base_addresses: dict[MemoryBlock, int] = {}
        self._pool_base_address: Optional[int] = None
        self.program_length = 0
        self.modification_records: list[tuple[int, int]] = []
        self._pool_data_entries: list[tuple[int, str, str]] = []

    def _get_block_loc(self, block: MemoryBlock) -> int:
        return self._block_locs.get(block, 0)

    def _block_symtab(self, block: MemoryBlock) -> dict[str, int]:
        return self._symbol_tables.get(block, {})

    def _lookup_symbol_entry(self, symbol: str) -> Optional[tuple[MemoryBlock, int]]:
        for block in (*self._USER_BLOCKS, MemoryBlock.POOL):
            symtab = self._block_symtab(block)
            if symbol in symtab:
                return block, symtab[symbol]
        return None

    def _try_parse_int(self, token: str) -> Optional[int]:
        cleaned = token.strip()
        if not cleaned:
            return None
        try:
            return int(cleaned, 0)
        except ValueError:
            return None

    def _block_relative_loc(self, block: MemoryBlock, block_loc: int) -> int:
        if block == MemoryBlock.DEFAULT:
            return block_loc - self.start_address
        return block_loc

    def _block_size(self, block: MemoryBlock) -> int:
        return max(0, self._block_relative_loc(block, self._get_block_loc(block)))

    def _build_memory_layout(self) -> None:
        block_sizes = {block: self._block_size(block) for block in self._USER_BLOCKS}
        pool_size = self._get_block_loc(MemoryBlock.POOL)

        insert_after = self._pool_anchor_block
        if insert_after is None or insert_after not in self._USER_BLOCKS:
            insert_after = self._USER_BLOCKS[-1]

        current = self.start_address
        self._block_base_addresses = {}
        self._pool_base_address = None

        for block in self._USER_BLOCKS:
            self._block_base_addresses[block] = current
            current += block_sizes[block]

            if pool_size > 0 and block == insert_after:
                self._pool_base_address = current
                self._block_base_addresses[MemoryBlock.POOL] = current
                current += pool_size

        if pool_size > 0 and self._pool_base_address is None:
            self._pool_base_address = current
            self._block_base_addresses[MemoryBlock.POOL] = current
            current += pool_size

        self.program_length = current - self.start_address

    def _absolute_address_from_block_loc(
        self, block: MemoryBlock, block_loc: int
    ) -> int:
        block_base = self._block_base_addresses.get(block)
        if block_base is None:
            raise ValueError(f"Missing base address for memory block {block.value}")
        return block_base + self._block_relative_loc(block, block_loc)

    def _instruction_abs_loc(self, instruction: AssemblyInstruction) -> int:
        if instruction.location_counter is None:
            return self.start_address
        return self._absolute_address_from_block_loc(
            instruction.block,
            instruction.location_counter,
        )

    def _lookup_symbol_absolute(
        self, symbol: str, program_counter: int, line_no: int
    ) -> int:
        symbol_entry = self._lookup_symbol_entry(symbol)
        if symbol_entry is None:
            raise UnidentifiedSymbolError(
                f"Unidentified symbol '{symbol}'",
                program_counter,
                line_no,
            )
        symbol_block, symbol_loc = symbol_entry
        return self._absolute_address_from_block_loc(symbol_block, symbol_loc)

    def _resolve_term_absolute(self, term: str, current_loc: int, line_no: int) -> int:
        cleaned = term.strip()
        while cleaned.startswith(("#", "@")):
            cleaned = cleaned[1:]

        if cleaned.endswith(",X"):
            cleaned = cleaned[:-2]

        if cleaned == "*":
            return current_loc

        parsed_number = self._try_parse_int(cleaned)
        if parsed_number is not None:
            return parsed_number

        return self._lookup_symbol_absolute(cleaned, current_loc, line_no)

    def _evaluate_expression_absolute(
        self, expr: str, current_loc: int, line_no: int
    ) -> int:
        expression = expr.replace(" ", "")
        if not expression:
            raise InvalidDirectiveOperandError(
                "Empty directive operand", current_loc, line_no
            )

        plus_idx = expression.find("+", 1)
        minus_idx = expression.find("-", 1)

        op_idx = -1
        operator = ""
        if plus_idx != -1 and (minus_idx == -1 or plus_idx < minus_idx):
            op_idx = plus_idx
            operator = "+"
        elif minus_idx != -1:
            op_idx = minus_idx
            operator = "-"

        if op_idx == -1:
            return self._resolve_term_absolute(expression, current_loc, line_no)

        lhs = expression[:op_idx]
        rhs = expression[op_idx + 1 :]
        lhs_value = self._resolve_term_absolute(lhs, current_loc, line_no)
        rhs_value = self._resolve_term_absolute(rhs, current_loc, line_no)
        return lhs_value + rhs_value if operator == "+" else lhs_value - rhs_value

    def _word_object_code(
        self, operand: Optional[str], program_counter: int, line_no: int
    ) -> str:
        if operand is None:
            raise InvalidDirectiveOperandError(
                "Directive 'WORD' requires an operand",
                program_counter,
                line_no,
            )

        value = self._evaluate_expression_absolute(operand, program_counter, line_no)
        if value < -(1 << 23) or value > 0xFFFFFF:
            raise InvalidDirectiveOperandError(
                f"WORD operand '{operand}' is out of 24-bit range",
                program_counter,
                line_no,
            )
        return f"{(value & 0xFFFFFF):06X}"

    def _byte_object_code(
        self, operand: Optional[str], program_counter: int, line_no: int
    ) -> str:
        if operand is None:
            raise InvalidDirectiveOperandError(
                "Directive 'BYTE' requires an operand",
                program_counter,
                line_no,
            )

        cleaned = operand.strip()
        if len(cleaned) >= 3 and cleaned[1] == "'" and cleaned.endswith("'"):
            kind = cleaned[0].upper()
            payload = cleaned[2:-1]
            if kind == "C":
                return payload.encode("ascii").hex().upper()
            if kind == "X":
                if len(payload) % 2 != 0:
                    raise InvalidDirectiveOperandError(
                        "Hex BYTE operand must contain an even number of digits",
                        program_counter,
                        line_no,
                    )
                return payload.upper()

        parsed_number = self._try_parse_int(cleaned)
        if parsed_number is not None:
            if parsed_number < 0 or parsed_number > 0xFF:
                raise InvalidDirectiveOperandError(
                    f"BYTE numeric operand '{operand}' is out of 8-bit range",
                    program_counter,
                    line_no,
                )
            return f"{parsed_number:02X}"

        raise InvalidDirectiveOperandError(
            f"Unsupported BYTE operand '{operand}'",
            program_counter,
            line_no,
        )

    def _byte_or_word_like_object_code(
        self, token: str, program_counter: int, line_no: int
    ) -> str:
        cleaned = token.strip()
        if len(cleaned) >= 3 and cleaned[1] == "'" and cleaned.endswith("'"):
            kind = cleaned[0].upper()
            payload = cleaned[2:-1]
            if kind == "C":
                return payload.encode("ascii").hex().upper()
            if kind == "X":
                if len(payload) % 2 != 0:
                    raise InvalidDirectiveOperandError(
                        "Hex literal must contain an even number of digits",
                        program_counter,
                        line_no,
                    )
                return payload.upper()

        parsed_number = self._try_parse_int(cleaned)
        if parsed_number is not None:
            if parsed_number < -(1 << 23) or parsed_number > 0xFFFFFF:
                raise InvalidDirectiveOperandError(
                    f"Literal '{token}' is out of 24-bit range",
                    program_counter,
                    line_no,
                )
            return f"{(parsed_number & 0xFFFFFF):06X}"

        raise InvalidDirectiveOperandError(
            f"Unsupported literal format '{token}'",
            program_counter,
            line_no,
        )

    def _literal_object_code(
        self, literal: str, program_counter: int, line_no: int
    ) -> str:
        token = literal[1:] if literal.startswith("&") else literal
        return self._byte_or_word_like_object_code(token, program_counter, line_no)

    def _format1_object_code(self, instruction: Format1Instruction) -> str:
        opcode_info = lookup_opcode(instruction.mnemonic)
        if opcode_info is None:
            raise InvalidMnemonicOrDirective(
                f"Unknown opcode '{instruction.mnemonic}'",
                self._instruction_abs_loc(instruction),
                instruction.parsed_line.line_no,
            )
        return f"{opcode_info.opcode:02X}"

    def _parse_register(self, token: str, program_counter: int, line_no: int) -> int:
        register_code = REGISTER_TABLE.get(token.strip().upper())
        if register_code is None:
            raise InvalidInstructionOperandError(
                f"Invalid register name '{token}'",
                program_counter,
                line_no,
            )
        return register_code

    def _format2_object_code(self, instruction: Format2Instruction) -> str:
        opcode_info = lookup_opcode(instruction.mnemonic)
        if opcode_info is None:
            raise InvalidMnemonicOrDirective(
                f"Unknown opcode '{instruction.mnemonic}'",
                self._instruction_abs_loc(instruction),
                instruction.parsed_line.line_no,
            )

        mnemonic = instruction.mnemonic.upper()
        operand = (instruction.operand or "").strip()
        line_no = instruction.parsed_line.line_no
        instruction_loc = self._instruction_abs_loc(instruction)
        parts = [part.strip() for part in operand.split(",") if part.strip()]

        r1 = 0
        r2 = 0

        if mnemonic in {"CLEAR", "TIXR"}:
            if len(parts) != 1:
                raise InvalidInstructionOperandError(
                    f"Instruction '{mnemonic}' requires one register operand",
                    instruction_loc,
                    line_no,
                )
            r1 = self._parse_register(parts[0], instruction_loc, line_no)
        elif mnemonic in {"SHIFTL", "SHIFTR"}:
            if len(parts) != 2:
                raise InvalidInstructionOperandError(
                    f"Instruction '{mnemonic}' requires register,count operands",
                    instruction_loc,
                    line_no,
                )
            r1 = self._parse_register(parts[0], instruction_loc, line_no)
            shift_count = self._try_parse_int(parts[1])
            if shift_count is None or not (0 <= shift_count <= 0xF):
                raise InvalidInstructionOperandError(
                    f"Invalid shift count '{parts[1]}' for '{mnemonic}'",
                    instruction_loc,
                    line_no,
                )
            r2 = shift_count
        elif mnemonic == "SVC":
            if len(parts) != 1:
                raise InvalidInstructionOperandError(
                    "Instruction 'SVC' requires one numeric operand",
                    instruction_loc,
                    line_no,
                )
            svc_number = self._try_parse_int(parts[0])
            if svc_number is None or not (0 <= svc_number <= 0xF):
                raise InvalidInstructionOperandError(
                    f"Invalid SVC number '{parts[0]}'",
                    instruction_loc,
                    line_no,
                )
            r1 = svc_number
        else:
            if len(parts) != 2:
                raise InvalidInstructionOperandError(
                    f"Instruction '{mnemonic}' requires two register operands",
                    instruction_loc,
                    line_no,
                )
            r1 = self._parse_register(parts[0], instruction_loc, line_no)
            r2 = self._parse_register(parts[1], instruction_loc, line_no)

        return f"{opcode_info.opcode:02X}{r1:X}{r2:X}"

    def _resolve_target_address(
        self,
        token: str,
        program_counter: int,
        line_no: int,
        current_loc: Optional[int] = None,
    ) -> tuple[int, bool]:
        cleaned = token.strip()
        if cleaned == "*":
            if current_loc is None:
                raise InvalidInstructionOperandError(
                    "Cannot resolve '*' without a current location",
                    program_counter,
                    line_no,
                )
            return current_loc, False

        parsed_number = self._try_parse_int(cleaned)
        if parsed_number is not None:
            return parsed_number, False

        symbol_entry = self._lookup_symbol_entry(cleaned)
        if symbol_entry is None:
            raise UnidentifiedSymbolError(
                f"Unidentified symbol '{cleaned}'",
                program_counter,
                line_no,
            )

        symbol_block, symbol_loc = symbol_entry
        symbol_abs = self._absolute_address_from_block_loc(symbol_block, symbol_loc)
        return symbol_abs, symbol_block == MemoryBlock.POOL

    def _split_indexed_operand(
        self, operand: str, program_counter: int, line_no: int
    ) -> tuple[str, bool]:
        cleaned = operand.strip()
        if cleaned.upper().endswith(",X"):
            target = cleaned[:-2].strip()
            if not target:
                raise InvalidInstructionOperandError(
                    f"Invalid indexed operand '{operand}'",
                    program_counter,
                    line_no,
                )
            return target, True
        return cleaned, False

    def _format3_object_code(
        self,
        instruction: Format3Instruction,
        base_register: Optional[int],
    ) -> str:
        opcode_info = lookup_opcode(instruction.mnemonic)
        if opcode_info is None:
            raise InvalidMnemonicOrDirective(
                f"Unknown opcode '{instruction.mnemonic}'",
                self._instruction_abs_loc(instruction),
                instruction.parsed_line.line_no,
            )

        opcode = opcode_info.opcode
        line_no = instruction.parsed_line.line_no
        instruction_loc = self._instruction_abs_loc(instruction)
        mnemonic = instruction.mnemonic.upper()
        operand = instruction.operand.strip() if instruction.operand else None

        if mnemonic == "RSUB":
            op = (opcode & 0xFC) | 0x03
            return f"{op:02X}0000"

        if operand is None:
            raise InvalidInstructionOperandError(
                f"Instruction '{mnemonic}' requires an operand",
                instruction_loc,
                line_no,
            )

        n, i = 1, 1
        target_operand = operand
        if target_operand.startswith("#"):
            n, i = 0, 1
            target_operand = target_operand[1:].strip()
        elif target_operand.startswith("@"):
            n, i = 1, 0
            target_operand = target_operand[1:].strip()

        target_operand, is_indexed = self._split_indexed_operand(
            target_operand, instruction_loc, line_no
        )
        if is_indexed and n == 0:
            raise InvalidInstructionOperandError(
                "Immediate addressing cannot be indexed",
                instruction_loc,
                line_no,
            )

        x = 1 if is_indexed else 0
        b = 0
        p = 0
        e = 0

        if n == 0 and i == 1:
            immediate_value = self._try_parse_int(target_operand)
            if immediate_value is not None:
                if not (0 <= immediate_value <= 0xFFF):
                    raise InvalidInstructionOperandError(
                        f"Immediate value '{target_operand}' cannot fit in format-3 displacement",
                        instruction_loc,
                        line_no,
                    )
                op = (opcode & 0xFC) | ((n << 1) | i)
                flags = (x << 3) | (b << 2) | (p << 1) | e
                return f"{op:02X}{flags:X}{immediate_value & 0xFFF:03X}"

        target_address, is_pool_reference = self._resolve_target_address(
            target_operand,
            instruction_loc,
            line_no,
            instruction_loc,
        )
        next_loc = instruction_loc + 3
        pc_disp = target_address - next_loc

        if -2048 <= pc_disp <= 2047:
            p = 1
            displacement = pc_disp & 0xFFF
        elif (
            base_register is not None and 0 <= (target_address - base_register) <= 0xFFF
        ):
            b = 1
            displacement = target_address - base_register
        else:
            if is_pool_reference:
                raise POOLVARError(
                    f"POOLVAR '{target_operand}' cannot be addressed using PC-relative or Base-relative mode",
                    instruction_loc,
                    line_no,
                )
            raise InvalidInstructionOperandError(
                f"Operand '{target_operand}' cannot be addressed using PC-relative or Base-relative mode",
                instruction_loc,
                line_no,
            )

        op = (opcode & 0xFC) | ((n << 1) | i)
        flags = (x << 3) | (b << 2) | (p << 1) | e
        return f"{op:02X}{flags:X}{displacement:03X}"

    def _format4_object_code(self, instruction: Format4Instruction) -> str:
        opcode_info = lookup_opcode(instruction.mnemonic)
        if opcode_info is None:
            raise InvalidMnemonicOrDirective(
                f"Unknown opcode '{instruction.mnemonic}'",
                self._instruction_abs_loc(instruction),
                instruction.parsed_line.line_no,
            )

        line_no = instruction.parsed_line.line_no
        instruction_loc = self._instruction_abs_loc(instruction)
        opcode = opcode_info.opcode

        operand = instruction.operand.strip() if instruction.operand else None
        if operand is None:
            raise InvalidInstructionOperandError(
                f"Instruction '{instruction.mnemonic}' requires an operand",
                instruction_loc,
                line_no,
            )

        n, i = 1, 1
        target_operand = operand
        if target_operand.startswith("#"):
            n, i = 0, 1
            target_operand = target_operand[1:].strip()
        elif target_operand.startswith("@"):
            n, i = 1, 0
            target_operand = target_operand[1:].strip()

        target_operand, is_indexed = self._split_indexed_operand(
            target_operand, instruction_loc, line_no
        )
        if is_indexed and n == 0:
            raise InvalidInstructionOperandError(
                "Immediate addressing cannot be indexed",
                instruction_loc,
                line_no,
            )

        target_address: int
        needs_modification_record = True

        if n == 0 and i == 1:
            immediate_value = self._try_parse_int(target_operand)
            if immediate_value is not None:
                if not (0 <= immediate_value <= 0xFFFFF):
                    raise InvalidInstructionOperandError(
                        f"Immediate value '{target_operand}' cannot fit in format-4 address field",
                        instruction_loc,
                        line_no,
                    )
                target_address = immediate_value
                needs_modification_record = False
            else:
                target_address, _ = self._resolve_target_address(
                    target_operand,
                    instruction_loc,
                    line_no,
                    instruction_loc,
                )
        else:
            target_address, _ = self._resolve_target_address(
                target_operand,
                instruction_loc,
                line_no,
                instruction_loc,
            )

        if not (0 <= target_address <= 0xFFFFF):
            raise InvalidInstructionOperandError(
                f"Address '{target_operand}' cannot fit in format-4 address field",
                instruction_loc,
                line_no,
            )

        if needs_modification_record:
            self.modification_records.append((instruction_loc + 1, 5))

        x = 1 if is_indexed else 0
        b = 0
        p = 0
        e = 1

        op = (opcode & 0xFC) | ((n << 1) | i)
        flags = (x << 3) | (b << 2) | (p << 1) | e
        return f"{op:02X}{flags:X}{target_address:05X}"

    def _collect_pool_data_entries(self) -> None:
        self._pool_data_entries = []
        for literal, relative_loc in sorted(
            self._block_symtab(MemoryBlock.POOL).items(),
            key=lambda item: item[1],
        ):
            absolute_loc = self._absolute_address_from_block_loc(
                MemoryBlock.POOL,
                relative_loc,
            )
            object_code = self._literal_object_code(literal, absolute_loc, 0)
            self._pool_data_entries.append((absolute_loc, literal, object_code))

    def process_pass_two(
        self,
        *,
        instructions: list[AssemblyInstruction],
        start_address: int,
        program_name: str,
        block_locs: dict[MemoryBlock, int],
        symbol_tables: dict[MemoryBlock, dict[str, int]],
        pool_anchor_block: Optional[MemoryBlock],
    ) -> None:
        self.instructions = list(instructions)
        self.start_address = start_address
        self.program_name = program_name
        self._block_locs = dict(block_locs)
        self._symbol_tables = {
            block: dict(symbols) for block, symbols in symbol_tables.items()
        }
        self._pool_anchor_block = pool_anchor_block

        self._build_memory_layout()
        self.modification_records = []

        for instruction in self.instructions:
            instruction.object_code = None

        base_register_value: Optional[int] = None

        for instruction in self.instructions:
            if isinstance(instruction, DirectiveInstruction):
                directive = instruction.directive.upper()
                line_no = instruction.parsed_line.line_no
                instruction_loc = self._instruction_abs_loc(instruction)

                if directive == "BASE":
                    if instruction.operand is None:
                        raise InvalidDirectiveOperandError(
                            "Directive 'BASE' requires an operand",
                            instruction_loc,
                            line_no,
                        )
                    base_register_value = self._evaluate_expression_absolute(
                        instruction.operand,
                        instruction_loc,
                        line_no,
                    )
                elif directive == "NOBASE":
                    base_register_value = None
                elif directive == "WORD":
                    instruction.object_code = self._word_object_code(
                        instruction.operand,
                        instruction_loc,
                        line_no,
                    )
                elif directive == "BYTE":
                    instruction.object_code = self._byte_object_code(
                        instruction.operand,
                        instruction_loc,
                        line_no,
                    )
                continue

            if isinstance(instruction, Format1Instruction):
                instruction.object_code = self._format1_object_code(instruction)
            elif isinstance(instruction, Format2Instruction):
                instruction.object_code = self._format2_object_code(instruction)
            elif isinstance(instruction, Format3Instruction):
                instruction.object_code = self._format3_object_code(
                    instruction,
                    base_register_value,
                )
            elif isinstance(instruction, Format4Instruction):
                instruction.object_code = self._format4_object_code(instruction)

        self._collect_pool_data_entries()

    def export_block_table(self, output_path: str) -> None:
        _display_name = {MemoryBlock.POOL: "POOL"}
        blocks_by_addr = sorted(self._block_base_addresses.items(), key=lambda x: x[1])
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"{'BLOCK NAME':<12}{'BLOCK NUMBER':<14}{'ADDRESS':<9}SIZE\n")
            for number, (block, base_addr) in enumerate(blocks_by_addr):
                name = _display_name.get(block, block.value)
                size = (
                    self._block_size(block)
                    if block != MemoryBlock.POOL
                    else self._get_block_loc(MemoryBlock.POOL)
                )
                f.write(f"{name:<12}{number:<14}{base_addr:04X}     {size:04X}\n")
            f.write(f"\nTotal program length: {self.program_length:04X}\n")

    def export_symbol_table(self, output_path: str, program_name: str) -> None:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"{'SYMBOL NAME':<13}ADDRESS\n")
            for block in self._USER_BLOCKS:
                for symbol, loc in self._block_symtab(block).items():
                    if symbol == program_name:
                        continue
                    abs_addr = self._absolute_address_from_block_loc(block, loc)
                    f.write(f"{symbol:<13}{abs_addr:04X}\n")

    def export_object_code_for_each_line(self, output_path: str) -> None:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("Location counter  Symbol   Instructions  Reference   Obj. code\n")
            f.write(
                "----------------  -------  ------------  ----------  --------------\n"
            )

            for instruction in self.instructions:
                label = getattr(instruction, "label", None) or ""
                operand = getattr(instruction, "operand", None) or ""

                if isinstance(instruction, DirectiveInstruction):
                    mnemonic_or_directive = instruction.directive
                    hide_location = instruction.directive.upper() == "USE"
                else:
                    mnemonic_or_directive = getattr(instruction, "mnemonic", "")
                    hide_location = False

                location = (
                    ""
                    if instruction.location_counter is None or hide_location
                    else f"{instruction.location_counter:04X}"
                )
                obj_code = (
                    instruction.object_code
                    if instruction.object_code is not None
                    else "No object code"
                )

                row = (
                    f"{location:<16}  "
                    f"{label:<9}"
                    f"{mnemonic_or_directive:<14}"
                    f"{operand:<12}"
                    f"{obj_code}"
                ).rstrip()
                f.write(row + "\n")

    def _text_record_entries_by_block(self) -> list[list[tuple[int, str]]]:
        block_entries: dict[MemoryBlock, list[tuple[int, str]]] = {
            b: [] for b in (*self._USER_BLOCKS, MemoryBlock.POOL)
        }
        for instr in self.instructions:
            if instr.object_code is None:
                continue
            block_entries[instr.block].append(
                (self._instruction_abs_loc(instr), instr.object_code)
            )
        for abs_loc, _, obj_code in self._pool_data_entries:
            block_entries[MemoryBlock.POOL].append((abs_loc, obj_code))

        result = []
        for block in self._USER_BLOCKS:
            entries = sorted(block_entries[block], key=lambda x: x[0])
            if entries:
                result.append(entries)
        pool = sorted(block_entries[MemoryBlock.POOL], key=lambda x: x[0])
        if pool:
            result.append(pool)
        return result

    def _text_record_entries(self) -> list[tuple[int, str]]:
        entries: list[tuple[int, str]] = []

        for instruction in self.instructions:
            if instruction.object_code is None:
                continue
            entries.append(
                (self._instruction_abs_loc(instruction), instruction.object_code)
            )

        for absolute_loc, _, object_code in self._pool_data_entries:
            entries.append((absolute_loc, object_code))

        entries.sort(key=lambda item: item[0])
        return entries

    def _build_text_records(self, entries: list[tuple[int, str]]) -> list[str]:
        if not entries:
            return []

        records: list[str] = []
        current_start = entries[0][0]
        current_codes: list[str] = []
        current_length = 0
        current_end = current_start

        for address, object_code in entries:
            object_len = len(object_code) // 2

            if current_codes and (
                address != current_end or current_length + object_len > 30
            ):
                records.append(
                    f"T.{current_start:06X}.{current_length:02X}."
                    + ".".join(current_codes)
                )
                current_start = address
                current_codes = []
                current_length = 0
                current_end = address

            current_codes.append(object_code)
            current_length += object_len
            current_end = address + object_len

        if current_codes:
            records.append(
                f"T.{current_start:06X}.{current_length:02X}." + ".".join(current_codes)
            )

        return records

    def _end_execution_address(self) -> int:
        for instruction in self.instructions:
            if (
                isinstance(instruction, DirectiveInstruction)
                and instruction.directive.upper() == "END"
                and instruction.operand is not None
            ):
                return self._evaluate_expression_absolute(
                    instruction.operand.strip(),
                    self._instruction_abs_loc(instruction),
                    instruction.parsed_line.line_no,
                )
        return self.start_address

    def generate_HTME_and_export(self, output_path: str) -> None:
        header_name = (self.program_name or "").upper()[:6].ljust(6, "X")
        header_record = (
            f"H.{header_name}.{self.start_address:06X}.{self.program_length:06X}"
        )

        text_records = []
        for group in self._text_record_entries_by_block():
            text_records.extend(self._build_text_records(group))
        modification_records = [
            f"M.{address:06X}.{half_bytes:02X}"
            for address, half_bytes in self.modification_records
        ]
        end_record = f"E.{self._end_execution_address():06X}"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header_record + "\n")
            for record in text_records:
                f.write(record + "\n")
            for record in modification_records:
                f.write(record + "\n")
            f.write(end_record + "\n")

    def get_HTME_data(self):
        return HTMEData(
            program_name=self.program_name,
            start_address=self.start_address,
            program_length=self.program_length,
            exec_address=self._end_execution_address(),
            text_entries=self._text_record_entries(),
            modification_records=list(self.modification_records),
        )
