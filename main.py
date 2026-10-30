"""Launcher: ``python main.py [run|check-media] [--dry-run] [--output-dir DIR]``."""
import sys

from presentation.cli import main

if __name__ == "__main__":
    sys.exit(main())
