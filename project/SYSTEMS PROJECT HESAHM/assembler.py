import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from main import main

main()
