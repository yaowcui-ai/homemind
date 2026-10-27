"""Record the actual Python PID for an independently owned restart verification process."""

import argparse
import json
import os
from pathlib import Path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid-file", required=True)
    parser.add_argument("--nonce", required=True)
    args = parser.parse_args()
    Path(args.pid_file).write_text(
        json.dumps({"pid": os.getpid(), "nonce": args.nonce}), encoding="utf-8"
    )
    from homemind.__main__ import main

    main()
