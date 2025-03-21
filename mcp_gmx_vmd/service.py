import asyncio
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple
import logging
import json
import fnmatch

# 完全移除对mcp的依赖
from pydantic import BaseModel

# 导入新的gromacs模块
from .gromacs import GromacsCmdResult, Context, run_gromacs_command

# 暂时注释掉vmd_manager导入，如果需要可以取消注释
# from .vmd import vmd_manager, VMDInstance, VMDScriptResult
from .models import (
    AnalysisParams, AnalysisResult, AnalysisType,
    CompleteSimulationParams, SimulationConfig,
    SimulationStatus, SimulationStep
)
from .analysis import analyze_trajectory
from .vmd_templates import VMDTemplates, VISUALIZATION_STYLES
from .simulation import SimulationWorkflow
from .workflow_manager import WorkflowManager, WorkflowMetadata
from .validator import ParameterValidator, ParameterOptimizer
from .vmd_manager import VMDManager

logger = logging.getLogger(__name__)

class SimulationParams(BaseModel):
    """分子动力学模拟参数"""
    structure_file: str
    topology_file: Optional[str] = None
    force_field: str = "amber99sb-ildn"
    water_model: str = "tip3p"
    box_type: str = "cubic"
    box_distance: float = 1.0
    ions_concentration: float = 0.15

# 保留MCPService类
class MCPService:
    """MCP服务主类"""
    
    def __init__(self, workspace_root: Union[str, Path], vmd_path: str = None):
        self.workspace_root = Path(workspace_root)
        self.workflow_manager = WorkflowManager(workspace_root)
        self.vmd_manager = VMDManager(vmd_path)
        # 添加结构文件搜索目录配置
        self.structure_search_paths = []
        
    def add_structure_search_path(self, path: Union[str, Path]):
        """添加结构文件搜索路径"""
        path = Path(path)
        if path.is_dir() and path not in self.structure_search_paths:
            self.structure_search_paths.append(path)
            
    def remove_structure_search_path(self, path: Union[str, Path]):
        """移除结构文件搜索路径"""
        path = Path(path)
        if path in self.structure_search_paths:
            self.structure_search_paths.remove(path)
            
    def get_structure_search_paths(self) -> List[Path]:
        """获取所有结构文件搜索路径"""
        return self.structure_search_paths
        
    def find_structure_files(self, pattern: str) -> List[Dict]:
        """查找匹配的结构文件
        
        Args:
            pattern: 搜索模式，可以是文件名、部分路径或结构名称
            
        Returns:
            List[Dict]: 匹配的结构文件列表，每个文件包含路径和描述信息
        """
        results = []
        # 支持的结构文件扩展名
        extensions = ['.pdb', '.gro', '.xyz', '.mol2']
        
        # 如果没有配置搜索路径，使用工作空间根目录
        search_paths = self.structure_search_paths or [self.workspace_root]
        
        for search_path in search_paths:
            for root, _, files in os.walk(search_path):
                for filename in files:
                    # 检查文件扩展名
                    if any(filename.lower().endswith(ext) for ext in extensions):
                        # 检查是否匹配搜索模式
                        if (fnmatch.fnmatch(filename.lower(), f'*{pattern.lower()}*') or
                            fnmatch.fnmatch(str(Path(root) / filename).lower(), f'*{pattern.lower()}*')):
                            file_path = Path(root) / filename
                            # 获取相对于搜索路径的路径
                            try:
                                rel_path = file_path.relative_to(search_path)
                            except ValueError:
                                rel_path = file_path
                            
                            results.append({
                                'path': str(file_path),
                                'filename': filename,
                                'relative_path': str(rel_path),
                                'type': file_path.suffix[1:].upper(),
                                'size': file_path.stat().st_size,
                                'modified': file_path.stat().st_mtime
                            })
                            
        return sorted(results, key=lambda x: x['modified'], reverse=True)
        
    def create_workflow(
        self,
        name: str,
        description: Optional[str] = None,
        params: Optional[CompleteSimulationParams] = None
    ) -> str:
        """创建新的工作流程"""
        # 验证参数
        if params:
            warnings = ParameterValidator.validate_complete_params(params)
            if any(warnings.values()):
                logger.warning(f"参数验证警告: {warnings}")
                
        return self.workflow_manager.create_workflow(name, description, params)
        
    def get_workflow(self, workflow_id: str) -> Optional[WorkflowMetadata]:
        """获取工作流程信息"""
        return self.workflow_manager.get_workflow(workflow_id)
        
    def list_workflows(self) -> List[WorkflowMetadata]:
        """列出所有工作流程"""
        return self.workflow_manager.list_workflows()
        
    def update_workflow(
        self,
        workflow_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[SimulationStatus] = None,
        params: Optional[CompleteSimulationParams] = None
    ) -> bool:
        """更新工作流程信息"""
        if params:
            warnings = ParameterValidator.validate_complete_params(params)
            if any(warnings.values()):
                logger.warning(f"参数验证警告: {warnings}")
                
        return self.workflow_manager.update_workflow(
            workflow_id, name, description, status, params
        )
        
    def delete_workflow(self, workflow_id: str) -> bool:
        """删除工作流程"""
        return self.workflow_manager.delete_workflow(workflow_id)
        
    def get_workflow_status(self, workflow_id: str) -> Optional[SimulationStatus]:
        """获取工作流程状态"""
        workflow = self.get_workflow(workflow_id)
        return workflow.status if workflow else None
        
    def get_workflow_logs(self, workflow_id: str) -> List[str]:
        """获取工作流程日志"""
        return self.workflow_manager.get_workflow_logs(workflow_id)
        
    def get_workflow_checkpoints(self, workflow_id: str) -> Dict[SimulationStep, List[str]]:
        """获取工作流程检查点"""
        return self.workflow_manager.get_workflow_checkpoints(workflow_id)
        
    def validate_parameters(self, params: CompleteSimulationParams) -> Dict[str, List[str]]:
        """验证模拟参数"""
        return ParameterValidator.validate_complete_params(params)
        
    def optimize_parameters(self, params: CompleteSimulationParams) -> Tuple[CompleteSimulationParams, Dict[str, List[str]]]:
        """优化模拟参数"""
        return ParameterOptimizer.optimize_complete_params(params)
        
    def export_workflow(self, workflow_id: str, output_file: Union[str, Path]) -> bool:
        """导出工作流程"""
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            return False
            
        try:
            with open(output_file, 'w') as f:
                json.dump(workflow.to_dict(), f, indent=2)
            return True
        except Exception as e:
            logger.error(f"导出工作流程失败: {str(e)}")
            return False
            
    def import_workflow(self, input_file: Union[str, Path]) -> Optional[str]:
        """导入工作流程"""
        try:
            with open(input_file, 'r') as f:
                data = json.load(f)
            workflow = WorkflowMetadata.from_dict(data)
            
            # 创建新的工作流程
            return self.create_workflow(
                name=workflow.name,
                description=workflow.description,
                params=workflow.params
            )
        except Exception as e:
            logger.error(f"导入工作流程失败: {str(e)}")
            return None
            
    async def analyze_trajectory(
        self,
        workflow_id: str,
        params: AnalysisParams,
        custom_workflow_dir: Optional[Path] = None
    ) -> Optional[AnalysisResult]:
        """分析轨迹"""
        logger.info(f"Service.analyze_trajectory调用: workflow_id={workflow_id}, params={params}")
        
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            logger.error(f"工作流程不存在: {workflow_id}")
            return None
            
        # 获取工作目录，优先使用自定义目录
        workflow_dir = custom_workflow_dir if custom_workflow_dir else self.workflow_manager.get_workflow_directory(workflow_id)
        logger.info(f"工作目录: {workflow_dir}，自定义目录: {custom_workflow_dir is not None}")
        if not workflow_dir:
            logger.error(f"无法获取工作流程目录: {workflow_id}")
            return None
            
        try:
            # 检查文件路径
            trajectory_file = params.trajectory_file
            structure_file = params.structure_file
            
            # 构建绝对路径
            if not os.path.isabs(trajectory_file):
                abs_traj_path = workflow_dir / trajectory_file
            else:
                abs_traj_path = Path(trajectory_file)
                
            if not os.path.isabs(structure_file):
                abs_struct_path = workflow_dir / structure_file
            else:
                abs_struct_path = Path(structure_file)
            
            # 验证文件存在
            if not os.path.exists(abs_traj_path):
                logger.error(f"轨迹文件不存在: {abs_traj_path}")
                return None
                
            if not os.path.exists(abs_struct_path):
                logger.error(f"结构文件不存在: {abs_struct_path}")
                return None
            
            logger.info(f"文件验证通过，创建分析上下文")
            
            # 创建上下文
            ctx = Context(working_dir=workflow_dir)
            
            # 调用分析函数
            logger.info(f"开始执行分析: {params.analysis_type}")
            result = await analyze_trajectory(ctx, params)
            logger.info(f"分析完成: {params.analysis_type}")
            
            return result
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"轨迹分析失败: {str(e)}")
            logger.error(f"异常堆栈: {tb}")
            return None
            
    def apply_vmd_template(
        self,
        workflow_id: str,
        template_name: str,
        params: Dict = None,
        custom_workflow_dir: Optional[Path] = None
    ) -> bool:
        """应用VMD模板"""
        # 优先使用自定义工作流目录
        workflow_dir = custom_workflow_dir if custom_workflow_dir else self.workflow_manager.get_workflow_directory(workflow_id)
        if not workflow_dir:
            logger.error(f"无法获取工作流目录: {workflow_id}")
            return False
            
        try:
            template = getattr(VMDTemplates, template_name)
            script = template(params) if params else template()
            return self.vmd_manager.execute_script(script)
        except Exception as e:
            logger.error(f"应用VMD模板失败: {str(e)}")
            return False
            
    def get_available_templates(self) -> List[str]:
        """获取可用的VMD模板"""
        return [name for name in dir(VMDTemplates) 
                if not name.startswith('_') and callable(getattr(VMDTemplates, name))]
                
    def get_workflow_help(self) -> str:
        """获取工作流程帮助信息"""
        return """
分子动力学模拟工作流程:

1. 系统准备
   - 准备蛋白质结构文件 (PDB/GRO格式)
   - 选择力场和水模型
   - 设置模拟盒子和溶剂化

2. 能量最小化
   - 优化初始结构
   - 消除不合理的接触

3. 平衡模拟
   - NVT系综平衡(温度)
   - NPT系综平衡(压力)

4. 生产模拟
   - 进行长时间模拟
   - 收集轨迹数据

5. 轨迹分析
   - RMSD/RMSF分析
   - 氢键分析
   - 二级结构分析
   - 密度分析等

6. 可视化
   - 使用VMD模板
   - 自定义可视化设置
   - 生成动画

注意事项:
1. 确保输入文件格式正确
2. 注意参数设置的合理性
3. 定期保存检查点
4. 监控模拟过程
5. 备份重要数据
""" 

    async def prepare_simulation(
        self,
        workflow_id: str,
        structure_file: str,
        force_field: str = "amber99sb-ildn",
        simulation_params: Optional[Dict] = None,
        custom_workflow_dir: Optional[Path] = None
    ) -> Dict:
        """准备分子动力学模拟
        
        Args:
            workflow_id: 工作流程ID
            structure_file: 结构文件路径
            force_field: 力场名称
            simulation_params: 模拟参数字典
            custom_workflow_dir: 自定义工作流目录（可选）
            
        Returns:
            Dict: 包含准备好的输入文件和命令的字典
        """
        logger.info(f"开始准备模拟，参数: workflow_id={workflow_id}, structure_file={structure_file}, force_field={force_field}")
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            logger.error(f"工作流程不存在: {workflow_id}")
            return {
                "success": False,
                "error": f"工作流程不存在: {workflow_id}"
            }
            
        # 获取工作目录，优先使用自定义目录
        workflow_dir = custom_workflow_dir if custom_workflow_dir else self.workflow_manager.get_workflow_directory(workflow_id)
        logger.info(f"工作目录: {workflow_dir}，自定义目录: {custom_workflow_dir is not None}")
        if not workflow_dir:
            logger.error(f"无法获取工作流程目录: {workflow_id}")
            return {
                "success": False,
                "error": f"无法获取工作流程目录: {workflow_id}"
            }
            
        # 处理结构文件路径
        structure_path = Path(structure_file)
        if not structure_path.is_absolute():
            structure_path = workflow_dir / structure_path
            
        if not structure_path.exists():
            return {
                "success": False,
                "error": f"结构文件不存在: {structure_path}"
            }
            
        # 创建上下文
        ctx = Context(working_dir=workflow_dir)
        
        # 默认参数
        default_params = {
            "water_model": "tip3p",
            "box_type": "cubic",
            "box_distance": 1.0,
            "ions_concentration": 0.15,
            "minimization": {
                "max_iterations": 50000,
                "energy_step": 10,
                "max_force": 1000.0
            },
            "equilibration": {
                "nvt": {
                    "temperature": 300,
                    "time_step": 0.002,
                    "time_length": 0.1
                },
                "npt": {
                    "temperature": 300,
                    "pressure": 1.0,
                    "time_step": 0.002,
                    "time_length": 0.1
                }
            },
            "production": {
                "temperature": 300,
                "pressure": 1.0,
                "time_step": 0.002,
                "time_length": 10.0
            }
        }
        
        # 合并用户提供的参数
        if simulation_params:
            # 递归合并字典
            def merge_dicts(d1, d2):
                for k, v in d2.items():
                    if k in d1 and isinstance(v, dict) and isinstance(d1[k], dict):
                        merge_dicts(d1[k], v)
                    else:
                        d1[k] = v
            
            merge_dicts(default_params, simulation_params)
        
        try:
            # 创建必要的目录
            for subdir in ["em", "nvt", "npt", "md", "analysis"]:
                (workflow_dir / subdir).mkdir(exist_ok=True)
            
            # 复制结构文件到工作目录
            target_structure = workflow_dir / structure_path.name
            import shutil
            shutil.copy2(structure_path, target_structure)
            
            # 生成拓扑文件
            logger.info(f"为 {structure_path.name} 生成拓扑文件")
            result = await run_gromacs_command(
                ctx,
                "pdb2gmx",
                [
                    "-f", structure_path.name,
                    "-o", "processed.gro",
                    "-water", default_params["water_model"],
                    "-ff", force_field,
                    "-ignh"  # 忽略氢原子
                ]
            )
            
            if not result.success:
                return {
                    "success": False,
                    "error": f"生成拓扑文件失败: {result.error}",
                    "output": result.output
                }
                
            # 定义模拟盒子
            logger.info("定义模拟盒子")
            result = await run_gromacs_command(
                ctx,
                "editconf",
                [
                    "-f", "processed.gro",
                    "-o", "box.gro",
                    "-c",  # 居中
                    "-d", str(default_params["box_distance"]),  # 距离边界
                    "-bt", default_params["box_type"]  # 盒子类型
                ]
            )
            
            if not result.success:
                return {
                    "success": False,
                    "error": f"定义模拟盒子失败: {result.error}",
                    "output": result.output
                }
                
            # 溶剂化系统
            logger.info("溶剂化系统")
            result = await run_gromacs_command(
                ctx,
                "solvate",
                [
                    "-cp", "box.gro",
                    "-cs", "spc216.gro",  # 水模型
                    "-o", "solv.gro",
                    "-p", "topol.top"
                ]
            )
            
            if not result.success:
                return {
                    "success": False,
                    "error": f"溶剂化系统失败: {result.error}",
                    "output": result.output
                }
                
            # 添加离子
            logger.info("添加离子")
            
            # 创建离子添加的mdp文件
            ions_mdp = workflow_dir / "ions.mdp"
            with open(ions_mdp, "w") as f:
                f.write("; 离子化的mdp参数\n")
                f.write("integrator = steep\n")
                f.write("emtol = 1000.0\n")
                f.write("emstep = 0.01\n")
                f.write("nsteps = 50000\n")
                
            # 生成离子化的tpr文件
            result = await run_gromacs_command(
                ctx,
                "grompp",
                [
                    "-f", "ions.mdp",
                    "-c", "solv.gro",
                    "-p", "topol.top",
                    "-o", "ions.tpr"
                ]
            )
            
            if not result.success:
                return {
                    "success": False,
                    "error": f"准备离子化失败: {result.error}",
                    "output": result.output
                }
                
            # 添加离子
            result = await run_gromacs_command(
                ctx,
                "genion",
                [
                    "-s", "ions.tpr",
                    "-o", "solv_ions.gro",
                    "-p", "topol.top",
                    "-pname", "NA",
                    "-nname", "CL",
                    "-neutral",
                    "-conc", str(default_params["ions_concentration"])
                ],
                input_data="SOL"  # 替换水分子
            )
            
            if not result.success:
                return {
                    "success": False,
                    "error": f"添加离子失败: {result.error}",
                    "output": result.output
                }
                
            # 创建能量最小化目录和mdp文件
            em_dir = workflow_dir / "em"
            em_mdp = em_dir / "em.mdp"
            
            # 写入能量最小化mdp文件
            with open(em_mdp, "w") as f:
                f.write("; 能量最小化参数\n")
                f.write("integrator = steep\n")
                f.write(f"emtol = {default_params['minimization']['max_force']}\n")
                f.write("emstep = 0.01\n")
                f.write(f"nsteps = {default_params['minimization']['max_iterations']}\n")
                f.write(f"nstxout = {default_params['minimization']['energy_step']}\n")
                f.write("cutoff-scheme = Verlet\n")
                f.write("coulombtype = PME\n")
                f.write("rcoulomb = 1.0\n")
                f.write("rvdw = 1.0\n")
                f.write("pbc = xyz\n")
                
            # 创建NVT平衡mdp文件
            nvt_dir = workflow_dir / "nvt"
            nvt_mdp = nvt_dir / "nvt.mdp"
            
            with open(nvt_mdp, "w") as f:
                f.write("; NVT平衡参数\n")
                f.write("integrator = md\n")
                f.write(f"dt = {default_params['equilibration']['nvt']['time_step']}\n")
                f.write(f"nsteps = {int(default_params['equilibration']['nvt']['time_length'] / default_params['equilibration']['nvt']['time_step'])}\n")
                f.write("cutoff-scheme = Verlet\n")
                f.write("coulombtype = PME\n")
                f.write("rcoulomb = 1.0\n")
                f.write("rvdw = 1.0\n")
                f.write("pbc = xyz\n")
                f.write("tcoupl = V-rescale\n")
                f.write("tc-grps = Protein Non-Protein\n")
                f.write(f"tau_t = 0.1 0.1\n")
                f.write(f"ref_t = {default_params['equilibration']['nvt']['temperature']} {default_params['equilibration']['nvt']['temperature']}\n")
                f.write("constraints = h-bonds\n")
                f.write("constraint_algorithm = LINCS\n")
                
                # 输出控制 - 设置1ps间隔的xtc轨迹输出
                time_step = default_params['equilibration']['nvt']['time_step']  # ps
                steps_per_ps = int(1.0 / time_step)  # 每ps的步数
                f.write(f"nstxout = {steps_per_ps * 10}\n")          # 完整坐标（每10ps）
                f.write(f"nstvout = {steps_per_ps * 10}\n")          # 速度（每10ps）
                f.write(f"nstfout = {steps_per_ps * 10}\n")          # 力（每10ps）
                f.write(f"nstxtcout = {steps_per_ps}\n")             # 压缩轨迹（每1ps）
                f.write("xtc_precision = 1000\n")                    # xtc精度
                f.write(f"nstlog = {steps_per_ps}\n")                # 日志输出（每1ps）
                f.write(f"nstenergy = {steps_per_ps}\n")             # 能量输出（每1ps）
                
            # 创建NPT平衡mdp文件
            npt_dir = workflow_dir / "npt"
            npt_mdp = npt_dir / "npt.mdp"
            
            with open(npt_mdp, "w") as f:
                f.write("; NPT平衡参数\n")
                f.write("integrator = md\n")
                f.write(f"dt = {default_params['equilibration']['npt']['time_step']}\n")
                f.write(f"nsteps = {int(default_params['equilibration']['npt']['time_length'] / default_params['equilibration']['npt']['time_step'])}\n")
                f.write("cutoff-scheme = Verlet\n")
                f.write("coulombtype = PME\n")
                f.write("rcoulomb = 1.0\n")
                f.write("rvdw = 1.0\n")
                f.write("pbc = xyz\n")
                f.write("tcoupl = V-rescale\n")
                f.write("tc-grps = Protein Non-Protein\n")
                f.write(f"tau_t = 0.1 0.1\n")
                f.write(f"ref_t = {default_params['equilibration']['npt']['temperature']} {default_params['equilibration']['npt']['temperature']}\n")
                f.write("pcoupl = Parrinello-Rahman\n")
                f.write("pcoupltype = isotropic\n")
                f.write(f"ref_p = {default_params['equilibration']['npt']['pressure']}\n")
                f.write("tau_p = 2.0\n")
                f.write("compressibility = 4.5e-5\n")
                f.write("constraints = h-bonds\n")
                f.write("constraint_algorithm = LINCS\n")
                
                # 输出控制 - 设置1ps间隔的xtc轨迹输出
                time_step = default_params['equilibration']['npt']['time_step']  # ps
                steps_per_ps = int(1.0 / time_step)  # 每ps的步数
                f.write(f"nstxout = {steps_per_ps * 10}\n")          # 完整坐标（每10ps）
                f.write(f"nstvout = {steps_per_ps * 10}\n")          # 速度（每10ps）
                f.write(f"nstfout = {steps_per_ps * 10}\n")          # 力（每10ps）
                f.write(f"nstxtcout = {steps_per_ps}\n")             # 压缩轨迹（每1ps）
                f.write("xtc_precision = 1000\n")                    # xtc精度
                f.write(f"nstlog = {steps_per_ps}\n")                # 日志输出（每1ps）
                f.write(f"nstenergy = {steps_per_ps}\n")             # 能量输出（每1ps）
                
            # 创建生产模拟mdp文件
            md_dir = workflow_dir / "md"
            md_mdp = md_dir / "md.mdp"
            
            with open(md_mdp, "w") as f:
                f.write("; 生产模拟参数\n")
                f.write("integrator = md\n")
                f.write(f"dt = {default_params['production']['time_step']}\n")
                f.write(f"nsteps = {int(default_params['production']['time_length'] / default_params['production']['time_step'])}\n")
                f.write("cutoff-scheme = Verlet\n")
                f.write("coulombtype = PME\n")
                f.write("rcoulomb = 1.0\n")
                f.write("rvdw = 1.0\n")
                f.write("pbc = xyz\n")
                f.write("tcoupl = V-rescale\n")
                f.write("tc-grps = Protein Non-Protein\n")
                f.write(f"tau_t = 0.1 0.1\n")
                f.write(f"ref_t = {default_params['production']['temperature']} {default_params['production']['temperature']}\n")
                f.write("pcoupl = Parrinello-Rahman\n")
                f.write("pcoupltype = isotropic\n")
                f.write(f"ref_p = {default_params['production']['pressure']}\n")
                f.write("tau_p = 2.0\n")
                f.write("compressibility = 4.5e-5\n")
                f.write("constraints = h-bonds\n")
                f.write("constraint_algorithm = LINCS\n")
                
                # 输出控制 - 设置1ps间隔的xtc轨迹输出
                time_step = default_params['production']['time_step']  # ps
                steps_per_ps = int(1.0 / time_step)  # 每ps的步数
                f.write(f"nstxout = {steps_per_ps * 10}\n")          # 完整坐标（每10ps）
                f.write(f"nstvout = {steps_per_ps * 10}\n")          # 速度（每10ps）
                f.write(f"nstfout = {steps_per_ps * 10}\n")          # 力（每10ps）
                f.write(f"nstxtcout = {steps_per_ps}\n")             # 压缩轨迹（每1ps）
                f.write("xtc_precision = 1000\n")                    # xtc精度
                f.write(f"nstlog = {steps_per_ps}\n")                # 日志输出（每1ps）
                f.write(f"nstenergy = {steps_per_ps}\n")             # 能量输出（每1ps）
                
            # 更新工作流程状态
            logger.info(f"更新工作流程状态: {workflow_id}, 步骤: {SimulationStep.SYSTEM_PREPARATION}")
            try:
                self.update_workflow(
                    workflow_id,
                    status=SimulationStatus(
                        current_step=SimulationStep.SYSTEM_PREPARATION,
                        completed_steps=[SimulationStep.SYSTEM_PREPARATION]
                    )
                )
                logger.info("工作流程状态更新成功")
            except Exception as e:
                logger.error(f"更新工作流程状态失败: {str(e)}")
                # 继续执行，不要因为状态更新失败而中断整个流程
            
            # 返回成功结果和下一步命令
            return {
                "success": True,
                "message": "模拟准备完成",
                "workflow_id": workflow_id,
                "files": {
                    "structure": str(target_structure),
                    "topology": str(workflow_dir / "topol.top"),
                    "solvated": str(workflow_dir / "solv_ions.gro"),
                    "em_mdp": str(em_mdp),
                    "nvt_mdp": str(nvt_mdp),
                    "npt_mdp": str(npt_mdp),
                    "md_mdp": str(md_mdp)
                },
                "next_commands": [
                    {
                        "step": "能量最小化准备",
                        "command": "grompp",
                        "args": [
                            "-f", str(em_mdp),
                            "-c", str(workflow_dir / "solv_ions.gro"),
                            "-p", str(workflow_dir / "topol.top"),
                            "-o", str(em_dir / "em.tpr")
                        ]
                    },
                    {
                        "step": "运行能量最小化",
                        "command": "mdrun",
                        "args": [
                            "-v",
                            "-s", str(em_dir / "em.tpr"),
                            "-deffnm", str(em_dir / "em")
                        ]
                    },
                    {
                        "step": "NVT平衡准备",
                        "command": "grompp",
                        "args": [
                            "-f", str(nvt_mdp),
                            "-c", str(em_dir / "em.gro"),
                            "-r", str(em_dir / "em.gro"),
                            "-p", str(workflow_dir / "topol.top"),
                            "-o", str(nvt_dir / "nvt.tpr")
                        ]
                    },
                    {
                        "step": "运行NVT平衡",
                        "command": "mdrun",
                        "args": [
                            "-v",
                            "-s", str(nvt_dir / "nvt.tpr"),
                            "-deffnm", str(nvt_dir / "nvt")
                        ]
                    },
                    {
                        "step": "NPT平衡准备",
                        "command": "grompp",
                        "args": [
                            "-f", str(npt_mdp),
                            "-c", str(nvt_dir / "nvt.gro"),
                            "-r", str(nvt_dir / "nvt.gro"),
                            "-p", str(workflow_dir / "topol.top"),
                            "-t", str(nvt_dir / "nvt.cpt"),
                            "-o", str(npt_dir / "npt.tpr")
                        ]
                    },
                    {
                        "step": "运行NPT平衡",
                        "command": "mdrun",
                        "args": [
                            "-v",
                            "-s", str(npt_dir / "npt.tpr"),
                            "-deffnm", str(npt_dir / "npt")
                        ]
                    }
                ],
                "next_commands_text": [
                    "# 从工作目录执行:",
                    f"cd {workflow_dir}",
                    "",
                    "# 1. 准备能量最小化:",
                    "gmx grompp -f em/em.mdp -c solv_ions.gro -p topol.top -o em/em.tpr",
                    "",
                    "# 2. 运行能量最小化:",
                    "gmx mdrun -v -s em/em.tpr -deffnm em/em",
                    "",
                    "# 3. 准备NVT平衡:",
                    "gmx grompp -f nvt/nvt.mdp -c em/em.gro -r em/em.gro -p topol.top -o nvt/nvt.tpr",
                    "",
                    "# 4. 运行NVT平衡:",
                    "gmx mdrun -v -s nvt/nvt.tpr -deffnm nvt/nvt",
                    "",
                    "# 5. 准备NPT平衡:",
                    "gmx grompp -f npt/npt.mdp -c nvt/nvt.gro -r nvt/nvt.gro -t nvt/nvt.cpt -p topol.top -o npt/npt.tpr",
                    "",
                    "# 6. 运行NPT平衡:",
                    "gmx mdrun -v -s npt/npt.tpr -deffnm npt/npt",
                    "",
                    "# 注意: 如果您使用的是GROMACS 5或更高版本，以上命令已经包含'gmx'前缀",
                    "# 如果使用的是旧版本GROMACS，请将命令中的'gmx'替换为相应的命令名称，例如:",
                    "# grompp -f em/em.mdp -c solv_ions.gro -p topol.top -o em/em.tpr",
                    "# mdrun -v -s em/em.tpr -deffnm em/em"
                ]
            }
            
        except Exception as e:
            logger.error(f"准备模拟失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "workflow_id": workflow_id
            } 