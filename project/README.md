# Modified SIC/XE Assembler

## Project Overview
This project is a Python-based, two-pass assembler that emulates a modified version of the SIC/XE machine architecture. The primary modification from the standard architecture is the logical segmentation of the program into up to five distinct memory blocks.

### The Five Memory Blocks:
1. **DEFAULT:** Executable instructions (Formats 1 & 2).
2. **DEFAULTB:** Executable instructions (Formats 3 & 4).
3. **CDATA:** Smaller-sized data.
4. **CBLKS:** Larger memory blocks.
5. **POOL:** A special assembler-managed block built incrementally to store operand values prefixed with `&` (e.g., `&X'10'`).

## System Architecture

### Pass 1: Memory Allocation & Mapping
Reads the input assembly file (`in.txt`) to track the Location Counter (LC) across the different memory blocks. It catalogs labels into a Symbol Table and pooled variables into a Pool Table.
* **Outputs:** `symbTable.txt`, `PoolTable.txt`, `intermediate.txt`

### Pass 2: Object Code Generation
Utilizes the maps generated in Pass 1 to convert assembly instructions into hexadecimal object code. Organizes the output into standard HTME (Header, Text, Modification, End) records for memory loading.
* **Outputs:** `out_pass2.txt`, `HTME.txt`

## Current Development Status
* **Phase 1 (In Progress):** Python environment established. Standard SIC/XE Operation Code Table (OPTAB) fully mapped. Base architecture for memory block tracking and Pass 1 file parsing implemented.

## Usage
Run the assembler via the command line:
\`\`\`bash
python3 assembler.py in.txt
\`\`\`
*(Note: Requires a valid `in.txt` assembly file in the root directory).*