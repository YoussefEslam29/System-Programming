from dataclasses import dataclass, field
from typing import Optional

from assembler_errors import (
    AssemblerError,
    DuplicateSymbolError,
    InvalidDirectiveOperandError,
    InvalidInstructionOperandError,
    POOLVARError,
    UnidentifiedBlockNameError,
    UnidentifiedSymbolError,
)
from instruction_set import MemoryBlock
from preprocessor import ParsedLine


@dataclass
class AssemblyInstruction:
    parsed_line: ParsedLine
    location_counter: Optional[int] = field(default=None)
    block: MemoryBlock = field(default=MemoryBlock.DEFAULT)
    size: int = field(default=0)
    object_code: Optional[str] = field(default=None)

    def _format_base(
        self,
        label: Optional[str],
        mnemonic: str,
        operand: Optional[str] = None,
    ) -> str:
        loc_str = (
            f"{self.location_counter:04X}"
            if self.location_counter is not None
            else "    "
        )

        lbl_str = (label or "").ljust(10)
        mne_str = mnemonic.ljust(8)
        opr_str = operand or ""

        prefix = f"{self.__class__.__name__}:".ljust(22)
        return f"{prefix} {loc_str}  {lbl_str}  {mne_str}  {opr_str}".rstrip()


@dataclass
class DirectiveInstruction(AssemblyInstruction):
    directive: str = field(default="")
    label: Optional[str] = field(default=None)
    operand: Optional[str] = field(default=None)

    def __str__(self) -> str:
        return self._format_base(self.label, self.directive, self.operand)


@dataclass
class Format1Instruction(AssemblyInstruction):
    mnemonic: str = field(default="")
    label: Optional[str] = field(default=None)

    def __str__(self) -> str:
        return self._format_base(self.label, self.mnemonic)


@dataclass
class Format2Instruction(AssemblyInstruction):
    mnemonic: str = field(default="")
    label: Optional[str] = field(default=None)
    operand: Optional[str] = field(default=None)

    def __str__(self) -> str:
        return self._format_base(self.label, self.mnemonic, self.operand)


@dataclass
class Format3Instruction(AssemblyInstruction):
    mnemonic: str = field(default="")
    label: Optional[str] = field(default=None)
    operand: Optional[str] = field(default=None)

    def __str__(self) -> str:
        return self._format_base(self.label, self.mnemonic, self.operand)


@dataclass
class Format4Instruction(AssemblyInstruction):
    mnemonic: str = field(default="")
    label: Optional[str] = field(default=None)
    operand: Optional[str] = field(default=None)

    def __str__(self) -> str:
        return self._format_base(self.label, self.mnemonic, self.operand)


@dataclass
class HTMEData:
    program_name: str
    start_address: int
    program_length: int
    exec_address: int
    text_entries: list[tuple[int, str]]         # (abs_addr, hex_string) — 2 chars per byte
    modification_records: list[tuple[int, int]] # (abs_addr, halfbytes)


from .pass_one import AssemblerPassOne
from .pass_two import AssemblerPassTwo

__all__ = [
    "AssemblyInstruction",
    "DirectiveInstruction",
    "Format1Instruction",
    "Format2Instruction",
    "Format3Instruction",
    "Format4Instruction",
    "DuplicateSymbolError",
    "InvalidDirectiveOperandError",
    "InvalidInstructionOperandError",
    "POOLVARError",
    "UnidentifiedBlockNameError",
    "UnidentifiedSymbolError",
    "AssemblerPassOne",
    "AssemblerPassTwo",
    "HTMEData",
]


class Assembler:
    def __init__(self) -> None:
        self.assembler_pass_one = AssemblerPassOne()
        self.assembler_pass_two = AssemblerPassTwo()

    def pass_one(self, parsed_lines: list[ParsedLine]) -> None:
        self.assembler_pass_one.process_pass_one(parsed_lines)

    def export_intermediate_table(self, output_path: str) -> None:
        self.assembler_pass_one.export_intermediate_table(output_path)

    def export_symbol_table(self, output_path: str) -> None:
        self.assembler_pass_two.export_symbol_table(
            output_path, self.assembler_pass_one.program_name
        )

    def export_pool_table(self, output_path: str) -> None:
        self.assembler_pass_one.export_pool_table(output_path)

    def pass_two(self) -> None:
        self.assembler_pass_two.process_pass_two(
            instructions=list(self.assembler_pass_one.instructions),
            start_address=self.assembler_pass_one.start_address,
            program_name=self.assembler_pass_one.program_name,
            block_locs=self.assembler_pass_one.block_locs,
            symbol_tables=self.assembler_pass_one.symbol_tables,
            pool_anchor_block=self.assembler_pass_one.pool_anchor_block,
        )

    def export_block_table(self, output_path: str) -> None:
        self.assembler_pass_two.export_block_table(output_path)

    def export_object_code_for_each_line(self, output_path: str) -> None:
        self.assembler_pass_two.export_object_code_for_each_line(output_path)

    def generate_HTME_and_export(self, output_path: str) -> None:
        self.assembler_pass_two.generate_HTME_and_export(output_path)

    def get_htme_data(self) -> HTMEData:
        return self.assembler_pass_two.get_HTME_data()
