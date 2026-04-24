import sys

# 1. THE INSTRUCTION SET DICTIONARY (OPTAB)
# This tells our assembler the hex value and format of each operation.
# We will populate this fully from your SICXE.pdf.
# Format: "MNEMONIC": ("HEX_OPCODE", FORMAT_NUMBER)
OPTAB = {
    "ADD":  ("18", 3),
    "ADDF": ("58", 3),
    "ADDR": ("90", 2),
    "AND":  ("40", 3),
    "CLEAR":("B4", 2),
    "COMP": ("28", 3),
    # ... we will add the rest here
}

# 2. MEMORY BLOCK MANAGEMENT
# Storing block names, their block numbers, current location counters, and start addresses.
blocks = {
    "DEFAULT":  {"num": 0, "locctr": 0, "start": 0, "length": 0},
    "DEFAULTB": {"num": 1, "locctr": 0, "start": 0, "length": 0},
    "CDATA":    {"num": 2, "locctr": 0, "start": 0, "length": 0},
    "CBLKS":    {"num": 3, "locctr": 0, "start": 0, "length": 0},
    "POOL":     {"num": 4, "locctr": 0, "start": 0, "length": 0}
}
current_block = "DEFAULT" # Programs always start in the default block

# 3. TABLES TO GENERATE
symbTable = {}  # Format: "LABEL": {"address": hex_val, "block": block_name}
poolTable = {}  # Format: "&OPERAND": {"address": hex_val}
intermediate_lines = [] # To store the parsed lines for Pass 2

def pass1(input_filename):
    global current_block
    
    try:
        with open(input_filename, 'r') as file:
            lines = file.readlines()
            
            for line in lines:
                # Our parsing logic goes here!
                # 1. Ignore comments (lines starting with .)
                # 2. Split line into Label, Opcode, Operand
                # 3. Check for block changes (USE opcode)
                # 4. Update the current block's Location Counter based on instruction format
                # 5. Store labels in symbTable and &operands in poolTable
                pass
                
    except FileNotFoundError:
        print(f"Error: {input_filename} not found.")
        sys.exit(1)

# Main Execution
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 assembler.py in.txt")
    else:
        input_file = sys.argv[1]
        print(f"Starting Pass 1 on {input_file}...")
        pass1(input_file)