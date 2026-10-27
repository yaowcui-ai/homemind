"""Run the real API against HomeMind's isolated MySQL test database."""

import os
import sys

from local_config import test_environment

if __name__ == "__main__":
    try:
        os.environ.update(test_environment())
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    # Import settings only after choosing the explicit test database.
    from homemind.__main__ import main

    main()
