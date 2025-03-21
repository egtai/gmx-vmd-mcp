import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('mcp_gmx_vmd.log')
    ]
)

logger = logging.getLogger(__name__)

# 相对导入
from .service import MCPService
from .workflow_manager import WorkflowManager
from .gromacs import Context

async def run_test(service):
    """运行测试功能"""
    logger.info("运行测试模式")
    
    # 创建测试工作流程
    workflow_id = service.create_workflow(
        name="测试工作流程",
        description="用于测试MCP GMX-VMD服务的工作流程"
    )
    
    logger.info(f"创建工作流程: {workflow_id}")
    
    # 列出所有工作流程
    workflows = service.list_workflows()
    logger.info(f"工作流程列表:")
    for wf in workflows:
        logger.info(f"  - {wf.workflow_id}: {wf.name}")
    
    # 获取可用的VMD模板
    templates = service.get_available_templates()
    logger.info(f"可用的VMD模板:")
    for template in templates:
        logger.info(f"  - {template}")
    
    # 获取工作流程帮助信息
    help_info = service.get_workflow_help()
    logger.info(f"工作流程帮助信息:\n{help_info}")
    
    logger.info("测试完成")

async def main_async():
    parser = argparse.ArgumentParser(description="MCP GMX-VMD服务")
    parser.add_argument("--workspace", type=str, default=os.getcwd(), help="工作目录")
    parser.add_argument("--debug", action="store_true", help="启用调试模式")
    parser.add_argument("--test", action="store_true", help="运行测试模式")
    args = parser.parse_args()
    
    # 设置日志级别
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        
    logger.info(f"启动MCP GMX-VMD服务")
    logger.info(f"工作目录: {args.workspace}")
    
    # 创建工作目录
    workspace_path = Path(args.workspace)
    workspace_path.mkdir(parents=True, exist_ok=True)
    
    # 创建服务实例
    service = MCPService(workspace_path)
    
    if args.test:
        # 运行测试逻辑
        await run_test(service)
    else:
        logger.info("服务已启动,但当前仅支持测试模式。请使用--test参数启动测试模式")

def main():
    """主函数，用于启动服务"""
    asyncio.run(main_async())

if __name__ == "__main__":
    main() 