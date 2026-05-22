import argparse
import re
import sys
from pathlib import Path

from assembler import Assembler
from assembler_errors import AssemblerError
from memory_viewer import MemoryViewer
from preprocessor import Preprocessor

# FILE_PREFIX = "output/"
FILE_PREFIX = "./"

INTERMEDIATE_FILE_NAME = f"{FILE_PREFIX}intermediate.txt"
SYMBOL_TABLE_FILE_NAME = f"{FILE_PREFIX}symbTable.txt"
POOL_TABLE_FILE_NAME   = f"{FILE_PREFIX}PoolTable.txt"
BLOCK_TABLE_FILE_NAME  = f"{FILE_PREFIX}blockTable.txt"
PASS2_OUTPUT_FILE_NAME = f"{FILE_PREFIX}out_pass2.txt"
HTME_OUTPUT_FILE_NAME  = f"{FILE_PREFIX}HTME.txt"


def _format_error_name(cls_name: str) -> str:
    name = cls_name.removesuffix("Error")
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="assembler",
        description="SIC/XE two-pass assembler",
    )
    parser.add_argument("input_file", type=Path, help="SIC/XE source file path")
    args = parser.parse_args()

    input_file: Path = args.input_file

    if not input_file.exists():
        print(f"Error: File '{input_file}' not found.", file=sys.stderr)
        sys.exit(1)

    try:
        lines = input_file.read_text(encoding="utf-8").splitlines()

        preprocessor = Preprocessor()
        assembler    = Assembler()

        print("Preprocessing...")
        parsed_lines = preprocessor.process(lines)

        print("Running Pass 1...")
        assembler.pass_one(parsed_lines)
        Path(FILE_PREFIX).mkdir(exist_ok=True)
        assembler.export_intermediate_table(INTERMEDIATE_FILE_NAME)
        assembler.export_pool_table(POOL_TABLE_FILE_NAME)

        print("Running Pass 2...")
        assembler.pass_two()
        assembler.export_symbol_table(SYMBOL_TABLE_FILE_NAME)
        assembler.export_block_table(BLOCK_TABLE_FILE_NAME)
        assembler.export_object_code_for_each_line(PASS2_OUTPUT_FILE_NAME)
        assembler.generate_HTME_and_export(HTME_OUTPUT_FILE_NAME)

        print("\nAssembly complete!")

        print("Launching memory viewer...")
        viewer = MemoryViewer()
        viewer.load(assembler.get_htme_data())
        viewer.show()

    except AssemblerError as e:
        name = _format_error_name(e.__class__.__name__)
        error_content = (
            f"Error : {name}\n"
            f"PC    : {e.program_counter:06X}\n"
            f"Line  : line {e.line_no}\n"
            f"Detail: {e}"
        )
        try:
            Path("error.txt").write_text(error_content, encoding="utf-8")
        except OSError as write_err:
            print(f"Failed to write error file: {write_err}", file=sys.stderr)

        print(error_content, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
