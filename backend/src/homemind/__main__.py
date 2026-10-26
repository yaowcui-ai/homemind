"""Start the development API using project-local configuration."""

import sys

import uvicorn
from pydantic import ValidationError

from homemind.app import create_app
from homemind.config import Settings


def main() -> None:
    try:
        settings = Settings()
    except ValidationError:
        print(
            "HomeMind 配置无效：请检查 HOMEMIND_ENVIRONMENT、HOMEMIND_API_HOST "
            "和 HOMEMIND_API_PORT。",
            file=sys.stderr,
        )
        raise SystemExit(2) from None

    uvicorn.run(create_app(settings), host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    main()
