"""Entry point: python -m sayou.agent"""

import uvicorn

from sayou.agent.config import get_settings


def main():
    settings = get_settings()
    uvicorn.run(
        "sayou.agent.server:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
