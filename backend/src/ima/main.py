"""ASGI entry point."""
import asyncio
from sys import platform

if platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from ima.api.app import create_app

app = create_app()
