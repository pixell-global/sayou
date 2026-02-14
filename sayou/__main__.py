import asyncio

from sayou.server import create_server


async def async_main():
    server, ws = create_server()
    try:
        await server.run_stdio_async()
    finally:
        await ws.close()


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
