import asyncio
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Union
import logging
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class Context:
    """上下文对象，用于传递信息"""
    def __init__(self, working_dir: Optional[Union[str, Path]] = None, gmx_path: Optional[str] = None):
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.gmx_path = gmx_path or "gmx"  # 默认使用gmx命令
        self.log = []

class GromacsCmdResult(BaseModel):
    """GROMACS命令执行结果"""
    stdout: str
    stderr: str
    return_code: int
    command: str
    success: bool

async def run_gromacs_command(ctx: Context, cmd: str, args: List[str], input_data: Optional[str] = None) -> GromacsCmdResult:
    """
    执行GROMACS命令
    
    Args:
        ctx: 上下文，包含工作目录和gmx路径
        cmd: GROMACS子命令名称
        args: 命令参数列表
        input_data: 提供给命令的标准输入数据（可选）
        
    Returns:
        GromacsCmdResult: 包含命令执行的所有输出信息
    """
    # 确定命令格式
    # GROMACS 5+ 版本使用 gmx <command> 格式
    # 旧版本直接使用命令名，如 grompp, mdrun 等
    gmx_path = ctx.gmx_path  # 通常为 "gmx"
    
    # 检查 ctx.gmx_path 是否为 "gmx"，如果是，使用新版GROMACS命令格式
    if gmx_path == "gmx":
        full_cmd = [gmx_path, cmd] + args
    else:
        # 旧版GROMACS，直接使用命令
        full_cmd = [cmd] + args
    
    try:
        cwd = ctx.working_dir if hasattr(ctx, "working_dir") else None
        
        logger.info(f"执行GROMACS命令: {' '.join(full_cmd)} (在目录: {cwd})")
        
        if input_data is not None:
            # 使用传入的输入数据
            logger.debug(f"提供标准输入: {input_data}")
            process = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            stdout, stderr = await process.communicate(input=input_data.encode())
        else:
            # 不需要输入数据
            process = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            stdout, stderr = await process.communicate()
        
        # 解码输出
        stdout_str = stdout.decode()
        stderr_str = stderr.decode()
        
        # 记录命令执行结果
        if hasattr(ctx, "log"):
            ctx.log.append({
                "command": " ".join(full_cmd),
                "return_code": process.returncode,
                "stdout": stdout_str,
                "stderr": stderr_str
            })
        
        # 记录输出以便调试
        logger.debug(f"GROMACS命令输出: {stdout_str}")
        if stderr_str:
            logger.debug(f"GROMACS命令错误: {stderr_str}")
        
        return GromacsCmdResult(
            stdout=stdout_str,
            stderr=stderr_str,
            return_code=process.returncode,
            command=" ".join(full_cmd),
            success=(process.returncode == 0)
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(f"执行GROMACS命令失败: {error_msg}")
        return GromacsCmdResult(
            stdout="",
            stderr=error_msg,
            return_code=-1,
            command=" ".join(full_cmd),
            success=False
        ) 