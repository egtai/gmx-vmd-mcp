from mcp.server.fastmcp import FastMCP
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union
import asyncio
import sys
import tempfile
import json

# 创建logger
logger = logging.getLogger(__name__)

# 全局工作流目录映射
workflow_dir_mapping = {}

# 创建MCP服务实例
mcp = FastMCP("GROMACS-VMD Service")

# 定义依赖
dependencies = []

# 导入功能性模块（使用绝对导入）
from mcp_gmx_vmd.service import MCPService, SimulationParams
from mcp_gmx_vmd.gromacs import Context, run_gromacs_command
from mcp_gmx_vmd.models import (
    AnalysisParams, AnalysisResult, AnalysisType,
    CompleteSimulationParams, SimulationConfig,
    SimulationStatus, SimulationStep
)
from mcp_gmx_vmd.workflow_manager import WorkflowMetadata

# 创建服务实例
service = MCPService(Path(os.getcwd()))

# 加载工作流目录映射
try:
    mapping_file = Path(os.getcwd()) / ".mcp" / "workflow_dir_mapping.json"
    if mapping_file.exists():
        with open(mapping_file, "r") as f:
            workflow_dir_mapping.update(json.load(f))
        logger.info(f"已加载工作流目录映射，共{len(workflow_dir_mapping)}个工作流")
except Exception as e:
    logger.error(f"加载工作流目录映射时出错: {e}")

# 添加权限检查和修复函数
def ensure_workflow_directory_permissions(directory_path: Path) -> None:
    """确保工作流目录及其子目录具有正确的权限"""
    if not directory_path.exists():
        logger.warning(f"工作流目录不存在，无法设置权限: {directory_path}")
        return
        
    try:
        import stat
        
        # 设置主目录权限
        os.chmod(directory_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        
        # 设置子目录权限
        for subdir in ["em", "nvt", "npt", "md"]:
            subdir_path = directory_path / subdir
            if subdir_path.exists():
                os.chmod(subdir_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
            else:
                # 创建不存在的子目录并设置权限
                subdir_path.mkdir(parents=True, exist_ok=True)
                os.chmod(subdir_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
                
        logger.debug(f"已确保工作流目录权限: {directory_path}")
    except Exception as e:
        logger.warning(f"设置目录权限失败: {e}")

# 自定义工作流目录获取函数
def get_custom_workflow_directory(workflow_id: str) -> Optional[Path]:
    """优先从目录映射中获取工作流目录，如果没有则使用默认路径"""
    global workflow_dir_mapping
    
    # 优先从映射中获取
    if workflow_id in workflow_dir_mapping:
        custom_dir = Path(workflow_dir_mapping[workflow_id])
        if custom_dir.exists():
            logger.info(f"从映射中找到工作流 {workflow_id} 的自定义目录: {custom_dir}")
            # 确保目录权限正确
            ensure_workflow_directory_permissions(custom_dir)
            return custom_dir
    
    # 退回到默认方法
    workflow_dir = service.workflow_manager.get_workflow_directory(workflow_id)
    if workflow_dir:
        # 确保默认目录的权限也是正确的
        ensure_workflow_directory_permissions(workflow_dir)
    return workflow_dir

# 从配置文件加载配置
config_file = Path(os.getcwd()) / "config.json"
if config_file.exists():
    try:
        with open(config_file, "r") as f:
            config = json.load(f)
        vmd_config = config.get("vmd", {})
        gmx_config = config.get("gmx", {})
        logger.info(f"从配置文件加载配置: {config_file}")
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        # 使用默认配置
        vmd_config = {
            "vmd_path": "/Applications/VMD.app/Contents/vmd/vmd_MACOSXARM64",
            "structure_search_paths": [
                "/Users/tanqiong/01_myProject/30.vmd-mcp/00.mcp-test/01.mcp-vmd-gmx",
                "/Users/tanqiong/01_myProject/30.vmd-mcp/00.mcp-test/04.mcp-gmx-vmd_v4/mcp-gmx-vmd"
            ]
        }
        gmx_config = {
            "gmx_path": "gmx",
        }
else:
    logger.warning(f"配置文件不存在: {config_file}，使用默认配置")
    # 使用默认配置
    vmd_config = {
        "vmd_path": "/Applications/VMD.app/Contents/vmd/vmd_MACOSXARM64",
        "structure_search_paths": [
            "/Users/tanqiong/01_myProject/30.vmd-mcp/00.mcp-test/01.mcp-vmd-gmx",
            "/Users/tanqiong/01_myProject/30.vmd-mcp/00.mcp-test/04.mcp-gmx-vmd_v4/mcp-gmx-vmd"
        ]
    }
    gmx_config = {
        "gmx_path": "gmx",
    }

# 更新服务实例使用配置
service.vmd_manager.vmd_path = vmd_config["vmd_path"]
# 添加结构文件搜索路径
for path in vmd_config["structure_search_paths"]:
    service.add_structure_search_path(path)

#====================
# 基本信息
#====================

@mcp.resource("gmx-vmd://info")
async def get_info() -> dict:
    """获取服务信息"""
    return {
        "name": "MCP GROMACS-VMD Service",
        "version": "0.1.0",
        "description": "用于分子动力学模拟和可视化的MCP服务"
    }

@mcp.resource("gmx-vmd://help")
async def get_help() -> str:
    """获取帮助信息"""
    return service.get_workflow_help()

#====================
# 工作流程管理
#====================

@mcp.resource("gmx-vmd://workflows/create?name={name}&description={description}&params={params}")
async def create_workflow(name: str, description: str = "", params: Optional[Dict] = None) -> Dict:
    """创建新的工作流程"""
    workflow_params = CompleteSimulationParams(**params) if params else None
    workflow_id = service.create_workflow(name, description, workflow_params)
    return {"workflow_id": workflow_id, "success": True}

@mcp.resource("gmx-vmd://workflows/list")
async def list_workflows() -> List[Dict]:
    """列出所有工作流程"""
    workflows = service.list_workflows()
    return [wf.to_dict() for wf in workflows]

@mcp.resource("gmx-vmd://workflows/get?workflow_id={workflow_id}")
async def get_workflow(workflow_id: str) -> Dict:
    """获取工作流程详情"""
    workflow = service.get_workflow(workflow_id)
    if workflow:
        return workflow.to_dict()
    return {"error": "工作流程不存在", "workflow_id": workflow_id}

@mcp.resource("gmx-vmd://workflows/update?workflow_id={workflow_id}&name={name}&description={description}&status={status}&params={params}")
async def update_workflow(
    workflow_id: str, 
    name: Optional[str] = None, 
    description: Optional[str] = None,
    status: Optional[Dict] = None,
    params: Optional[Dict] = None
) -> Dict:
    """更新工作流程"""
    status_obj = SimulationStatus(**status) if status else None
    params_obj = CompleteSimulationParams(**params) if params else None
    success = service.update_workflow(workflow_id, name, description, status_obj, params_obj)
    return {"success": success, "workflow_id": workflow_id}

@mcp.resource("gmx-vmd://workflows/delete?workflow_id={workflow_id}")
async def delete_workflow(workflow_id: str) -> Dict:
    """删除工作流程"""
    success = service.delete_workflow(workflow_id)
    return {"success": success, "workflow_id": workflow_id}

@mcp.resource("gmx-vmd://workflows/status?workflow_id={workflow_id}")
async def get_workflow_status(workflow_id: str) -> Dict:
    """获取工作流程状态"""
    status = service.get_workflow_status(workflow_id)
    if status:
        return status.dict()
    return {"error": "无法获取工作流程状态", "workflow_id": workflow_id}

@mcp.resource("gmx-vmd://workflows/logs?workflow_id={workflow_id}")
async def get_workflow_logs(workflow_id: str) -> Dict:
    """获取工作流程日志"""
    logs = service.get_workflow_logs(workflow_id)
    return {"logs": logs, "workflow_id": workflow_id}

@mcp.resource("gmx-vmd://workflows/checkpoints?workflow_id={workflow_id}")
async def get_workflow_checkpoints(workflow_id: str) -> Dict:
    """获取工作流程检查点"""
    checkpoints = service.get_workflow_checkpoints(workflow_id)
    result = {}
    for step, files in checkpoints.items():
        result[step.value] = files
    return {"checkpoints": result, "workflow_id": workflow_id}

@mcp.resource("gmx-vmd://workflows/export?workflow_id={workflow_id}&output_file={output_file}")
async def export_workflow(workflow_id: str, output_file: str) -> Dict:
    """导出工作流程"""
    success = service.export_workflow(workflow_id, output_file)
    return {"success": success, "workflow_id": workflow_id, "output_file": output_file}

@mcp.resource("gmx-vmd://workflows/import?input_file={input_file}")
async def import_workflow(input_file: str) -> Dict:
    """导入工作流程"""
    workflow_id = service.import_workflow(input_file)
    if workflow_id:
        return {"success": True, "workflow_id": workflow_id}
    return {"success": False, "error": "导入工作流程失败"}

#====================
# 模拟参数管理
#====================

@mcp.resource("gmx-vmd://parameters/validate?params={params}")
async def validate_parameters(params: Dict) -> Dict:
    """验证模拟参数"""
    params_obj = CompleteSimulationParams(**params)
    warnings = service.validate_parameters(params_obj)
    return {"warnings": warnings, "valid": not any(warnings.values())}

@mcp.resource("gmx-vmd://parameters/optimize?params={params}")
async def optimize_parameters(params: Dict) -> Dict:
    """优化模拟参数"""
    params_obj = CompleteSimulationParams(**params)
    optimized_params, warnings = service.optimize_parameters(params_obj)
    return {
        "optimized_params": optimized_params.dict(),
        "warnings": warnings,
        "success": True
    }

#====================
# 轨迹分析和可视化
#====================

@mcp.resource("gmx-vmd://analysis/trajectory?workflow_id={workflow_id}&params={params}")
async def analyze_trajectory(workflow_id: str, params: Dict) -> Dict:
    """分析轨迹"""
    # 记录请求信息
    logger.info(f"收到轨迹分析请求：workflow_id={workflow_id}, params={params}")
    
    # 验证参数
    errors = []
    
    # 检查分析类型
    if "analysis_type" not in params:
        errors.append("缺少分析类型(analysis_type)参数")
    elif params["analysis_type"].upper() == "RMSD" and params["analysis_type"] != "rmsd":
        errors.append("分析类型错误：RMSD 需要以小写形式指定为 rmsd")
    
    # 检查结构文件
    if "structure_file" not in params or not params["structure_file"]:
        errors.append("缺失字段：需要明确提供参考的 structure_file 参数")
    
    # 检查轨迹文件
    if "trajectory_file" not in params or not params["trajectory_file"]:
        errors.append("缺失字段：需要提供 trajectory_file 参数")
    
    # 如果有错误，直接返回错误信息
    if errors:
        error_msg = "参数验证失败: " + "; ".join(errors)
        logger.error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "workflow_id": workflow_id
        }
    
    # 确保所有参数都是正确的小写形式
    if "analysis_type" in params:
        params["analysis_type"] = params["analysis_type"].lower()
    
    try:
        # 获取工作流目录
        workflow_dir = get_custom_workflow_directory(workflow_id)
        if not workflow_dir:
            error_msg = f"无法获取工作流程目录: {workflow_id}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "workflow_id": workflow_id
            }
        
        # 检查文件路径
        if "trajectory_file" in params and not os.path.isabs(params["trajectory_file"]):
            traj_path = os.path.join(workflow_dir, params["trajectory_file"])
            if not os.path.exists(traj_path):
                error_msg = f"轨迹文件不存在: {traj_path}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "workflow_id": workflow_id
                }
        
        if "structure_file" in params and not os.path.isabs(params["structure_file"]):
            struct_path = os.path.join(workflow_dir, params["structure_file"])
            if not os.path.exists(struct_path):
                error_msg = f"结构文件不存在: {struct_path}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "workflow_id": workflow_id
                }
        
        logger.info(f"参数验证通过，准备创建AnalysisParams对象")
        
        # 创建分析参数对象
        try:
            analysis_params = AnalysisParams(**params)
            logger.info(f"成功创建AnalysisParams对象: {analysis_params}")
        except Exception as e:
            error_msg = f"创建分析参数对象失败: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False, 
                "error": error_msg,
                "workflow_id": workflow_id
            }
        
        # 执行分析，传递自定义工作流目录
        logger.info(f"开始调用service.analyze_trajectory")
        result = await service.analyze_trajectory(workflow_id, analysis_params, workflow_dir)
        
        if result:
            logger.info(f"分析成功完成，返回结果")
            return {
                "success": True,
                "result": result.dict(),
                "workflow_id": workflow_id
            }
            
        logger.error("轨迹分析失败，service.analyze_trajectory返回None")
        return {
            "success": False, 
            "error": "轨迹分析失败，请检查参数和日志", 
            "workflow_id": workflow_id
        }
    except Exception as e:
        import traceback
        error_msg = str(e)
        tb = traceback.format_exc()
        logger.error(f"分析轨迹时发生错误: {error_msg}")
        logger.error(f"异常堆栈: {tb}")
        
        return {
            "success": False,
            "error": f"分析轨迹时发生错误: {error_msg}",
            "traceback": tb,
            "workflow_id": workflow_id
        }

@mcp.resource("gmx-vmd://visualization/apply-template?workflow_id={workflow_id}&template_name={template_name}&params={params}")
async def apply_vmd_template(workflow_id: str, template_name: str, params: Optional[Dict] = None) -> Dict:
    """应用VMD模板"""
    # 获取自定义工作流目录
    workflow_dir = get_custom_workflow_directory(workflow_id)
    if not workflow_dir:
        return {
            "success": False,
            "error": f"无法获取工作流目录: {workflow_id}",
            "workflow_id": workflow_id,
            "template": template_name
        }
    
    # 调用服务方法，传递自定义工作流目录
    success = service.apply_vmd_template(workflow_id, template_name, params, workflow_dir)
    return {
        "success": success,
        "workflow_id": workflow_id,
        "template": template_name
    }

@mcp.resource("gmx-vmd://visualization/templates")
async def get_available_templates() -> Dict:
    """获取可用的VMD模板"""
    templates = service.get_available_templates()
    return {"templates": templates}

#====================
# GROMACS命令执行
#====================

@mcp.resource("gmx-vmd://gromacs/execute?workflow_id={workflow_id}&command={command}&args={args}&input_data={input_data}")
async def execute_gromacs_command(workflow_id: str, command: str, args: List[str] = None, input_data: Optional[str] = None) -> Dict:
    """执行GROMACS命令"""
    workflow_dir = get_custom_workflow_directory(workflow_id)
    if not workflow_dir:
        return {"success": False, "error": "工作流程目录不存在", "workflow_id": workflow_id}
    
    # 检查工作目录是否存在
    if not os.path.isdir(workflow_dir):
        return {"success": False, "error": f"工作流程目录不存在: {workflow_dir}", "workflow_id": workflow_id}
    
    # 查找命令参数中的文件路径，并转换为绝对路径
    if args:
        for i, arg in enumerate(args):
            # 处理以"-"开头的选项后面的参数
            if arg.startswith("-") and i + 1 < len(args):
                next_arg = args[i + 1]
                if not next_arg.startswith("-"):
                    # 判断这个选项是否是文件路径参数
                    file_options = ['-c', '-s', '-f', '-r', '-t', '-n', '-o', '-e', '-g', '-cpi']
                    if arg in file_options:
                        # 将文件路径转换为绝对路径
                        if not os.path.isabs(next_arg):
                            # 如果路径中包含斜杠，直接使用；否则添加目录前缀
                            if '/' in next_arg:
                                args[i + 1] = str(workflow_dir / next_arg)
                            else:
                                # 特殊处理不含目录分隔符的文件名
                                # 对于某些选项，添加特定的子目录
                                if arg in ['-t', '-cpi'] and next_arg.startswith('nvt'):
                                    # 对于checkpoint文件，如nvt.cpt应该在nvt/目录下
                                    args[i + 1] = str(workflow_dir / "nvt" / next_arg)
                                elif arg in ['-t', '-cpi'] and next_arg.startswith('npt'):
                                    # 对于checkpoint文件，如npt.cpt应该在npt/目录下
                                    args[i + 1] = str(workflow_dir / "npt" / next_arg)
                                else:
                                    # 其他文件默认在工作目录下
                                    args[i + 1] = str(workflow_dir / next_arg)
            
            # 处理 -deffnm 选项，该选项后面跟着的是没有扩展名的文件前缀
            elif arg == "-deffnm" and i + 1 < len(args):
                next_arg = args[i + 1]
                if not os.path.isabs(next_arg):
                    # 如果路径中包含斜杠，直接使用；否则添加工作目录前缀
                    args[i + 1] = str(workflow_dir / next_arg)
    
    # 输出实际使用的参数（调试用）
    logger.debug(f"处理后的命令参数: {args}")
    
    # 验证输入文件是否存在
    if args:
        missing_files = []
        for i, arg in enumerate(args):
            if arg in ['-c', '-s', '-f', '-r', '-t', '-n'] and i + 1 < len(args):
                file_path = args[i + 1]
                if not os.path.isabs(file_path):
                    file_path = os.path.join(workflow_dir, file_path)
                if not os.path.exists(file_path):
                    missing_files.append(f"文件 '{args[i + 1]}' 不存在")
        
        if missing_files:
            return {
                "success": False,
                "error": f"输入文件不存在: {', '.join(missing_files)}",
                "workflow_id": workflow_id,
                "command": command
            }
    
    # 特殊处理 GROMACS 命令格式
    # GROMACS 5+ 使用 "gmx <command>" 格式，而旧版直接使用命令名
    gmx_cmd = gmx_config["gmx_path"]  # 通常为 "gmx"
    actual_command = command
    actual_args = args or []
    
    # 检查命令是否已包含 gmx 前缀
    if command.startswith("gmx "):
        # 命令已包含前缀，分离出实际命令
        parts = command.split(" ", 1)
        actual_command = parts[1] if len(parts) > 1 else ""
    elif not command.startswith("gmx") and gmx_cmd == "gmx":
        # 如果命令不包含前缀，且配置为使用前缀，则不做特殊处理
        # 这种情况会由 run_gromacs_command 正确处理
        pass
    
    # 确保输出目录存在
    output_path = None
    if args:
        for i, arg in enumerate(args):
            if arg == '-o' and i + 1 < len(args):
                output_path = args[i + 1]
                if not os.path.isabs(output_path):
                    output_path = os.path.join(workflow_dir, output_path)
                output_dir = os.path.dirname(output_path)
                os.makedirs(output_dir, exist_ok=True)
    
    # 设置执行上下文并执行命令
    ctx = Context(working_dir=workflow_dir, gmx_path=gmx_config["gmx_path"])
    
    # 记录实际执行的命令（用于调试）
    logger.info(f"执行GROMACS命令: {gmx_cmd} {actual_command} {' '.join(str(a) for a in actual_args)}")
    
    result = await run_gromacs_command(ctx, actual_command, actual_args, input_data)
    
    # 构建完整命令字符串，用于显示
    full_command = f"{gmx_cmd} {actual_command} {' '.join(str(a) for a in actual_args)}"
    
    return {
        "success": result.success,
        "output": result.stdout,  # 返回标准输出
        "error": result.stderr,   # 返回错误输出
        "return_code": result.return_code,
        "workflow_id": workflow_id,
        "command": command,
        "full_command": full_command,
        "debug_info": {
            "working_dir": str(workflow_dir),
            "command_executed": f"{gmx_cmd} {actual_command}",
            "args": [str(a) for a in actual_args]
        }
    }

#====================
# MCP工具定义
#====================

# 基本信息工具
@mcp.tool("获取服务信息")
async def get_info_tool() -> Dict:
    """获取GMX-VMD服务的基本信息，包括名称、版本和描述"""
    return await get_info()

@mcp.tool("获取帮助文档")
async def get_help_tool() -> str:
    """获取GMX-VMD服务的使用帮助和工作流程指南"""
    return await get_help()

# 工作流程管理工具
@mcp.tool("创建工作流程")
async def create_workflow_tool(name: str, description: str = "", params: Optional[Dict] = None, workspace_dir: Optional[str] = None) -> Dict:
    """创建一个新的分子动力学模拟工作流程
    
    Args:
        name: 工作流程名称
        description: 工作流程描述
        params: 模拟参数（可选）
        workspace_dir: 工作流的工作目录（可选，默认为MCP服务的工作目录）
    """
    global workflow_dir_mapping
    
    if workspace_dir:
        # 如果指定了workspace_dir，创建一个临时的WorkflowManager
        from mcp_gmx_vmd.workflow_manager import WorkflowManager
        from mcp_gmx_vmd.models import CompleteSimulationParams
        
        # 确保目录存在并设置正确的权限
        workspace_path = Path(workspace_dir)
        workspace_path.mkdir(parents=True, exist_ok=True)
        
        # 设置目录权限为777，确保所有用户都有完全访问权限
        try:
            import stat
            os.chmod(workspace_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)  # 等同于 chmod 777
            logger.info(f"已设置目录权限: {workspace_path}")
        except Exception as e:
            logger.warning(f"设置目录权限失败: {e}")
        
        # 创建临时工作流管理器
        temp_manager = WorkflowManager(workspace_path)
        
        # 解析参数（如果有）
        workflow_params = CompleteSimulationParams(**params) if params else None
        
        # 创建工作流
        workflow_id = temp_manager.create_workflow(name, description, workflow_params)
        
        # 获取工作流目录并设置权限
        workflow_dir = workspace_path / workflow_id
        if workflow_dir.exists():
            try:
                import stat
                os.chmod(workflow_dir, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)  # 等同于 chmod 777
                logger.info(f"已设置工作流目录权限: {workflow_dir}")
                
                # 确保子目录也有正确的权限
                for subdir in ["em", "nvt", "npt", "md"]:
                    subdir_path = workflow_dir / subdir
                    subdir_path.mkdir(parents=True, exist_ok=True)
                    os.chmod(subdir_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
            except Exception as e:
                logger.warning(f"设置工作流目录权限失败: {e}")
        
        # 将此工作流元数据复制到主服务的工作流管理器中
        metadata = temp_manager.get_workflow(workflow_id)
        if metadata:
            service.workflow_manager._save_metadata(metadata)
            
        # 记录工作流目录映射
        workflow_dir_mapping[workflow_id] = str(workflow_dir)
        logger.info(f"已记录工作流 {workflow_id} 的自定义目录: {workflow_dir_mapping[workflow_id]}")
        
        # 保存工作流目录映射到文件，确保服务重启后仍能找到
        try:
            mapping_file = Path(os.getcwd()) / ".mcp" / "workflow_dir_mapping.json"
            mapping_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 读取现有映射（如果存在）
            existing_mapping = {}
            if mapping_file.exists():
                with open(mapping_file, "r") as f:
                    existing_mapping = json.load(f)
            
            # 更新映射
            existing_mapping[workflow_id] = str(workflow_dir)
            
            # 保存更新后的映射
            with open(mapping_file, "w") as f:
                json.dump(existing_mapping, f, indent=4)
                
            logger.info(f"工作流目录映射已保存到: {mapping_file}")
        except Exception as e:
            logger.error(f"保存工作流目录映射时出错: {e}")
        
        return {"workflow_id": workflow_id, "success": True, "workspace_dir": str(workflow_dir)}
    else:
        # 使用默认工作流管理器
        return await create_workflow(name, description, params)

@mcp.tool("列出所有工作流程")
async def list_workflows_tool() -> List[Dict]:
    """获取所有已创建的工作流程列表"""
    return await list_workflows()

@mcp.tool("获取工作流程详情")
async def get_workflow_tool(workflow_id: str) -> Dict:
    """获取指定工作流程的详细信息
    
    Args:
        workflow_id: 工作流程ID
    """
    return await get_workflow(workflow_id)

@mcp.tool("更新工作流程")
async def update_workflow_tool(workflow_id: str, name: Optional[str] = None, 
                             description: Optional[str] = None,
                             status: Optional[Dict] = None,
                             params: Optional[Dict] = None) -> Dict:
    """更新现有工作流程的信息
    
    Args:
        workflow_id: 工作流程ID
        name: 新的工作流程名称（可选）
        description: 新的工作流程描述（可选）
        status: 工作流程状态信息（可选）
        params: 模拟参数（可选）
    """
    return await update_workflow(workflow_id, name, description, status, params)

@mcp.tool("删除工作流程")
async def delete_workflow_tool(workflow_id: str) -> Dict:
    """删除指定的工作流程
    
    Args:
        workflow_id: 要删除的工作流程ID
    """
    return await delete_workflow(workflow_id)

@mcp.tool("获取工作流程状态")
async def get_workflow_status_tool(workflow_id: str) -> Dict:
    """获取指定工作流程的当前运行状态
    
    Args:
        workflow_id: 工作流程ID
    """
    return await get_workflow_status(workflow_id)

@mcp.tool("获取工作流程日志")
async def get_workflow_logs_tool(workflow_id: str) -> Dict:
    """获取指定工作流程的运行日志
    
    Args:
        workflow_id: 工作流程ID
    """
    return await get_workflow_logs(workflow_id)

@mcp.tool("获取工作流程检查点")
async def get_workflow_checkpoints_tool(workflow_id: str) -> Dict:
    """获取指定工作流程的所有检查点
    
    Args:
        workflow_id: 工作流程ID
    """
    return await get_workflow_checkpoints(workflow_id)

@mcp.tool("导出工作流程")
async def export_workflow_tool(workflow_id: str, output_file: str) -> Dict:
    """将指定工作流程导出到文件
    
    Args:
        workflow_id: 工作流程ID
        output_file: 导出文件路径
    """
    return await export_workflow(workflow_id, output_file)

@mcp.tool("导入工作流程")
async def import_workflow_tool(input_file: str) -> Dict:
    """从文件导入工作流程
    
    Args:
        input_file: 导入文件路径
    """
    return await import_workflow(input_file)

# 参数管理工具
@mcp.tool("验证模拟参数")
async def validate_parameters_tool(params: Dict) -> Dict:
    """验证分子动力学模拟参数的有效性
    
    Args:
        params: 模拟参数
    """
    return await validate_parameters(params)

@mcp.tool("优化模拟参数")
async def optimize_parameters_tool(params: Dict) -> Dict:
    """优化分子动力学模拟参数，提高模拟效率和稳定性
    
    Args:
        params: 原始模拟参数
    """
    return await optimize_parameters(params)

# 轨迹分析工具
@mcp.tool("分析轨迹")
async def analyze_trajectory_tool(workflow_id: str, params: Dict) -> Dict:
    """分析模拟轨迹数据，提取结构和动力学信息
    
    Args:
        workflow_id: 工作流程ID
        params: 分析参数
    """
    try:
        logger.info(f"开始轨迹分析，工作流ID: {workflow_id}, 参数: {params}")
        
        # 检查工作流是否存在
        workflow_dir = get_custom_workflow_directory(workflow_id)
        if not workflow_dir:
            logger.error(f"工作流目录不存在: {workflow_id}")
            return {
                "success": False,
                "error": f"工作流目录不存在: {workflow_id}"
            }
        
        # 检查文件路径
        if "trajectory_file" in params and not os.path.isabs(params["trajectory_file"]):
            trajectory_file = os.path.join(workflow_dir, params["trajectory_file"])
            if not os.path.exists(trajectory_file):
                logger.error(f"轨迹文件不存在: {trajectory_file}")
                return {
                    "success": False,
                    "error": f"轨迹文件不存在: {params['trajectory_file']}"
                }
            # 更新为相对路径，防止路径问题
            params["trajectory_file"] = os.path.relpath(trajectory_file, workflow_dir)
        
        if "structure_file" in params and not os.path.isabs(params["structure_file"]):
            structure_file = os.path.join(workflow_dir, params["structure_file"])
            if not os.path.exists(structure_file):
                logger.error(f"结构文件不存在: {structure_file}")
                return {
                    "success": False,
                    "error": f"结构文件不存在: {params['structure_file']}"
                }
            # 更新为相对路径，防止路径问题
            params["structure_file"] = os.path.relpath(structure_file, workflow_dir)
        
        logger.info(f"文件检查通过，准备执行分析: trajectory_file={params.get('trajectory_file')}, structure_file={params.get('structure_file')}")
        
        # 调用API函数执行分析
        result = await analyze_trajectory(workflow_id, params)
        
        # 记录结果
        if not result.get("success", False):
            logger.error(f"轨迹分析失败: {result.get('error', '未知错误')}")
        else:
            logger.info(f"轨迹分析成功完成")
            
        return result
    except Exception as e:
        import traceback
        error_msg = str(e)
        tb = traceback.format_exc()
        logger.error(f"轨迹分析过程中发生异常: {error_msg}")
        logger.error(f"异常堆栈: {tb}")
        
        return {
            "success": False,
            "error": f"分析轨迹时发生错误: {error_msg}",
            "details": tb
        }

# 可视化工具
@mcp.tool("应用VMD模板")
async def apply_vmd_template_tool(workflow_id: str, template_name: str, params: Optional[Dict] = None) -> Dict:
    """应用预定义的VMD可视化模板
    
    Args:
        workflow_id: 工作流程ID
        template_name: 模板名称
        params: 模板参数（可选）
    """
    return await apply_vmd_template(workflow_id, template_name, params)

@mcp.tool("获取可用的VMD模板")
async def get_available_templates_tool() -> Dict:
    """获取所有可用的VMD可视化模板列表"""
    return await get_available_templates()

# GROMACS命令执行工具
@mcp.tool("执行GROMACS命令")
async def execute_gromacs_command_tool(workflow_id: str, command: str, args: List[str] = None, input_data: Optional[str] = None) -> Dict:
    """执行GROMACS命令行工具
    
    Args:
        workflow_id: 工作流程ID
        command: GROMACS命令名称
        args: 命令参数列表（可选）
        input_data: 标准输入数据（可选，用于需要交互式输入的命令，如genion）
        
    Returns:
        Dict: 包含命令执行结果、标准输出和错误输出的字典
    """
    result = await execute_gromacs_command(workflow_id, command, args, input_data)
    # 确保将完整的标准输出和错误信息返回给用户
    return {
        "success": result["success"],
        "output": result["output"],    # 完整的命令标准输出
        "error": result["error"],      # 完整的命令错误输出
        "return_code": result["return_code"],
        "workflow_id": workflow_id,
        "command": command,
        "full_command": result.get("full_command", ""),
        "debug_info": result.get("debug_info", {})
    }

@mcp.tool("执行GROMACS命令序列")
async def execute_gromacs_command_sequence_tool(workflow_id: str, commands: List[Dict]) -> Dict:
    """执行一系列GROMACS命令
    
    连续执行多个GROMACS命令，适用于完成分子动力学模拟的完整流程。
    每个命令会等待前一个命令完成后再执行。
    
    Args:
        workflow_id: 工作流程ID
        commands: 命令列表，每个命令包含command、args和可选的input_data
        
    Returns:
        Dict: 包含所有命令执行结果的字典
    """
    results = []
    workflow_dir = get_custom_workflow_directory(workflow_id)
    
    if not workflow_dir:
        return {
            "success": False, 
            "error": "工作流程目录不存在", 
            "workflow_id": workflow_id
        }
    
    # 确保工作目录存在
    if not os.path.isdir(workflow_dir):
        error_msg = f"工作流程目录不存在或无法访问: {workflow_dir}"
        logger.error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "workflow_id": workflow_id
        }
    
    # 确保工作目录有正确的权限
    ensure_workflow_directory_permissions(workflow_dir)
    
    # 记录基本信息
    logger.info(f"开始执行命令序列，共{len(commands)}个命令，工作流ID: {workflow_id}")
    logger.info(f"工作目录: {workflow_dir}")
    
    for idx, cmd_info in enumerate(commands):
        command = cmd_info.get("command")
        args = cmd_info.get("args", [])
        input_data = cmd_info.get("input_data")
        step = cmd_info.get("step", f"步骤{idx+1}")
        
        logger.info(f"执行命令序列 - {step}: {command} {' '.join(str(a) for a in (args or []))}")
        
        # 执行单个命令
        result = await execute_gromacs_command(workflow_id, command, args, input_data)
        
        # 添加步骤信息
        result["step"] = step
        results.append(result)
        
        # 如果命令失败，打印详细错误信息并停止执行后续命令
        if not result["success"]:
            error_msg = result.get("error", "未知错误")
            output_msg = result.get("output", "")
            logger.error(f"命令序列在步骤 {step} 失败")
            logger.error(f"错误信息: {error_msg}")
            logger.error(f"命令输出: {output_msg}")
            
            # 获取更多调试信息
            debug_info = result.get("debug_info", {})
            if debug_info:
                logger.error(f"调试信息: {debug_info}")
                
            # 检查输入文件是否存在
            if args:
                for i, arg in enumerate(args):
                    if arg in ['-c', '-s', '-f', '-r', '-t', '-n'] and i + 1 < len(args):
                        file_path = args[i + 1]
                        if not os.path.isabs(file_path):
                            file_path = os.path.join(workflow_dir, file_path)
                        if not os.path.exists(file_path):
                            logger.error(f"文件不存在: {file_path}")
            
            break
    
    # 计算整体成功/失败状态
    all_success = all(r["success"] for r in results)
    
    # 汇总错误信息
    all_errors = []
    for r in results:
        if not r.get("success", False) and r.get("error"):
            all_errors.append(f"{r.get('step', '未知步骤')}: {r.get('error')}")
    
    return {
        "success": all_success,
        "results": results,
        "workflow_id": workflow_id,
        "completed_steps": len(results),
        "total_steps": len(commands),
        "error": "; ".join(all_errors) if all_errors else None
    }

@mcp.tool("运行分子动力学模拟阶段")
async def run_md_simulation_stage_tool(workflow_id: str, stage: str) -> Dict:
    """运行指定阶段的分子动力学模拟
    
    执行分子动力学模拟的特定阶段，如能量最小化、NVT平衡或NPT平衡。
    
    Args:
        workflow_id: 工作流程ID
        stage: 模拟阶段名称 (minimization, nvt, npt, production)
        
    Returns:
        Dict: 包含模拟执行结果的字典
    """
    # 获取工作流程信息
    workflow = service.get_workflow(workflow_id)
    if not workflow:
        return {"success": False, "error": f"工作流程不存在: {workflow_id}"}
        
    # 获取工作目录
    workflow_dir = get_custom_workflow_directory(workflow_id)
    if not workflow_dir:
        return {"success": False, "error": f"无法获取工作流程目录: {workflow_id}"}
        
    # 确保所需目录存在
    for subdir in ["em", "nvt", "npt", "md"]:
        os.makedirs(os.path.join(workflow_dir, subdir), exist_ok=True)
    
    # 检查前置步骤是否已完成
    if stage != "minimization":
        # 检查能量最小化结果
        em_gro = os.path.join(workflow_dir, "em", "em.gro")
        if not os.path.exists(em_gro):
            return {
                "success": False, 
                "error": f"能量最小化结果文件不存在: {em_gro}，请先运行能量最小化步骤"
            }
    
    if stage in ["npt", "production"]:
        # 检查NVT平衡结果
        nvt_gro = os.path.join(workflow_dir, "nvt", "nvt.gro")
        nvt_cpt = os.path.join(workflow_dir, "nvt", "nvt.cpt")
        if not os.path.exists(nvt_gro) or not os.path.exists(nvt_cpt):
            return {
                "success": False, 
                "error": f"NVT平衡结果文件不存在，请先运行NVT平衡步骤"
            }
    
    if stage == "production":
        # 检查NPT平衡结果
        npt_gro = os.path.join(workflow_dir, "npt", "npt.gro")
        npt_cpt = os.path.join(workflow_dir, "npt", "npt.cpt")
        if not os.path.exists(npt_gro) or not os.path.exists(npt_cpt):
            return {
                "success": False, 
                "error": f"NPT平衡结果文件不存在，请先运行NPT平衡步骤"
            }
    
    # 根据阶段名称准备不同的命令
    commands = []
    
    if stage == "minimization":
        # 能量最小化阶段
        commands = [
            {
                "step": "能量最小化准备",
                "command": "grompp",
                "args": [
                    "-f", str(workflow_dir / "em/em.mdp"),
                    "-c", str(workflow_dir / "solv_ions.gro"),
                    "-p", str(workflow_dir / "topol.top"),
                    "-o", str(workflow_dir / "em/em.tpr")
                ]
            },
            {
                "step": "运行能量最小化",
                "command": "mdrun",
                "args": [
                    "-v",
                    "-s", str(workflow_dir / "em/em.tpr"),
                    "-deffnm", str(workflow_dir / "em/em")
                ]
            }
        ]
    elif stage == "nvt":
        # NVT平衡阶段
        commands = [
            {
                "step": "NVT平衡准备",
                "command": "grompp",
                "args": [
                    "-f", str(workflow_dir / "nvt/nvt.mdp"),
                    "-c", str(workflow_dir / "em/em.gro"), 
                    "-r", str(workflow_dir / "em/em.gro"),  # 约束参考坐标
                    "-p", str(workflow_dir / "topol.top"),
                    "-o", str(workflow_dir / "nvt/nvt.tpr"),
                    "-maxwarn", "1"  # 允许一些警告
                ]
            },
            {
                "step": "运行NVT平衡",
                "command": "mdrun",
                "args": [
                    "-v",
                    "-s", str(workflow_dir / "nvt/nvt.tpr"),
                    "-deffnm", str(workflow_dir / "nvt/nvt")
                ]
            }
        ]
    elif stage == "npt":
        # NPT平衡阶段
        commands = [
            {
                "step": "NPT平衡准备",
                "command": "grompp",
                "args": [
                    "-f", str(workflow_dir / "npt/npt.mdp"),
                    "-c", str(workflow_dir / "nvt/nvt.gro"),
                    "-r", str(workflow_dir / "nvt/nvt.gro"),
                    "-t", str(workflow_dir / "nvt/nvt.cpt"),
                    "-p", str(workflow_dir / "topol.top"),
                    "-o", str(workflow_dir / "npt/npt.tpr"),
                    "-maxwarn", "1"  # 允许一些警告
                ]
            },
            {
                "step": "运行NPT平衡",
                "command": "mdrun",
                "args": [
                    "-v",
                    "-s", str(workflow_dir / "npt/npt.tpr"),
                    "-deffnm", str(workflow_dir / "npt/npt")
                ]
            }
        ]
    elif stage == "production":
        # 生产模拟阶段
        commands = [
            {
                "step": "生产模拟准备",
                "command": "grompp",
                "args": [
                    "-f", str(workflow_dir / "md/md.mdp"),
                    "-c", str(workflow_dir / "npt/npt.gro"),
                    "-t", str(workflow_dir / "npt/npt.cpt"),
                    "-p", str(workflow_dir / "topol.top"),
                    "-o", str(workflow_dir / "md/md.tpr"),
                    "-maxwarn", "1"  # 允许一些警告
                ]
            },
            {
                "step": "运行生产模拟",
                "command": "mdrun",
                "args": [
                    "-v",
                    "-s", str(workflow_dir / "md/md.tpr"),
                    "-deffnm", str(workflow_dir / "md/md")
                ]
            }
        ]
    else:
        return {"success": False, "error": f"未知的模拟阶段: {stage}"}
    
    # 记录阶段执行的开始
    logger.info(f"开始执行{stage}阶段模拟，工作流ID: {workflow_id}")
        
    # 执行命令序列
    result = await execute_gromacs_command_sequence_tool(workflow_id, commands)
    
    # 添加调试信息
    if not result["success"]:
        logger.error(f"{stage}阶段执行失败: {result.get('error', '未知错误')}")
        # 检查是否有具体错误信息
        if "results" in result:
            for cmd_result in result["results"]:
                if not cmd_result.get("success", False):
                    step = cmd_result.get("step", "未知步骤")
                    error = cmd_result.get("error", "未知错误")
                    logger.error(f"步骤 {step} 失败: {error}")
    else:
        logger.info(f"{stage}阶段执行成功")
    
    return result

# VMD相关工具
@mcp.tool("启动VMD图形界面")
async def launch_vmd_gui_tool(structure_file: Optional[str] = None, trajectory_file: Optional[str] = None) -> Dict:
    """启动VMD的图形界面并加载分子文件
    
    启动VMD分子可视化程序的图形用户界面，可以同时加载结构文件和轨迹文件。
    
    Args:
        structure_file: 可选的结构文件路径，如.gro、.pdb等
        trajectory_file: 可选的轨迹文件路径，如.xtc、.trr等
    
    Returns:
        Dict: 包含进程ID和启动状态的字典
    """
    # 检查文件是否存在
    if structure_file and not os.path.exists(structure_file):
        return {
            "success": False,
            "error": f"结构文件不存在: {structure_file}"
        }
    
    if trajectory_file and not os.path.exists(trajectory_file):
        return {
            "success": False,
            "error": f"轨迹文件不存在: {trajectory_file}"
        }
    
    # 如果同时提供了结构文件和轨迹文件，使用系统命令直接启动VMD
    if structure_file and trajectory_file:
        try:
            # 构建命令 - 在macOS上保证在后台运行
            if sys.platform == 'darwin':
                # 在macOS上使用VMD启动脚本的完整路径
                struct_abs_path = os.path.abspath(structure_file)
                traj_abs_path = os.path.abspath(trajectory_file)
                
                # 使用os.system直接运行shell命令
                # 这更接近于在终端手动输入命令的行为
                cmd = f"vmd {struct_abs_path} {traj_abs_path} &"
                logger.info(f"使用os.system直接启动VMD: {cmd}")
                
                # 使用os.system直接运行命令而不是通过asyncio
                os.system(cmd)
                
                # 由于我们使用了os.system，我们无法获取进程ID
                # 但这种方式更接近于终端手动输入，更可能成功
                process_id = None
                
                # 不等待进程完成，让它在后台运行
                logger.info(f"VMD GUI已启动，加载结构文件{structure_file}和轨迹文件{trajectory_file}")
                
                return {
                    "success": True,
                    "pid": process_id,
                    "display": os.environ.get("DISPLAY", ":0"),
                    "message": "VMD图形界面已成功启动，并加载了结构和轨迹文件",
                    "structure_file": structure_file,
                    "trajectory_file": trajectory_file
                }
            else:
                # 在其他系统上也使用系统命令
                struct_abs_path = os.path.abspath(structure_file)
                traj_abs_path = os.path.abspath(trajectory_file)
                
                # 构建命令
                cmd = f"vmd {struct_abs_path} {traj_abs_path} &"
                logger.info(f"使用系统命令启动VMD: {cmd}")
                
                # 使用系统命令运行VMD
                os.system(cmd)
                
                # 不等待进程完成，让它在后台运行
                logger.info(f"VMD GUI已启动，加载结构文件{structure_file}和轨迹文件{trajectory_file}")
                
                return {
                    "success": True,
                    "pid": None,
                    "display": os.environ.get("DISPLAY", ":0"),
                    "message": "VMD图形界面已成功启动，并加载了结构和轨迹文件",
                    "structure_file": structure_file,
                    "trajectory_file": trajectory_file
                }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"启动VMD时发生异常: {error_msg}")
            return {
                "success": False,
                "error": f"启动VMD时发生异常: {error_msg}"
            }
    
    # 如果只提供了结构文件或没有提供任何文件，使用原有方法
    return await service.vmd_manager.launch_gui(structure_file)

@mcp.tool("执行VMD TCL脚本")
async def execute_vmd_script_tool(
    script: str, 
    process_id: Optional[int] = None, 
    structure_file: Optional[str] = None,
    generate_image: bool = False,
    image_file: Optional[str] = None
) -> Dict:
    """向VMD实例执行TCL脚本
    
    向已运行或新启动的VMD实例发送TCL脚本进行执行。可以选择性地加载分子结构并生成渲染图像。
    
    Args:
        script: TCL脚本内容
        process_id: 可选的VMD进程ID（若不提供则启动新实例）
        structure_file: 可选的分子结构文件路径
        generate_image: 是否生成渲染图像
        image_file: 输出图像文件路径（可选）
    
    Returns:
        Dict: 包含脚本执行结果和生成图像路径的字典
    """
    return await service.vmd_manager.execute_script(
        script, 
        process_id, 
        structure_file,
        generate_image,
        image_file
    )

@mcp.tool("关闭VMD实例")
async def close_vmd_instance_tool(process_id: int) -> Dict:
    """关闭指定的VMD实例
    
    根据进程ID关闭正在运行的VMD实例。
    
    Args:
        process_id: VMD实例的进程ID
    
    Returns:
        Dict: 操作结果
    """
    success = await service.vmd_manager.close_instance(process_id)
    return {
        "success": success,
        "message": f"VMD实例 {process_id} {'已关闭' if success else '关闭失败'}"
    }

@mcp.tool("列出VMD实例")
async def list_vmd_instances_tool() -> Dict:
    """列出所有正在运行的VMD实例
    
    Returns:
        Dict: 包含所有VMD实例信息的字典
    """
    instances = service.vmd_manager.list_instances()
    return {
        "success": True,
        "instances": instances,
        "count": len(instances)
    }

# 分子动力学模拟工具
@mcp.tool("准备分子动力学模拟")
async def prepare_simulation_tool(
    workflow_id: str,
    structure_file: str,
    force_field: str = "amber99sb-ildn",
    simulation_params: Optional[Dict] = None
) -> Dict:
    """准备分子动力学模拟
    
    为分子动力学模拟准备所有必要的输入文件和参数，包括系统构建、能量最小化、平衡和生产模拟的配置。
    
    Args:
        workflow_id: 工作流程ID
        structure_file: 结构文件路径（PDB格式）
        force_field: 力场名称（默认为amber99sb-ildn）
        simulation_params: 模拟参数（可选）
    
    Returns:
        Dict: 包含准备好的输入文件和命令的字典
    """
    # 检查是否有自定义工作流目录
    custom_dir = get_custom_workflow_directory(workflow_id)
    if custom_dir and workflow_id in workflow_dir_mapping:
        # 有自定义目录，确保目录权限正确
        ensure_workflow_directory_permissions(custom_dir)
        
        # 处理结构文件路径 - 使其相对于工作流目录
        structure_path = Path(structure_file)
        if structure_path.is_absolute():
            # 将绝对路径转为相对路径
            try:
                rel_path = os.path.relpath(structure_path, custom_dir)
                structure_file = rel_path
            except ValueError:
                # 路径可能在不同驱动器上，无法获取相对路径，保持原样
                pass
        
        logger.info(f"使用自定义工作流目录: {custom_dir}, 调整后的结构文件路径: {structure_file}")
        
    # 调用服务方法准备模拟
    result = await service.prepare_simulation(
        workflow_id,
        structure_file,
        force_field,
        simulation_params,
        custom_workflow_dir=custom_dir  # 传递自定义工作目录
    )
    
    # 如果成功，确保工作流目录和所有子目录都有正确权限
    if result.get("success", False) and custom_dir:
        ensure_workflow_directory_permissions(custom_dir)
        
        # 再次检查关键目录是否存在并有正确权限
        for subdir in ["em", "nvt", "npt", "md"]:
            subdir_path = custom_dir / subdir
            if not subdir_path.exists():
                subdir_path.mkdir(parents=True, exist_ok=True)
            try:
                import stat
                os.chmod(subdir_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
            except Exception as e:
                logger.warning(f"设置{subdir}目录权限失败: {e}")
    
    return result

# 配置工具
@mcp.tool("更新服务配置")
async def update_config_tool(vmd_path: Optional[str] = None, gmx_path: Optional[str] = None) -> Dict:
    """更新服务配置
    
    更新VMD路径、GROMACS路径等服务配置。
    
    Args:
        vmd_path: VMD可执行文件路径（可选）
        gmx_path: GROMACS可执行文件路径（可选）
        
    Returns:
        Dict: 更新后的配置
    """
    return await update_config(vmd_path=vmd_path, gmx_path=gmx_path)

@mcp.tool("获取当前配置")
async def get_config_tool() -> Dict:
    """获取当前服务配置
    
    Returns:
        Dict: 当前配置信息，包含VMD路径、结构搜索路径和GROMACS路径
    """
    return await get_config()

#====================
# 配置设置
#====================

@mcp.resource("gmx-vmd://config/update?vmd_path={vmd_path}&structure_search_paths={structure_search_paths}&gmx_path={gmx_path}")
async def update_config(vmd_path: Optional[str] = None, structure_search_paths: Optional[List[str]] = None, gmx_path: Optional[str] = None) -> Dict:
    """更新服务配置"""
    if vmd_path:
        vmd_config["vmd_path"] = vmd_path
        service.vmd_manager.vmd_path = vmd_path
        
    if structure_search_paths:
        # 清除现有搜索路径
        service.structure_search_paths.clear()
        # 添加新的搜索路径
        vmd_config["structure_search_paths"] = structure_search_paths
        for path in structure_search_paths:
            service.add_structure_search_path(path)
            
    if gmx_path:
        gmx_config["gmx_path"] = gmx_path
    
    # 保存配置到文件
    try:
        config = {
            "vmd": vmd_config,
            "gmx": gmx_config
        }
        config_file = Path(os.getcwd()) / "config.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=4)
        logger.info(f"配置已保存到文件: {config_file}")
    except Exception as e:
        logger.error(f"保存配置到文件时出错: {e}")
    
    return {
        "success": True,
        "config": {**vmd_config, **gmx_config}
    }

@mcp.resource("gmx-vmd://config")
async def get_config() -> Dict:
    """获取当前配置"""
    return {**vmd_config, **gmx_config}

#====================
# 结构文件搜索
#====================

@mcp.resource("gmx-vmd://structures/search?pattern={pattern}")
async def search_structures(pattern: str) -> Dict:
    """搜索结构文件
    
    Args:
        pattern: 搜索模式，可以是文件名、部分路径或结构名称
    """
    results = service.find_structure_files(pattern)
    return {
        "success": True,
        "count": len(results),
        "results": results
    }

#====================
# 工具定义
#====================

@mcp.tool("搜索分子结构文件")
async def search_structures_tool(pattern: str) -> Dict:
    """搜索分子结构文件
    
    根据文件名、路径或结构名称搜索分子结构文件。
    
    Args:
        pattern: 搜索模式，例如"1aki"或"protein"
        
    Returns:
        Dict: 包含搜索结果的字典
    """
    return await search_structures(pattern)

@mcp.tool("配置结构搜索路径")
async def configure_search_paths_tool(paths: List[str]) -> Dict:
    """配置结构文件搜索路径
    
    设置在哪些目录下搜索分子结构文件。
    
    Args:
        paths: 搜索路径列表
        
    Returns:
        Dict: 更新后的配置
    """
    return await update_config(structure_search_paths=paths)

@mcp.tool("修改模拟参数")
async def modify_simulation_params_tool(
    workflow_id: str,
    instruction: str,
    stage: str = "all"  # 可以是 "minimization", "nvt", "npt", "production" 或 "all"
) -> Dict:
    """通过自然语言指令修改分子动力学模拟参数
    
    使用自然语言描述修改模拟参数的需求，系统会智能解析并应用到相应的mdp文件中。
    
    Args:
        workflow_id: 工作流程ID
        instruction: 自然语言指令，例如"将温度设置为310K"、"NVT平衡运行2ns"等
        stage: 要修改的模拟阶段，可选值为"minimization"、"nvt"、"npt"、"production"或"all"
        
    Returns:
        Dict: 包含修改结果的字典
    """
    # 获取工作流程信息
    workflow = service.get_workflow(workflow_id)
    if not workflow:
        return {"success": False, "error": f"工作流程不存在: {workflow_id}"}
        
    # 获取工作目录（使用自定义目录）
    workflow_dir = get_custom_workflow_directory(workflow_id)
    if not workflow_dir:
        return {"success": False, "error": f"无法获取工作流程目录: {workflow_id}"}
    
    # 确保相关目录存在，并设置权限
    for subdir in ["em", "nvt", "npt", "md"]:
        subdir_path = os.path.join(workflow_dir, subdir)
        os.makedirs(subdir_path, exist_ok=True)
        try:
            import stat
            os.chmod(subdir_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        except Exception as e:
            logger.warning(f"设置{subdir}目录权限失败: {e}")
    
    # 定义要修改的mdp文件
    mdp_files = []
    if stage == "all" or stage == "minimization":
        mdp_files.append({"path": workflow_dir / "em" / "em.mdp", "stage": "能量最小化"})
    if stage == "all" or stage == "nvt":
        mdp_files.append({"path": workflow_dir / "nvt" / "nvt.mdp", "stage": "NVT平衡"})
    if stage == "all" or stage == "npt":
        mdp_files.append({"path": workflow_dir / "npt" / "npt.mdp", "stage": "NPT平衡"})
    if stage == "all" or stage == "production":
        mdp_files.append({"path": workflow_dir / "md" / "md.mdp", "stage": "生产模拟"})
    
    # 检查mdp文件是否存在
    missing_files = []
    for mdp_file in mdp_files:
        if not os.path.exists(mdp_file["path"]):
            missing_files.append(f"{mdp_file['stage']}参数文件({mdp_file['path']})")
    
    if missing_files:
        # 如果mdp文件不存在，可能需要先运行准备模拟步骤
        return {
            "success": False,
            "error": f"以下参数文件不存在: {', '.join(missing_files)}，请先运行'准备分子动力学模拟'工具"
        }
    
    # 解析自然语言指令并生成相应的修改
    modifications = parse_simulation_params_instruction(instruction)
    
    # 应用修改到mdp文件
    modified_files = []
    for mdp_file in mdp_files:
        # 读取原始mdp文件内容
        with open(mdp_file["path"], "r") as f:
            original_content = f.read()
        
        # 应用修改
        new_content = apply_mdp_modifications(original_content, modifications, mdp_file["stage"])
        
        # 如果内容有变化，写回文件
        if new_content != original_content:
            with open(mdp_file["path"], "w") as f:
                f.write(new_content)
            modified_files.append(mdp_file["path"])
    
    # 返回修改结果
    if modified_files:
        logger.info(f"成功修改了以下文件: {', '.join([str(path) for path in modified_files])}")
        logger.info(f"应用的修改: {modifications}")
        return {
            "success": True,
            "message": f"已成功修改以下参数文件: {', '.join([str(path) for path in modified_files])}",
            "modifications": modifications,
            "affected_stages": [mdp_file["stage"] for mdp_file in mdp_files if mdp_file["path"] in modified_files]
        }
    else:
        logger.warning(f"未能应用任何修改，指令: '{instruction}'")
        logger.warning(f"解析结果: {modifications}")
        logger.warning(f"目标文件: {[mdp_file['path'] for mdp_file in mdp_files]}")
        return {
            "success": False,
            "message": "未能应用任何修改，请检查您的指令是否有效",
            "instruction": instruction,
            "debug_info": {
                "parsed_modifications": modifications,
                "target_files": [str(mdp_file["path"]) for mdp_file in mdp_files],
                "file_exists": [os.path.exists(mdp_file["path"]) for mdp_file in mdp_files]
            }
        }

def parse_simulation_params_instruction(instruction: str) -> Dict:
    """解析自然语言指令，提取模拟参数修改
    
    Args:
        instruction: 自然语言指令
        
    Returns:
        Dict: 包含参数名称和值的字典
    """
    modifications = {}
    
    # 解析温度设置
    if "温度" in instruction or "temperature" in instruction.lower():
        # 匹配数字和单位K
        import re
        temp_match = re.search(r'(\d+(?:\.\d+)?)\s*[Kk]', instruction)
        if temp_match:
            modifications["temperature"] = float(temp_match.group(1))
    
    # 解析压力设置
    if "压力" in instruction or "压强" in instruction or "pressure" in instruction.lower():
        # 匹配数字和单位bar
        import re
        press_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:bar|巴)', instruction)
        if press_match:
            modifications["pressure"] = float(press_match.group(1))
    
    # 解析模拟时间设置
    if "时间" in instruction or "步数" in instruction or "步" in instruction or "time" in instruction.lower() or "step" in instruction.lower() or "运行" in instruction or "进行" in instruction:
        import re
        # 改进的正则表达式，更灵活地匹配数字和单位
        time_match = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(?:ns|纳秒|ps|皮秒)', instruction)
        if time_match:
            time_value = float(time_match.group(1))
            # 确定单位（默认为ps）
            time_unit = "ps"
            if "ns" in instruction or "纳秒" in instruction:
                time_unit = "ns"
            
            # 转换为ps
            if time_unit in ["ns", "纳秒"]:
                time_value *= 1000  # 转换为ps
                
            modifications["simulation_time"] = time_value
            logger.info(f"从指令中提取的模拟时间: {time_value} ps (原始指令: '{instruction}')")
        else:
            logger.warning(f"无法从指令中提取模拟时间: '{instruction}'")
    
    # 解析时间步长设置
    if "步长" in instruction or "time step" in instruction.lower() or "dt" in instruction.lower():
        import re
        # 匹配数字和单位fs或ps
        dt_match = re.search(r'(\d+(?:\.\d+)?)\s*(fs|飞秒|ps|皮秒)', instruction)
        if dt_match:
            dt_value = float(dt_match.group(1))
            dt_unit = dt_match.group(2)
            
            # 转换为ps
            if dt_unit in ["fs", "飞秒"]:
                dt_value /= 1000  # 转换为ps
                
            modifications["time_step"] = dt_value
    
    # 解析输出频率设置
    if "输出" in instruction or "轨迹" in instruction or "output" in instruction.lower() or "trajectory" in instruction.lower():
        import re
        # 匹配数字和单位ps或ns
        out_match = re.search(r'每\s*(\d+(?:\.\d+)?)\s*(ps|皮秒|ns|纳秒)', instruction)
        if out_match:
            out_value = float(out_match.group(1))
            out_unit = out_match.group(2)
            
            # 转换为ps
            if out_unit in ["ns", "纳秒"]:
                out_value *= 1000  # 转换为ps
                
            modifications["output_frequency"] = out_value
    
    # 解析约束设置
    if "约束" in instruction or "constraint" in instruction.lower():
        if "无约束" in instruction or "no constraint" in instruction.lower():
            modifications["constraints"] = "none"
        elif "氢键" in instruction or "h-bond" in instruction.lower():
            modifications["constraints"] = "h-bonds"
        elif "所有键" in instruction or "all bonds" in instruction.lower():
            modifications["constraints"] = "all-bonds"
    
    return modifications

def apply_mdp_modifications(mdp_content: str, modifications: Dict, stage: str) -> str:
    """应用参数修改到mdp文件内容
    
    Args:
        mdp_content: 原始mdp文件内容
        modifications: 要应用的修改
        stage: 模拟阶段
        
    Returns:
        str: 修改后的mdp文件内容
    """
    import re
    lines = mdp_content.split('\n')
    modified_lines = []
    
    # 提取当前时间步长
    dt_match = re.search(r'dt\s*=\s*(\d+(?:\.\d+)?)', mdp_content)
    current_dt = float(dt_match.group(1)) if dt_match else 0.002  # 默认值
    
    # 计算每ps的步数
    steps_per_ps = int(1.0 / current_dt)
    
    # 处理温度修改
    if "temperature" in modifications and ("NVT" in stage or "NPT" in stage or "生产" in stage):
        temp_value = modifications["temperature"]
        # 修改ref_t参数
        ref_t_pattern = re.compile(r'(ref_t\s*=\s*)(\d+(?:\.\d+)?)(.*)')
        temp_modified = False
        
        for line in lines:
            if ref_t_pattern.match(line):
                # 提取当前参数值后面的部分（可能包含注释）
                match = ref_t_pattern.match(line)
                prefix = match.group(1)
                suffix = match.group(3)
                
                # 根据格式可能是"ref_t = 300 300"这样的形式
                if " " in suffix.strip():
                    # 如果有多个温度值，全部替换
                    groups = suffix.strip().split()
                    new_suffix = " ".join([str(temp_value)] * len(groups))
                    modified_lines.append(f"{prefix}{temp_value} {new_suffix}")
                else:
                    # 单个温度值
                    modified_lines.append(f"{prefix}{temp_value}{suffix}")
                temp_modified = True
            else:
                modified_lines.append(line)
                
        # 如果没有找到并修改温度参数，添加它
        if not temp_modified and ("NVT" in stage or "NPT" in stage or "生产" in stage):
            modified_lines.append(f"ref_t = {temp_value} {temp_value}  ; Modified by user instruction")
    else:
        modified_lines = lines
    
    # 处理压力修改
    if "pressure" in modifications and ("NPT" in stage or "生产" in stage):
        press_value = modifications["pressure"]
        # 修改ref_p参数
        ref_p_pattern = re.compile(r'(ref_p\s*=\s*)(\d+(?:\.\d+)?)(.*)')
        press_modified = False
        
        lines = modified_lines
        modified_lines = []
        
        for line in lines:
            if ref_p_pattern.match(line):
                # 提取当前参数值后面的部分（可能包含注释）
                match = ref_p_pattern.match(line)
                prefix = match.group(1)
                suffix = match.group(3)
                
                modified_lines.append(f"{prefix}{press_value}{suffix}")
                press_modified = True
            else:
                modified_lines.append(line)
                
        # 如果没有找到并修改压力参数，添加它
        if not press_modified and ("NPT" in stage or "生产" in stage):
            modified_lines.append(f"ref_p = {press_value}  ; Modified by user instruction")
    
    # 处理模拟时间修改
    if "simulation_time" in modifications:
        time_value_ps = modifications["simulation_time"]  # 单位已转为ps
        
        # 根据时间步长计算步数
        nsteps = int(time_value_ps / current_dt)
        logger.info(f"基于时间步长 {current_dt} ps 计算的步数: {nsteps}")
        
        # 修改nsteps参数
        nsteps_pattern = re.compile(r'(nsteps\s*=\s*)(\d+)(.*)')
        time_modified = False
        
        lines = modified_lines
        modified_lines = []
        
        for line in lines:
            if nsteps_pattern.match(line):
                # 提取当前参数值后面的部分（可能包含注释）
                match = nsteps_pattern.match(line)
                prefix = match.group(1)
                old_value = match.group(2)
                suffix = match.group(3)
                
                logger.info(f"修改模拟步数: {old_value} -> {nsteps}")
                modified_lines.append(f"{prefix}{nsteps}{suffix}")
                time_modified = True
            else:
                modified_lines.append(line)
                
        # 如果没有找到并修改步数参数，添加它
        if not time_modified:
            logger.info(f"未找到nsteps参数，添加新行: nsteps = {nsteps}")
            modified_lines.append(f"nsteps = {nsteps}  ; Modified by user instruction")
    
    # 处理时间步长修改
    if "time_step" in modifications and stage != "能量最小化":  # 能量最小化不使用dt
        dt_value = modifications["time_step"]  # 单位已转为ps
        
        # 更新时间步长
        dt_pattern = re.compile(r'(dt\s*=\s*)(\d+(?:\.\d+)?)(.*)')
        dt_modified = False
        
        lines = modified_lines
        modified_lines = []
        
        for line in lines:
            if dt_pattern.match(line):
                # 提取当前参数值后面的部分（可能包含注释）
                match = dt_pattern.match(line)
                prefix = match.group(1)
                suffix = match.group(3)
                
                modified_lines.append(f"{prefix}{dt_value}{suffix}")
                dt_modified = True
            else:
                modified_lines.append(line)
                
        # 如果没有找到并修改时间步长参数，添加它
        if not dt_modified and stage != "能量最小化":
            modified_lines.append(f"dt = {dt_value}  ; Modified by user instruction")
            
        # 更新步数/ps
        steps_per_ps = int(1.0 / dt_value)
    
    # 处理输出频率修改
    if "output_frequency" in modifications:
        out_freq_ps = modifications["output_frequency"]  # 单位已转为ps
        
        # 计算对应的步数
        out_steps = int(out_freq_ps * steps_per_ps)
        
        # 修改轨迹输出相关参数
        output_params = {
            "nstxtcout": out_steps,    # 压缩轨迹输出频率
            "nstxout": out_steps * 10, # 完整轨迹输出频率
            "nstvout": out_steps * 10, # 速度输出频率
            "nstfout": out_steps * 10, # 力输出频率
            "nstlog": out_steps,       # 日志输出频率
            "nstenergy": out_steps     # 能量输出频率
        }
        
        lines = modified_lines
        modified_lines = []
        modified_params = set()
        
        # 修改已存在的参数
        for line in lines:
            param_modified = False
            for param, value in output_params.items():
                param_pattern = re.compile(f'({param}\\s*=\\s*)(\\d+)(.*)')
                if param_pattern.match(line):
                    # 提取当前参数值后面的部分（可能包含注释）
                    match = param_pattern.match(line)
                    prefix = match.group(1)
                    suffix = match.group(3)
                    
                    modified_lines.append(f"{prefix}{value}{suffix}")
                    modified_params.add(param)
                    param_modified = True
                    break
            
            if not param_modified:
                modified_lines.append(line)
        
        # 添加未找到的参数
        for param, value in output_params.items():
            if param not in modified_params:
                modified_lines.append(f"{param} = {value}  ; Modified by user instruction")
    
    # 处理约束设置
    if "constraints" in modifications:
        constraint_value = modifications["constraints"]
        
        # 修改constraints参数
        constraints_pattern = re.compile(r'(constraints\s*=\s*)(\S+)(.*)')
        constraint_modified = False
        
        lines = modified_lines
        modified_lines = []
        
        for line in lines:
            if constraints_pattern.match(line):
                # 提取当前参数值后面的部分（可能包含注释）
                match = constraints_pattern.match(line)
                prefix = match.group(1)
                suffix = match.group(3)
                
                modified_lines.append(f"{prefix}{constraint_value}{suffix}")
                constraint_modified = True
            else:
                modified_lines.append(line)
                
        # 如果没有找到并修改约束参数，添加它
        if not constraint_modified:
            modified_lines.append(f"constraints = {constraint_value}  ; Modified by user instruction")
    
    # 检查是否真的修改了文件内容
    result = '\n'.join(modified_lines)
    if "simulation_time" in modifications and 'nsteps' not in result:
        logger.warning(f"警告: 修改后的内容中没有找到nsteps参数")
        
    return result

@mcp.tool("获取RMSD分析示例")
async def get_rmsd_analysis_example_tool(workflow_id: str) -> Dict:
    """获取RMSD分析的参数示例
    
    根据指定的工作流生成RMSD分析所需的参数示例。
    
    Args:
        workflow_id: 工作流程ID
        
    Returns:
        Dict: 包含RMSD分析参数示例的字典
    """
    # 获取工作流目录（使用自定义目录）
    workflow_dir = get_custom_workflow_directory(workflow_id)
    if not workflow_dir:
        return {
            "success": False,
            "error": f"工作流程目录不存在: {workflow_id}"
        }
    
    # 尝试找到可用的轨迹文件和结构文件
    trajectory_files = []
    structure_files = []
    
    # 检查em目录
    em_dir = workflow_dir / "em"
    if os.path.exists(em_dir):
        if os.path.exists(em_dir / "em.xtc"):
            trajectory_files.append("em/em.xtc")
        if os.path.exists(em_dir / "em.trr"):
            trajectory_files.append("em/em.trr")
        if os.path.exists(em_dir / "em.gro"):
            structure_files.append("em/em.gro")
    
    # 检查nvt目录
    nvt_dir = workflow_dir / "nvt"
    if os.path.exists(nvt_dir):
        if os.path.exists(nvt_dir / "nvt.xtc"):
            trajectory_files.append("nvt/nvt.xtc")
        if os.path.exists(nvt_dir / "nvt.trr"):
            trajectory_files.append("nvt/nvt.trr")
        if os.path.exists(nvt_dir / "nvt.gro"):
            structure_files.append("nvt/nvt.gro")
    
    # 检查npt目录
    npt_dir = workflow_dir / "npt"
    if os.path.exists(npt_dir):
        if os.path.exists(npt_dir / "npt.xtc"):
            trajectory_files.append("npt/npt.xtc")
        if os.path.exists(npt_dir / "npt.trr"):
            trajectory_files.append("npt/npt.trr")
        if os.path.exists(npt_dir / "npt.gro"):
            structure_files.append("npt/npt.gro")
    
    # 检查md目录
    md_dir = workflow_dir / "md"
    if os.path.exists(md_dir):
        if os.path.exists(md_dir / "md.xtc"):
            trajectory_files.append("md/md.xtc")
        if os.path.exists(md_dir / "md.trr"):
            trajectory_files.append("md/md.trr")
        if os.path.exists(md_dir / "md.gro"):
            structure_files.append("md/md.gro")
    
    # 也检查根目录的结构文件
    for file in os.listdir(workflow_dir):
        if file.endswith(".gro") and os.path.isfile(workflow_dir / file):
            structure_files.append(file)
    
    # 生成示例参数
    example = {
        "analysis_type": "rmsd",
        "output_prefix": "rmsd_analysis",
        "selection": "protein",
        "begin_time": 0,
        "end_time": -1,
        "dt": 1
    }
    
    # 添加找到的文件
    if trajectory_files:
        example["trajectory_file"] = trajectory_files[0]  # 使用第一个找到的轨迹文件
    else:
        example["trajectory_file"] = "请提供轨迹文件路径，例如：npt/npt.xtc"
        
    if structure_files:
        example["structure_file"] = structure_files[0]  # 使用第一个找到的结构文件
    else:
        example["structure_file"] = "请提供结构文件路径，例如：npt/npt.gro"
    
    return {
        "success": True,
        "message": "RMSD分析参数示例",
        "example": example,
        "note": "请注意：analysis_type必须使用小写'rmsd'，且必须提供structure_file和trajectory_file参数",
        "available_files": {
            "trajectory_files": trajectory_files,
            "structure_files": structure_files
        }
    }

# 导入VMD模块的部分
try:
    import vmd
    from vmd import molecule, display, animate, molrep, color, material, render, trans
    HAS_VMD_PYTHON = True
except ImportError:
    HAS_VMD_PYTHON = False
    logger.warning("未找到vmd-python模块，一些功能可能受限")

@mcp.tool("加载GROMACS轨迹")
async def load_gromacs_trajectory_tool(
    workflow_id: str,
    trajectory_file: str,
    structure_file: str,
    selection: str = "all",
    generate_image: bool = True,
    image_file: Optional[str] = None,
    representation: str = "动态新卡通"
) -> Dict:
    """加载并可视化GROMACS格式的分子模拟轨迹
    
    使用VMD加载分子模拟轨迹并应用一些基本的可视化设置。可以选择生成静态渲染图像。
    
    Args:
        workflow_id: 工作流程ID
        trajectory_file: 轨迹文件路径，相对于工作流程目录（如 md/md.xtc）或绝对路径
        structure_file: 结构文件路径，相对于工作流程目录（如 md/md.gro）或绝对路径
        selection: VMD选择表达式（默认为"all"，选择所有原子）
        generate_image: 是否生成渲染图像
        image_file: 输出图像文件名（可选），默认为"trajectory_view.png"
        representation: 可视化表现形式，可选值："动态新卡通"、"标准"、"卡通"、"VDW"、"Licorice"、"CPK"
    
    Returns:
        Dict: 包含加载结果和图像路径的字典
    """
    # 获取工作流程目录
    workflow_dir = get_custom_workflow_directory(workflow_id)
    if not workflow_dir:
        return {
            "success": False,
            "error": f"工作流程目录不存在: {workflow_id}"
        }
    
    # 处理文件路径（支持绝对路径和相对路径）
    logger.info(f"处理文件路径: 轨迹={trajectory_file}, 结构={structure_file}, 工作目录={workflow_dir}")
    
    # 构建完整的文件路径（如果是相对路径，则添加工作目录前缀）
    traj_path = trajectory_file if os.path.isabs(trajectory_file) else os.path.join(workflow_dir, trajectory_file)
    struct_path = structure_file if os.path.isabs(structure_file) else os.path.join(workflow_dir, structure_file)
    
    logger.info(f"最终处理后的文件路径: 轨迹={traj_path}, 结构={struct_path}")
    
    # 检查文件是否存在
    if not os.path.exists(traj_path):
        return {
            "success": False,
            "error": f"轨迹文件不存在: {traj_path}"
        }
    
    if not os.path.exists(struct_path):
        return {
            "success": False,
            "error": f"结构文件不存在: {struct_path}"
        }
    
    # 设置输出图像文件
    if generate_image:
        if not image_file:
            image_file = "trajectory_view.png"
        # 处理图像文件路径
        image_path = image_file if os.path.isabs(image_file) else os.path.join(workflow_dir, image_file)
        # 确保输出目录存在并有写权限
        image_dir = os.path.dirname(os.path.abspath(image_path))
        os.makedirs(image_dir, exist_ok=True)
        # 确保目录具有写权限
        try:
            import stat
            os.chmod(image_dir, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        except Exception as e:
            logger.warning(f"设置图像目录权限失败: {e}")
    else:
        image_path = None
    
    # 同时使用两种方法加载轨迹：
    # 1. vmd-python方式（如果可用）
    # 2. 系统命令方式（作为备选）
    
    # 先尝试使用vmd-python方式
    if HAS_VMD_PYTHON:
        try:
            logger.info("使用vmd-python模块加载轨迹")
            # 创建新的可视化会话
            molid = molecule.load('gro', struct_path)
            molecule.read(molid, 'xtc', traj_path)
            
            # 应用显示设置
            display.display(reset=True)
            display.projection("Orthographic")
            display.depthcue(False)
            display.rendermode("GLSL")
            color.color("Display", "Background", "white")
            
            # 设置动画模式 - 根据文档使用animate模块
            animate.activate(molid)
            animate.goto(0)  # 跳到第一帧
            animate.forward()  # 开始向前播放
            animate.once()  # 播放一次
            
            # 根据representation设置显示风格
            molrep.delrep(0, molid)  # 删除默认显示
            
            # 添加蛋白质表示
            if representation == "动态新卡通" or representation == "卡通":
                molrep.addrep(molid, 
                              selection=f"{selection} and (not water) and (not ions)",
                              style="NewCartoon",
                              color="Structure")
            elif representation == "标准":
                molrep.addrep(molid,
                              selection=f"{selection} and (not water) and (not ions)",
                              style="Lines",
                              color="Name")
            elif representation == "VDW":
                molrep.addrep(molid,
                              selection=f"{selection} and (not water) and (not ions)", 
                              style="VDW",
                              color="Name")
            elif representation == "Licorice":
                molrep.addrep(molid,
                              selection=f"{selection} and (not water) and (not ions)",
                              style="Licorice",
                              color="Name")
            elif representation == "CPK":
                molrep.addrep(molid,
                              selection=f"{selection} and (not water) and (not ions)", 
                              style="CPK",
                              color="Name")
            
            # 添加水分子点状表示
            molrep.addrep(molid, 
                          selection="water", 
                          style="Points", 
                          color="Name",
                          material="Transparent")
            
            # 添加离子VDW表示
            molrep.addrep(molid, 
                          selection="ions or name NA or name CL or name NA+ or name CL- or name CA or name MG or name ZN",
                          style="VDW",
                          color="Name")
            
            # 调整视角
            display.zoom(1.5)
            trans.rotate('x', -30)
            trans.rotate('y', 45)
            
            # 生成图像（如果需要）
            image_result = None
            if generate_image and image_path:
                render.render('snapshot', image_path)
                image_result = image_path
                logger.info(f"使用vmd-python生成图像: {image_path}")
            
            # 成功使用vmd-python加载轨迹
            return {
                "success": True,
                "message": "成功使用vmd-python加载GROMACS轨迹",
                "vmd_process_id": None,  # vmd-python没有独立进程ID
                "trajectory_file": traj_path,
                "structure_file": struct_path,
                "image_path": image_result,
                "method": "vmd-python",
                "note": "VMD Python界面已加载，请在VMD窗口中查看"
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"使用vmd-python加载轨迹时出错: {error_msg}")
            # 如果vmd-python方式失败，继续尝试系统命令方式
    
    # 使用系统命令方式作为备选
    try:
        logger.info("使用系统命令方式加载VMD轨迹")
        
        # 生成一个非常简单的TCL脚本，只用于生成图像
        if generate_image and image_path:
            # 创建在公共临时目录中
            temp_dir = os.path.join(os.path.dirname(workflow_dir), "temp")
            os.makedirs(temp_dir, exist_ok=True)
            try:
                import stat
                os.chmod(temp_dir, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
            except Exception as e:
                logger.warning(f"设置临时目录权限失败: {e}")
            
            img_tcl_fd, img_tcl_path = tempfile.mkstemp(dir=temp_dir, suffix='.tcl')
            with os.fdopen(img_tcl_fd, 'w') as f:
                f.write(f"""
                # 加载结构和轨迹
                mol new "{struct_path}" type gro waitfor all
                mol addfile "{traj_path}" type xtc waitfor all
                
                # 调整视角
                display resetview
                color Display Background white
                scale by 1.5
                rotate x by -30
                rotate y by 45
                
                # 生成图像
                render snapshot "{image_path}" display %s
                exit
                """)
                
            # 使用text模式运行VMD生成图像（不打开GUI）
            vmd_path = "/Applications/VMD.app/Contents/MacOS/startup.command" if sys.platform == 'darwin' else "vmd"
            img_cmd = f"{vmd_path} -dispdev text -e {img_tcl_path}"
            logger.info(f"执行VMD命令生成图像: {img_cmd}")
            
            # 使用subprocess执行命令，等待完成
            import subprocess
            subprocess.run(img_cmd, shell=True, check=False)
            
            logger.info(f"图像生成完成: {image_path}")
        
        # 使用最直接的方法启动VMD查看器
        # 直接使用终端命令，确保使用绝对路径
        view_cmd = f"cd {os.path.dirname(struct_path)} && vmd {os.path.basename(struct_path)} {os.path.basename(traj_path)}"
        logger.info(f"启动VMD查看器命令: {view_cmd}")
        
        # 创建在公共临时目录中
        temp_dir = os.path.join(os.path.dirname(workflow_dir), "temp")
        os.makedirs(temp_dir, exist_ok=True)
        try:
            import stat
            os.chmod(temp_dir, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        except Exception as e:
            logger.warning(f"设置临时目录权限失败: {e}")

        # 创建一个独立的脚本文件来运行VMD
        script_fd, script_path = tempfile.mkstemp(dir=temp_dir, suffix='.sh')
        with os.fdopen(script_fd, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write(f"cd {os.path.dirname(struct_path)}\n")
            # 使用VMD的完整路径
            if sys.platform == 'darwin':
                f.write(f"/Applications/VMD.app/Contents/MacOS/startup.command {os.path.basename(struct_path)} {os.path.basename(traj_path)}\n")
            else:
                f.write(f"vmd {os.path.basename(struct_path)} {os.path.basename(traj_path)}\n")
        
        # 使脚本可执行
        os.chmod(script_path, 0o755)
        
        # 在新终端窗口中运行脚本
        if sys.platform == 'darwin':
            # macOS上使用open命令在新终端中运行
            term_cmd = f"open -a Terminal {script_path}"
            subprocess.Popen(term_cmd, shell=True)
        else:
            # Linux上使用x-terminal-emulator
            term_cmd = f"x-terminal-emulator -e '{script_path}'"
            subprocess.Popen(term_cmd, shell=True)
        
        return {
            "success": True,
            "message": "成功加载GROMACS轨迹到VMD",
            "vmd_process_id": None,
            "trajectory_file": traj_path,
            "structure_file": struct_path,
            "image_path": image_path if generate_image else None,
            "method": "terminal-launch",
            "note": "VMD已在新终端窗口中启动，请查看桌面"
        }
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"加载GROMACS轨迹时发生异常: {error_msg}")
        
        return {
            "success": False,
            "error": f"加载GROMACS轨迹失败: {error_msg}"
        }