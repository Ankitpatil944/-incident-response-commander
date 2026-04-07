from __future__ import annotations

import argparse

from incident_env.server.app import app
from incident_env.server.app import main as _package_main


def main(host: str = "0.0.0.0", port: int = 8000):
    return _package_main(host=host, port=port)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()
    # Validator probe: main()
    main(host=args.host, port=args.port)
