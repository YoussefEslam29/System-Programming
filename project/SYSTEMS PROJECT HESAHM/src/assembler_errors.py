from typing import Optional


class AssemblerError(Exception):
    def __init__(
        self, message: str, program_counter: int, line_no: Optional[int] = None
    ):
        super().__init__(message)
        self.program_counter = program_counter
        self.line_no = line_no if line_no is not None else program_counter


class InvalidMnemonicOrDirective(AssemblerError):
    def __init__(self, message: str, program_counter: int, line_no: Optional[int] = None):
        super().__init__(message, program_counter, line_no)


class UnidentifiedBlockNameError(AssemblerError):
    def __init__(self, message: str, program_counter: int, line_no: Optional[int] = None):
        super().__init__(message, program_counter, line_no)


class DuplicateSymbolError(AssemblerError):
    def __init__(self, message: str, program_counter: int, line_no: Optional[int] = None):
        super().__init__(message, program_counter, line_no)


class InvalidDirectiveOperandError(AssemblerError):
    def __init__(self, message: str, program_counter: int, line_no: Optional[int] = None):
        super().__init__(message, program_counter, line_no)


class UnidentifiedSymbolError(AssemblerError):
    def __init__(self, message: str, program_counter: int, line_no: Optional[int] = None):
        super().__init__(message, program_counter, line_no)


class POOLVARError(AssemblerError):
    def __init__(self, message: str, program_counter: int, line_no: Optional[int] = None):
        super().__init__(message, program_counter, line_no)


class InvalidInstructionOperandError(AssemblerError):
    def __init__(self, message: str, program_counter: int, line_no: Optional[int] = None):
        super().__init__(message, program_counter, line_no)
