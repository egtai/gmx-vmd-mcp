import asyncio
import signal
import sys
from typing import Optional

import mcp.server.stdio
from mcp.server.models import InitializationOptions
from mcp.server.lowlevel import NotificationOptions

from .service import mcp
from .vmd import vmd_manager

async def cleanup(sig: Optional[signal.Signals] = None):
    """清理资源"""
    await vmd_manager.close_all()
    if sig:
        sys.exit(0)

async def main_async():
    """异步主函数"""
    # 设置信号处理
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_event_loop().add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(cleanup(s))
        )
    
    try:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await mcp.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="GROMACS-VMD MCP Service",
                    server_version="0.1.0",
                    capabilities=mcp.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={}
                    )
                )
            )
    finally:
        await cleanup()

def main():
    """命令行入口点"""
    asyncio.run(main_async()) 