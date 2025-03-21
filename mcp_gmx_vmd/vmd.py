import asyncio
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional, List

from pydantic import BaseModel

class VMDInstance(BaseModel):
    """VMD实例信息"""
    process: Optional[asyncio.subprocess.Process] = None
    pid: Optional[int] = None
    display: Optional[str] = None
    script_pipe: Optional[asyncio.subprocess.Process] = None

class VMDScriptResult(BaseModel):
    """VMD脚本执行结果"""
    stdout: str
    stderr: str
    return_code: int
    script: str

class VMDManager:
    def __init__(self):
        self.instances: Dict[int, VMDInstance] = {}
        
    async def launch_gui(self, structure_file: Optional[str] = None) -> VMDInstance:
        """启动VMD图形界面"""
        # 构建VMD命令
        cmd = ["vmd"]
        if structure_file:
            cmd.append(str(Path(structure_file).resolve()))
            
        # 启动VMD进程
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        instance = VMDInstance(
            process=process,
            pid=process.pid,
            display=os.environ.get("DISPLAY", ":0")
        )
        
        if process.pid:
            self.instances[process.pid] = instance
            
        return instance
    
    async def execute_script(
        self,
        script: str,
        instance_pid: Optional[int] = None,
        structure_file: Optional[str] = None
    ) -> VMDScriptResult:
        """执行VMD TCL脚本"""
        # 如果指定了实例但不存在，返回错误
        if instance_pid and instance_pid not in self.instances:
            return VMDScriptResult(
                stdout="",
                stderr=f"VMD instance with PID {instance_pid} not found",
                return_code=-1,
                script=script
            )
            
        # 创建临时脚本文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tcl', delete=False) as f:
            f.write(script)
            script_path = f.name
            
        try:
            # 构建VMD命令
            cmd = ["vmd", "-dispdev", "text"]
            if structure_file:
                cmd.extend([str(Path(structure_file).resolve())])
            cmd.extend(["-e", script_path])
            
            # 执行脚本
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            return VMDScriptResult(
                stdout=stdout.decode(),
                stderr=stderr.decode(),
                return_code=process.returncode or 0,
                script=script
            )
            
        finally:
            # 清理临时文件
            os.unlink(script_path)
            
    async def close_instance(self, pid: int) -> bool:
        """关闭VMD实例"""
        if pid not in self.instances:
            return False
            
        instance = self.instances[pid]
        if instance.process:
            instance.process.terminate()
            await instance.process.wait()
            
        del self.instances[pid]
        return True
        
    async def close_all(self):
        """关闭所有VMD实例"""
        for pid in list(self.instances.keys()):
            await self.close_instance(pid)
            
# 创建全局VMD管理器实例
vmd_manager = VMDManager() 