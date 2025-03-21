from mcp.server.fastmcp import FastMCP
import os
from pathlib import Path
from typing import Dict, List, Optional, Union

# 创建MCP服务实例
mcp = FastMCP("GROMACS-VMD Service")

# 定义依赖
dependencies = []

# 导入功能性模块（使用绝对导入）
from mcp_gmx_vmd.service import MCPService
from mcp_gmx_vmd.gromacs import Context, run_gromacs_command
from mcp_gmx_vmd.models import (
    AnalysisParams, AnalysisResult, AnalysisType,
    CompleteSimulationParams, SimulationConfig,
    SimulationStatus, SimulationStep,
    SimulationParams
)
from mcp_gmx_vmd.workflow_manager import WorkflowMetadata

# 创建服务实例
service = MCPService(Path(os.getcwd()))

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

@mcp.resource("gmx-vmd://workflows/create")
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

@mcp.resource("gmx-vmd://workflows/get")
async def get_workflow(workflow_id: str) -> Dict:
    """获取工作流程详情"""
    workflow = service.get_workflow(workflow_id)
    if workflow:
        return workflow.to_dict()
    return {"error": "工作流程不存在", "workflow_id": workflow_id}

@mcp.resource("gmx-vmd://workflows/update")
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

@mcp.resource("gmx-vmd://workflows/delete")
async def delete_workflow(workflow_id: str) -> Dict:
    """删除工作流程"""
    success = service.delete_workflow(workflow_id)
    return {"success": success, "workflow_id": workflow_id}

@mcp.resource("gmx-vmd://workflows/status")
async def get_workflow_status(workflow_id: str) -> Dict:
    """获取工作流程状态"""
    status = service.get_workflow_status(workflow_id)
    if status:
        return status.dict()
    return {"error": "无法获取工作流程状态", "workflow_id": workflow_id}

@mcp.resource("gmx-vmd://workflows/logs")
async def get_workflow_logs(workflow_id: str) -> Dict:
    """获取工作流程日志"""
    logs = service.get_workflow_logs(workflow_id)
    return {"logs": logs, "workflow_id": workflow_id}

@mcp.resource("gmx-vmd://workflows/checkpoints")
async def get_workflow_checkpoints(workflow_id: str) -> Dict:
    """获取工作流程检查点"""
    checkpoints = service.get_workflow_checkpoints(workflow_id)
    result = {}
    for step, files in checkpoints.items():
        result[step.value] = files
    return {"checkpoints": result, "workflow_id": workflow_id}

@mcp.resource("gmx-vmd://workflows/export")
async def export_workflow(workflow_id: str, output_file: str) -> Dict:
    """导出工作流程"""
    success = service.export_workflow(workflow_id, output_file)
    return {"success": success, "workflow_id": workflow_id, "output_file": output_file}

@mcp.resource("gmx-vmd://workflows/import")
async def import_workflow(input_file: str) -> Dict:
    """导入工作流程"""
    workflow_id = service.import_workflow(input_file)
    if workflow_id:
        return {"success": True, "workflow_id": workflow_id}
    return {"success": False, "error": "导入工作流程失败"}

#====================
# 模拟参数管理
#====================

@mcp.resource("gmx-vmd://parameters/validate")
async def validate_parameters(params: Dict) -> Dict:
    """验证模拟参数"""
    params_obj = CompleteSimulationParams(**params)
    warnings = service.validate_parameters(params_obj)
    return {"warnings": warnings, "valid": not any(warnings.values())}

@mcp.resource("gmx-vmd://parameters/optimize")
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

@mcp.resource("gmx-vmd://analysis/trajectory")
async def analyze_trajectory(workflow_id: str, params: Dict) -> Dict:
    """分析轨迹"""
    analysis_params = AnalysisParams(**params)
    result = await service.analyze_trajectory(workflow_id, analysis_params)
    if result:
        return {
            "success": True,
            "result": result.dict(),
            "workflow_id": workflow_id
        }
    return {"success": False, "error": "轨迹分析失败", "workflow_id": workflow_id}

@mcp.resource("gmx-vmd://visualization/apply-template")
async def apply_vmd_template(workflow_id: str, template_name: str, params: Optional[Dict] = None) -> Dict:
    """应用VMD模板"""
    success = service.apply_vmd_template(workflow_id, template_name, params)
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

@mcp.resource("gmx-vmd://gromacs/execute")
async def execute_gromacs_command(workflow_id: str, command: str, args: List[str] = None, input_data: Optional[str] = None) -> Dict:
    """执行GROMACS命令"""
    workflow_dir = service.workflow_manager.get_workflow_directory(workflow_id)
    if not workflow_dir:
        return {"success": False, "error": "工作流程目录不存在", "workflow_id": workflow_id}
    
    ctx = Context(working_dir=workflow_dir)
    result = await run_gromacs_command(ctx, command, args or [], input_data)
    return {
        "success": result.success,
        "output": result.stdout,
        "error": result.stderr,
        "workflow_id": workflow_id,
        "command": command
    } 