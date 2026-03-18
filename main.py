# pyre-ignore-all-errors[21]
"""PESync - Entrypoint."""
import sys
import os

# Asegurar que la ruta src está en el path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.core.backup_logic import main  # pyre-ignore[21]

if __name__ == "__main__":
    try:
        main()
    finally:
        if sys.stdin and sys.stdin.isatty() and not os.environ.get("CI"):
            input("\nPresiona Enter para salir...")
