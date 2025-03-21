import asyncio
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Dict, Optional, List, Union
import logging
from datetime import datetime
import sys
import random

logger = logging.getLogger(__name__)

class VMDScriptResult:
    """VMD脚本执行结果"""
    def __init__(self, stdout: str = "", stderr: str = "", success: bool = False):
        self.stdout = stdout
        self.stderr = stderr
        self.success = success
        
    def dict(self):
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "success": self.success
        }

class VMDInstance:
    """VMD实例"""
    def __init__(self, pid: int, display: str, process = None):
        self.pid = pid
        self.display = display
        self.process = process

class VMDManager:
    """VMD管理器"""
    
    def __init__(self, vmd_path: str = None):
        self.instances = {}  # pid -> VMDInstance
        # 设置VMD可执行文件路径，如果未提供则尝试使用默认的'vmd'命令
        self.vmd_path = vmd_path or "vmd"
        
    async def launch_gui(self, structure_file: Optional[str] = None) -> Dict:
        """启动VMD图形界面
        
        Args:
            structure_file: 可选的初始加载分子文件
            
        Returns:
            Dict: 包含进程ID和启动状态的字典
        """
        # 在macOS上使用open命令打开VMD.app
        if sys.platform == 'darwin':
            try:
                # 创建启动命令
                cmd = ['open', '-a', 'VMD']
                if structure_file:
                    # 添加文件
                    cmd.extend(['--args', str(structure_file)])
                    
                logger.info(f"在macOS上启动VMD GUI: {' '.join(cmd)}")
                
                # 执行命令
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    logger.error(f"VMD启动失败: {stderr.decode()}")
                    return {
                        "success": False,
                        "error": f"启动VMD GUI失败: {stderr.decode()}"
                    }
                
                # 等待VMD启动
                await asyncio.sleep(3)
                
                # 尝试获取VMD进程ID
                vmds_cmd = await asyncio.create_subprocess_exec(
                    'pgrep', 'VMD',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await vmds_cmd.communicate()
                
                if vmds_cmd.returncode != 0:
                    logger.warning("无法获取VMD进程ID，但GUI可能已经启动")
                    # 生成一个虚拟PID，仅用于标识
                    pid = random.randint(10000, 99999)  
                else:
                    # 获取最后一个VMD进程ID
                    pids = stdout.decode().strip().split('\n')
                    if pids:
                        pid = int(pids[-1])
                    else:
                        # 生成一个虚拟PID
                        pid = random.randint(10000, 99999)
                        logger.warning(f"无法获取真实VMD进程ID，使用虚拟ID: {pid}")
                
                # 创建实例
                display = os.environ.get("DISPLAY", ":0")
                instance = VMDInstance(pid, display, None)
                self.instances[pid] = instance
                
                logger.info(f"成功启动VMD GUI: pid={pid} (可能是虚拟ID)")
                
                return {
                    "success": True,
                    "pid": pid,
                    "display": display,
                    "message": "VMD图形界面已成功启动",
                    "note": "在macOS上，进程ID可能是虚拟的"
                }
                
            except Exception as e:
                logger.error(f"启动VMD失败: {str(e)}")
                return {
                    "success": False,
                    "error": str(e),
                    "message": "启动VMD图形界面失败"
                }
        else:
            # 对于非macOS系统，使用原有方法
            cmd = [self.vmd_path]
            if structure_file:
                cmd.append(str(structure_file))
                
            try:
                # 设置显示环境变量
                env = os.environ.copy()
                
                logger.info(f"启动VMD命令: {' '.join(cmd)}")
                
                # 在非终端模式下启动VMD
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env
                )
                
                # 获取进程PID
                pid = process.pid
                display = env.get("DISPLAY", ":0")
                
                # 创建实例
                instance = VMDInstance(pid, display, process)
                self.instances[pid] = instance
                
                # 等待片刻确保VMD启动
                await asyncio.sleep(1)
                
                logger.info(f"启动VMD图形界面: pid={pid}, display={display}")
                
                # 检查进程是否仍在运行
                if process.returncode is not None:
                    logger.error(f"VMD进程已退出，退出码: {process.returncode}")
                    stderr_data = await process.stderr.read()
                    return {
                        "success": False,
                        "pid": pid,
                        "error": stderr_data.decode()
                    }
                
                return {
                    "success": True,
                    "pid": pid,
                    "display": display,
                    "message": "VMD图形界面已成功启动"
                }
                
            except Exception as e:
                logger.error(f"启动VMD失败: {str(e)}")
                return {
                    "success": False,
                    "error": str(e),
                    "message": "启动VMD图形界面失败"
                }
            
    async def execute_script(
        self, 
        script: str, 
        instance_pid: Optional[int] = None,
        structure_file: Optional[str] = None,
        generate_image: bool = False,
        image_file: Optional[str] = None,
        timeout: int = 60
    ) -> Dict:
        """执行VMD TCL脚本
        
        Args:
            script: TCL脚本内容
            instance_pid: 可选的VMD进程ID（若不提供则启动新实例）
            structure_file: 可选的加载结构文件
            generate_image: 是否生成图像
            image_file: 图像文件名（如果generate_image为True）
            timeout: 脚本执行超时时间（秒）
            
        Returns:
            Dict: 脚本执行结果
        """
        # 处理图像生成逻辑
        if generate_image and not image_file:
            image_file = f"vmd_render_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            
        if generate_image:
            # 添加图像渲染命令
            image_path = Path(image_file).absolute()
            render_commands = f"""
            display update
            display update ui
            render TachyonInternal {image_path} %s
            puts "IMAGE_SAVED:{image_path}"
            """
            script = script + render_commands
            
        # 创建临时脚本文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tcl', delete=False) as f:
            script_path = f.name
            f.write(script)
            
            # 仅在新实例模式下才添加退出命令
            if instance_pid is None:
                f.write("\nexit")  # 确保VMD执行完脚本后退出
        
        result = {}
        
        try:
            # 特别处理macOS上的VMD
            if sys.platform == 'darwin' and instance_pid is not None:
                logger.info(f"在macOS上向现有VMD实例发送脚本: {instance_pid}")
                
                # 在macOS上，使用临时文件和特殊的执行方式
                # 创建一个Apple Script命令，让VMD执行TCL脚本
                applescript_cmd = f'''
                tell application "VMD"
                    activate
                    delay 1
                    do shell script "echo 'source {script_path}' | /Applications/VMD.app/Contents/vmd/vmd_MACOSXARM64 -dispdev text -eofexit"
                end tell
                '''
                
                # 创建临时Apple Script文件
                with tempfile.NamedTemporaryFile(mode='w', suffix='.scpt', delete=False) as f:
                    applescript_path = f.name
                    f.write(applescript_cmd)
                
                try:
                    # 执行Apple Script
                    process = await asyncio.create_subprocess_exec(
                        'osascript', applescript_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    
                    try:
                        stdout, stderr = await asyncio.wait_for(
                            process.communicate(), 
                            timeout=timeout
                        )
                        
                        stdout_str = stdout.decode()
                        stderr_str = stderr.decode()
                        
                        # 提取图像路径（如果有）
                        image_path = None
                        for line in stdout_str.split('\n'):
                            if line.startswith("IMAGE_SAVED:"):
                                image_path = line.split(':')[1].strip()
                        
                        result = {
                            "success": process.returncode == 0,
                            "stdout": stdout_str,
                            "stderr": stderr_str,
                            "pid": instance_pid,
                            "image_path": image_path if generate_image else None
                        }
                        
                    except asyncio.TimeoutError:
                        result = {
                            "success": False,
                            "error": f"脚本执行超时（{timeout}秒）",
                            "pid": instance_pid
                        }
                finally:
                    # 清理临时Apple Script文件
                    try:
                        os.unlink(applescript_path)
                    except:
                        pass
                    
            elif instance_pid is not None and instance_pid in self.instances:
                # 向现有实例发送脚本
                instance = self.instances[instance_pid]
                
                # 使用VMD的-send选项向现有实例发送命令
                send_cmd = [self.vmd_path, "-dispdev", "text", "-e", script_path, "-send", f"source {script_path}"]
                
                process = await asyncio.create_subprocess_exec(
                    *send_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), 
                        timeout=timeout
                    )
                    
                    stdout_str = stdout.decode()
                    stderr_str = stderr.decode()
                    
                    # 提取图像路径（如果有）
                    image_path = None
                    for line in stdout_str.split('\n'):
                        if line.startswith("IMAGE_SAVED:"):
                            image_path = line.split(':')[1].strip()
                    
                    result = {
                        "success": process.returncode == 0,
                        "stdout": stdout_str,
                        "stderr": stderr_str,
                        "pid": instance_pid,
                        "image_path": image_path if generate_image else None
                    }
                    
                except asyncio.TimeoutError:
                    result = {
                        "success": False,
                        "error": f"脚本执行超时（{timeout}秒）",
                        "pid": instance_pid
                    }
            else:
                # 启动新实例执行脚本
                cmd = [self.vmd_path, "-dispdev", "text"]
                
                if structure_file:
                    cmd.append(structure_file)
                cmd.extend(["-e", script_path])
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), 
                        timeout=timeout
                    )
                    
                    stdout_str = stdout.decode()
                    stderr_str = stderr.decode()
                    
                    # 提取图像路径（如果有）
                    image_path = None
                    for line in stdout_str.split('\n'):
                        if line.startswith("IMAGE_SAVED:"):
                            image_path = line.split(':')[1].strip()
                    
                    result = {
                        "success": process.returncode == 0,
                        "stdout": stdout_str,
                        "stderr": stderr_str,
                        "image_path": image_path if generate_image else None
                    }
                    
                except asyncio.TimeoutError:
                    result = {
                        "success": False,
                        "error": f"脚本执行超时（{timeout}秒）"
                    }
            
            return result
            
        except Exception as e:
            logger.error(f"执行VMD脚本失败: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            # 删除临时脚本文件
            try:
                os.unlink(script_path)
            except:
                pass
            
    async def close_instance(self, pid: int) -> bool:
        """关闭VMD实例"""
        if pid not in self.instances:
            return False
            
        instance = self.instances[pid]
        if not instance.process:
            return False
            
        try:
            instance.process.terminate()
            await asyncio.sleep(1)
            
            if instance.process.returncode is None:
                # 强制终止
                instance.process.kill()
                
            del self.instances[pid]
            return True
            
        except Exception as e:
            logger.error(f"关闭VMD实例失败: {str(e)}")
            return False
            
    def get_instance(self, pid: int) -> Optional[VMDInstance]:
        """获取VMD实例"""
        return self.instances.get(pid)
        
    def list_instances(self) -> List[Dict]:
        """列出所有VMD实例"""
        return [
            {
                "pid": pid,
                "display": instance.display,
                "status": "running" if instance.process and instance.process.returncode is None else "stopped"
            }
            for pid, instance in self.instances.items()
        ] 