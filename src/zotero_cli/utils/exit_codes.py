"""CLI exit codes per design §9.1.

These constants are used by:
- CLIError subclasses (models/errors.py) to set exit_code
- commands/* outermost handler to call sys.exit(...)
"""

from __future__ import annotations

from typing import Final

EXIT_SUCCESS: Final[int] = 0
EXIT_USER_ERROR: Final[int] = 1
EXIT_NETWORK_ERROR: Final[int] = 2
EXIT_AUTH_ERROR: Final[int] = 3
EXIT_LOCAL_ERROR: Final[int] = 4
EXIT_USAGE_ERROR: Final[int] = 64
EXIT_INTERRUPTED: Final[int] = 130
