"""
SIC/XE Assembler — Main Entry Point
Orchestrates the two-pass assembly process.

Usage:
    python assembler.py in.txt
"""

import sys
from pass2 import pass2


# ───────────────────────────────────────────────────────────────────────────
# Entry point
# ───────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) >= 2:
        input_file = sys.argv[1]
    else:
        input_file = "in.txt"

    print(f"Starting Pass 2 on {input_file}...")
    pass2(input_file)