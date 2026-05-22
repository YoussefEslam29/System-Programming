from dataclasses import field, dataclass
from typing import Optional

@dataclass
class ParsedLine:
    line_no: int
    first: str
    second: Optional[str] = field(default=None)
    third: Optional[str] = field(default=None)

    @property
    def number_of_parts(self) -> int:
        return (
            (self.first is not None)
            + (self.second is not None)
            + (self.third is not None)
        )


class Preprocessor:
    def __init__(self) -> None:
        self.parsed_lines: list[ParsedLine] = []

    def process(self, input_lines: list[str]) -> list[ParsedLine]:
        result = []
        for i, line in enumerate(input_lines):
            line = line.strip()

            if "." in line:
                dot_idx = line.find(" .")
                if dot_idx != -1:
                    line = line[:dot_idx]

                if line.lstrip().startswith("."):
                    continue

            # Split by whitespace
            split_line = line.split()
            if not split_line:
                continue

            new_parsed_line = ParsedLine(
                line_no=i,
                first=split_line[0],
                second=split_line[1] if len(split_line) > 1 else None,
                third=split_line[2] if len(split_line) > 2 else None,
            )

            result.append(new_parsed_line)

        self.parsed_lines = result
        return result

    def export_to_file(self, output_path: str) -> None:
        header = f"{'Line':<8}{'First':<12}{'Second':<12}{'Third'}"
        separator = "-" * 45

        try:
            with open(output_path, "w") as f:
                f.write(header + "\n")
                f.write(separator + "\n")

                for line in self.parsed_lines:
                    # Convert None to empty string for clean printing
                    l_no = str(line.line_no)
                    lbl = line.first or ""
                    opc = line.second or ""
                    opr = line.third or ""

                    formatted_row = f"{l_no:<8}{lbl:<12}{opc:<12}{opr}"
                    f.write(formatted_row.rstrip() + "\n")

            print(
                f"Successfully exported {len(self.parsed_lines)} lines to {output_path}"
            )

        except IOError as e:
            print(f"Failed to write export file: {e}")
