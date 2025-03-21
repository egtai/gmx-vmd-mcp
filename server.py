from mcp.server.fastmcp import FastMCP

# 创建MCP服务实例
mcp = FastMCP("GROMACS-VMD Service")

# 定义依赖
dependencies = []

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
    return """
MCP GROMACS-VMD Service 帮助

1. 创建工作流程：
   - 使用create_workflow工具创建新的工作流程

2. 轨迹分析：
   - 使用analyze_trajectory工具分析轨迹文件

3. VMD可视化：
   - 使用apply_vmd_template工具应用VMD模板

4. 工作流程管理：
   - 使用list_workflows工具列出所有工作流程
   - 使用get_workflow_status工具获取工作流程状态
   
更多信息请参考文档。
""" 