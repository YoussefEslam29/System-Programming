from enum import Enum
from dataclasses import dataclass


class InstructionFormat(Enum):
    FORMAT_1 = 1
    FORMAT_2 = 2
    FORMAT_3 = 3
    FORMAT_4 = 4
    DIRECTIVE = 5


class MemoryBlock(Enum):
    DEFAULT = "DEFAULT"
    DEFAULTB = "DEFAULTB"
    CDATA = "CDATA"
    CBLKS = "CBLKS"
    POOL = "POOLBLK"


class Register(Enum):
    A = 0
    X = 1
    L = 2
    B = 3
    S = 4
    T = 5
    F = 6
    PC = 8
    SW = 9


@dataclass(frozen=True)
class OpcodeInfo:
    mnemonic: str
    opcode: int
    fmt: InstructionFormat

    @property
    def opcode_hex(self) -> str:
        return f"{self.opcode:02X}"

    @property
    def size(self) -> int:
        for x in (
            InstructionFormat.FORMAT_1,
            InstructionFormat.FORMAT_2,
            InstructionFormat.FORMAT_3,
        ):
            if x == self.fmt.value:
                return self.fmt.value

        return 3


_F1, _F2, _F34 = (
    InstructionFormat.FORMAT_1,
    InstructionFormat.FORMAT_2,
    InstructionFormat.FORMAT_3,
)

_RAW_OPCODES = [
    ("FIX", 0xC4, _F1),
    ("FLOAT", 0xC0, _F1),
    ("HIO", 0xF4, _F1),
    ("NORM", 0xC8, _F1),
    ("SIO", 0xF0, _F1),
    ("TIO", 0xF8, _F1),
    ("ADDR", 0x90, _F2),
    ("CLEAR", 0xB4, _F2),
    ("COMPR", 0xA0, _F2),
    ("DIVR", 0x9C, _F2),
    ("MULR", 0x98, _F2),
    ("RMO", 0xAC, _F2),
    ("SHIFTL", 0xA4, _F2),
    ("SHIFTR", 0xA8, _F2),
    ("SUBR", 0x94, _F2),
    ("SVC", 0xB0, _F2),
    ("TIXR", 0xB8, _F2),
    ("ADD", 0x18, _F34),
    ("ADDF", 0x58, _F34),
    ("AND", 0x40, _F34),
    ("COMP", 0x28, _F34),
    ("COMPF", 0x88, _F34),
    ("DIV", 0x24, _F34),
    ("DIVF", 0x64, _F34),
    ("J", 0x3C, _F34),
    ("JEQ", 0x30, _F34),
    ("JGT", 0x34, _F34),
    ("JLT", 0x38, _F34),
    ("JSUB", 0x48, _F34),
    ("LDA", 0x00, _F34),
    ("LDB", 0x68, _F34),
    ("LDCH", 0x50, _F34),
    ("LDF", 0x70, _F34),
    ("LDL", 0x08, _F34),
    ("LDS", 0x6C, _F34),
    ("LDT", 0x74, _F34),
    ("LDX", 0x04, _F34),
    ("LPS", 0xD0, _F34),
    ("MUL", 0x20, _F34),
    ("MULF", 0x60, _F34),
    ("OR", 0x44, _F34),
    ("RD", 0xD8, _F34),
    ("RSUB", 0x4C, _F34),
    ("SSK", 0xEC, _F34),
    ("STA", 0x0C, _F34),
    ("STB", 0x78, _F34),
    ("STCH", 0x54, _F34),
    ("STF", 0x80, _F34),
    ("STI", 0xD4, _F34),
    ("STL", 0x14, _F34),
    ("STS", 0x7C, _F34),
    ("STSW", 0xE8, _F34),
    ("STT", 0x84, _F34),
    ("STX", 0x10, _F34),
    ("SUB", 0x1C, _F34),
    ("SUBF", 0x5C, _F34),
    ("TD", 0xE0, _F34),
    ("TIX", 0x2C, _F34),
    ("WD", 0xDC, _F34),
]

OPCODE_TABLE = {m: OpcodeInfo(m, o, f) for m, o, f in _RAW_OPCODES}

DIRECTIVE_SET: frozenset[str] = frozenset(
    {
        "START",
        "END",
        "BYTE",
        "WORD",
        "RESB",
        "RESW",
        "BASE",
        "NOBASE",
        "USE",
        "EXTDEF",
        "EXTREF",
    }
)

REGISTER_TABLE: dict[str, int] = {reg.name: reg.value for reg in Register}


def lookup_opcode(mnemonic: str) -> OpcodeInfo | None:
    return OPCODE_TABLE.get(mnemonic.lstrip("+").upper())


def is_opcode(mnemonic: str) -> bool:
    return lookup_opcode(mnemonic) is not None


def is_directive(token: str) -> bool:
    return token.upper() in DIRECTIVE_SET


def is_supported(token: str) -> bool:
    return is_opcode(token) or is_directive(token)


def is_format4(mnemonic: str) -> bool:
    return mnemonic.startswith("+")


def is_valid_block(name: str) -> bool:
    return name.upper() in {b.value for b in MemoryBlock}
