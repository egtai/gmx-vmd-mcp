import asyncio
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from .models import (
    CompleteSimulationParams,
    EnergyMinimizationParams,
    EquilibrationParams,
    ProductionParams,
    SimulationStatus,
    SimulationStep
)
from .service import run_gromacs_command, Context

# 设置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimulationError(Exception):
    """模拟过程中的错误"""
    pass

class SimulationWorkflow:
    def __init__(self, params: CompleteSimulationParams):
        self.params = params
        self.work_dir = Path.cwd()
        self.log_dir = self.work_dir / "logs"
        self.log_dir.mkdir(exist_ok=True)
        self.status = SimulationStatus()
        self._setup_logging()
        
    def _setup_logging(self):
        """设置日志记录"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.log_dir / f"simulation_{timestamp}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        logger.addHandler(file_handler)
        
    async def _check_output_files(self, step: SimulationStep, required_files: List[str]) -> bool:
        """检查输出文件是否存在且有效"""
        for file in required_files:
            file_path = self.work_dir / file
            if not file_path.exists():
                logger.error(f"{step}: 缺少必要的输出文件 {file}")
                return False
            if file_path.stat().st_size == 0:
                logger.error(f"{step}: 输出文件 {file} 为空")
                return False
        return True
        
    async def _validate_energy(self, step: SimulationStep, energy_file: str) -> bool:
        """验证能量是否合理"""
        try:
            cmd_result = await run_gromacs_command(None, "energy", [
                "-f", energy_file,
                "-o", f"{step.value}_energy.xvg"
            ])
            
            if cmd_result.return_code != 0:
                logger.error(f"{step}: 能量分析失败")
                return False
                
            # TODO: 添加具体的能量值检查逻辑
            return True
            
        except Exception as e:
            logger.error(f"{step}: 能量验证时发生错误 - {str(e)}")
            return False
            
    async def _monitor_progress(self, step: SimulationStep, log_file: str):
        """监控模拟进度"""
        try:
            while True:
                if not Path(log_file).exists():
                    await asyncio.sleep(1)
                    continue
                    
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    
                if lines:
                    last_line = lines[-1]
                    if "Finished mdrun" in last_line:
                        logger.info(f"{step}: 模拟完成")
                        break
                    elif "Fatal error" in last_line:
                        logger.error(f"{step}: 模拟出错 - {last_line}")
                        raise SimulationError(f"{step} 模拟失败")
                        
                await asyncio.sleep(5)
                
        except Exception as e:
            logger.error(f"{step}: 进度监控时发生错误 - {str(e)}")
            raise
            
    async def run_minimization(self, ctx: Context) -> Dict[str, str]:
        """运行能量最小化"""
        step = SimulationStep.MINIMIZATION
        self.status.current_step = step
        logger.info(f"开始{step}")
        
        try:
            # 创建最小化的mdp文件
            em_mdp = self.work_dir / "em.mdp"
            self._create_em_mdp(em_mdp, self.params.minimization)
            
            # 生成tpr文件
            grompp_result = await run_gromacs_command(ctx, "grompp", [
                "-f", str(em_mdp),
                "-c", "solvated.gro",
                "-p", "topol.top",
                "-o", "em.tpr"
            ])
            
            if grompp_result.return_code != 0:
                raise SimulationError(f"生成TPR文件失败: {grompp_result.stderr}")
            
            # 运行能量最小化
            mdrun_result = await run_gromacs_command(ctx, "mdrun", [
                "-v",
                "-deffnm", "em"
            ])
            
            # 监控进度
            await self._monitor_progress(step, "em.log")
            
            # 验证输出
            required_files = ["em.gro", "em.edr", "em.log"]
            if not await self._check_output_files(step, required_files):
                raise SimulationError(f"{step} 输出文件验证失败")
                
            # 验证能量
            if not await self._validate_energy(step, "em.edr"):
                raise SimulationError(f"{step} 能量验证失败")
            
            self.status.completed_steps.append(step)
            logger.info(f"{step} 完成")
            
            return {
                "grompp": grompp_result.dict(),
                "mdrun": mdrun_result.dict(),
                "status": "success"
            }
            
        except Exception as e:
            self.status.errors[step] = str(e)
            logger.error(f"{step} 失败: {str(e)}")
            raise
        
    async def run_nvt_equilibration(self, ctx: Context) -> Dict[str, str]:
        """运行NVT平衡"""
        step = SimulationStep.NVT_EQUILIBRATION
        self.status.current_step = step
        logger.info(f"开始{step}")
        
        try:
            # 检查前一步是否完成
            if SimulationStep.MINIMIZATION not in self.status.completed_steps:
                raise SimulationError("必须先完成能量最小化")
            
            # 创建NVT平衡的mdp文件
            nvt_mdp = self.work_dir / "nvt.mdp"
            self._create_nvt_mdp(nvt_mdp, self.params.equilibration)
            
            # 生成tpr文件
            grompp_result = await run_gromacs_command(ctx, "grompp", [
                "-f", str(nvt_mdp),
                "-c", "em.gro",
                "-r", "em.gro",
                "-p", "topol.top",
                "-o", "nvt.tpr"
            ])
            
            if grompp_result.return_code != 0:
                raise SimulationError(f"生成TPR文件失败: {grompp_result.stderr}")
            
            # 运行NVT平衡
            mdrun_result = await run_gromacs_command(ctx, "mdrun", [
                "-v",
                "-deffnm", "nvt"
            ])
            
            # 监控进度
            await self._monitor_progress(step, "nvt.log")
            
            # 验证输出
            required_files = ["nvt.gro", "nvt.edr", "nvt.log", "nvt.cpt"]
            if not await self._check_output_files(step, required_files):
                raise SimulationError(f"{step} 输出文件验证失败")
                
            # 验证能量
            if not await self._validate_energy(step, "nvt.edr"):
                raise SimulationError(f"{step} 能量验证失败")
            
            self.status.completed_steps.append(step)
            logger.info(f"{step} 完成")
            
            return {
                "grompp": grompp_result.dict(),
                "mdrun": mdrun_result.dict(),
                "status": "success"
            }
            
        except Exception as e:
            self.status.errors[step] = str(e)
            logger.error(f"{step} 失败: {str(e)}")
            raise
        
    async def run_npt_equilibration(self, ctx: Context) -> Dict[str, str]:
        """运行NPT平衡"""
        step = SimulationStep.NPT_EQUILIBRATION
        self.status.current_step = step
        logger.info(f"开始{step}")
        
        try:
            # 检查前一步是否完成
            if SimulationStep.NVT_EQUILIBRATION not in self.status.completed_steps:
                raise SimulationError("必须先完成NVT平衡")
            
            # 创建NPT平衡的mdp文件
            npt_mdp = self.work_dir / "npt.mdp"
            self._create_npt_mdp(npt_mdp, self.params.equilibration)
            
            # 生成tpr文件
            grompp_result = await run_gromacs_command(ctx, "grompp", [
                "-f", str(npt_mdp),
                "-c", "nvt.gro",
                "-r", "nvt.gro",
                "-t", "nvt.cpt",
                "-p", "topol.top",
                "-o", "npt.tpr"
            ])
            
            if grompp_result.return_code != 0:
                raise SimulationError(f"生成TPR文件失败: {grompp_result.stderr}")
            
            # 运行NPT平衡
            mdrun_result = await run_gromacs_command(ctx, "mdrun", [
                "-v",
                "-deffnm", "npt"
            ])
            
            # 监控进度
            await self._monitor_progress(step, "npt.log")
            
            # 验证输出
            required_files = ["npt.gro", "npt.edr", "npt.log", "npt.cpt"]
            if not await self._check_output_files(step, required_files):
                raise SimulationError(f"{step} 输出文件验证失败")
                
            # 验证能量
            if not await self._validate_energy(step, "npt.edr"):
                raise SimulationError(f"{step} 能量验证失败")
            
            self.status.completed_steps.append(step)
            logger.info(f"{step} 完成")
            
            return {
                "grompp": grompp_result.dict(),
                "mdrun": mdrun_result.dict(),
                "status": "success"
            }
            
        except Exception as e:
            self.status.errors[step] = str(e)
            logger.error(f"{step} 失败: {str(e)}")
            raise
        
    async def run_production(self, ctx: Context) -> Dict[str, str]:
        """运行生产模拟"""
        step = SimulationStep.PRODUCTION
        self.status.current_step = step
        logger.info(f"开始{step}")
        
        try:
            # 检查前一步是否完成
            if SimulationStep.NPT_EQUILIBRATION not in self.status.completed_steps:
                raise SimulationError("必须先完成NPT平衡")
            
            # 创建生产模拟的mdp文件
            md_mdp = self.work_dir / "md.mdp"
            self._create_md_mdp(md_mdp, self.params.production)
            
            # 生成tpr文件
            grompp_result = await run_gromacs_command(ctx, "grompp", [
                "-f", str(md_mdp),
                "-c", "npt.gro",
                "-t", "npt.cpt",
                "-p", "topol.top",
                "-o", "md.tpr"
            ])
            
            if grompp_result.return_code != 0:
                raise SimulationError(f"生成TPR文件失败: {grompp_result.stderr}")
            
            # 运行生产模拟
            mdrun_result = await run_gromacs_command(ctx, "mdrun", [
                "-v",
                "-deffnm", "md"
            ])
            
            # 监控进度
            await self._monitor_progress(step, "md.log")
            
            # 验证输出
            required_files = ["md.gro", "md.edr", "md.log", "md.xtc", "md.cpt"]
            if not await self._check_output_files(step, required_files):
                raise SimulationError(f"{step} 输出文件验证失败")
                
            # 验证能量
            if not await self._validate_energy(step, "md.edr"):
                raise SimulationError(f"{step} 能量验证失败")
            
            self.status.completed_steps.append(step)
            logger.info(f"{step} 完成")
            
            return {
                "grompp": grompp_result.dict(),
                "mdrun": mdrun_result.dict(),
                "status": "success"
            }
            
        except Exception as e:
            self.status.errors[step] = str(e)
            logger.error(f"{step} 失败: {str(e)}")
            raise
            
    async def get_simulation_status(self) -> SimulationStatus:
        """获取模拟状态"""
        return self.status
        
    async def backup_checkpoint(self, step: SimulationStep):
        """备份检查点文件"""
        try:
            checkpoint_dir = self.work_dir / "checkpoints" / step.value
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            
            # 根据步骤备份相关文件
            files_to_backup = {
                SimulationStep.MINIMIZATION: ["em.gro", "em.edr", "em.log"],
                SimulationStep.NVT_EQUILIBRATION: ["nvt.gro", "nvt.edr", "nvt.log", "nvt.cpt"],
                SimulationStep.NPT_EQUILIBRATION: ["npt.gro", "npt.edr", "npt.log", "npt.cpt"],
                SimulationStep.PRODUCTION: ["md.gro", "md.edr", "md.log", "md.xtc", "md.cpt"]
            }
            
            for file in files_to_backup.get(step, []):
                src = self.work_dir / file
                if src.exists():
                    dst = checkpoint_dir / file
                    import shutil
                    shutil.copy2(src, dst)
                    
            logger.info(f"已备份{step}的检查点文件")
            
        except Exception as e:
            logger.error(f"备份{step}检查点文件失败: {str(e)}")
            raise
            
    async def restore_checkpoint(self, step: SimulationStep) -> bool:
        """从检查点恢复"""
        try:
            checkpoint_dir = self.work_dir / "checkpoints" / step.value
            if not checkpoint_dir.exists():
                logger.error(f"找不到{step}的检查点目录")
                return False
                
            # 恢复文件
            files_to_restore = {
                SimulationStep.MINIMIZATION: ["em.gro", "em.edr", "em.log"],
                SimulationStep.NVT_EQUILIBRATION: ["nvt.gro", "nvt.edr", "nvt.log", "nvt.cpt"],
                SimulationStep.NPT_EQUILIBRATION: ["npt.gro", "npt.edr", "npt.log", "npt.cpt"],
                SimulationStep.PRODUCTION: ["md.gro", "md.edr", "md.log", "md.xtc", "md.cpt"]
            }
            
            for file in files_to_restore.get(step, []):
                src = checkpoint_dir / file
                if src.exists():
                    dst = self.work_dir / file
                    import shutil
                    shutil.copy2(src, dst)
                else:
                    logger.error(f"找不到检查点文件: {file}")
                    return False
                    
            logger.info(f"已从检查点恢复{step}")
            return True
            
        except Exception as e:
            logger.error(f"恢复{step}检查点失败: {str(e)}")
            return False
    
    def _create_em_mdp(self, file_path: Path, params: EnergyMinimizationParams):
        """创建能量最小化的mdp文件"""
        content = f"""
; 能量最小化参数
integrator              = {params.integrator}
emtol                  = {params.emtol}
nsteps                 = {params.nsteps}
nstenergy              = 500
nstlog                 = 500

; 约束
constraints            = none
cutoff-scheme         = Verlet

; van der Waals
vdwtype               = Cut-off
rvdw                  = 1.0
rvdw-switch           = 0.8

; 静电
coulombtype           = PME
rcoulomb              = 1.0
        """
        with open(file_path, 'w') as f:
            f.write(content.strip())
            
    def _create_nvt_mdp(self, file_path: Path, params: EquilibrationParams):
        """创建NVT平衡的mdp文件"""
        content = f"""
; NVT平衡参数
integrator              = md
nsteps                 = {params.nvt_steps}
dt                     = 0.002

; 输出控制
nstxout                = 500
nstvout                = 500
nstenergy              = 500
nstlog                 = 500

; 温度耦合
tcoupl                 = V-rescale
tc-grps                = Protein Non-Protein
tau_t                  = 0.1 0.1
ref_t                  = {params.temperature} {params.temperature}

; 压力耦合
pcoupl                 = no

; 约束
constraints            = all-bonds
constraint_algorithm   = lincs

; van der Waals
vdwtype               = Cut-off
rvdw                  = 1.0
rvdw-switch           = 0.8

; 静电
coulombtype           = PME
rcoulomb              = 1.0
        """
        with open(file_path, 'w') as f:
            f.write(content.strip())
            
    def _create_npt_mdp(self, file_path: Path, params: EquilibrationParams):
        """创建NPT平衡的mdp文件"""
        content = f"""
; NPT平衡参数
integrator              = md
nsteps                 = {params.npt_steps}
dt                     = 0.002

; 输出控制
nstxout                = 500
nstvout                = 500
nstenergy              = 500
nstlog                 = 500

; 温度耦合
tcoupl                 = V-rescale
tc-grps                = Protein Non-Protein
tau_t                  = 0.1 0.1
ref_t                  = {params.temperature} {params.temperature}

; 压力耦合
pcoupl                 = Parrinello-Rahman
pcoupltype             = isotropic
tau_p                  = 2.0
ref_p                  = {params.pressure}
compressibility        = 4.5e-5

; 约束
constraints            = all-bonds
constraint_algorithm   = lincs

; van der Waals
vdwtype               = Cut-off
rvdw                  = 1.0
rvdw-switch           = 0.8

; 静电
coulombtype           = PME
rcoulomb              = 1.0
        """
        with open(file_path, 'w') as f:
            f.write(content.strip())
            
    def _create_md_mdp(self, file_path: Path, params: ProductionParams):
        """创建生产模拟的mdp文件"""
        content = f"""
; 生产模拟参数
integrator              = md
nsteps                 = {params.nsteps}
dt                     = {params.dt}

; 输出控制
nstxout                = 5000
nstvout                = 5000
nstenergy              = 5000
nstlog                 = 5000
nstxtcout              = 5000

; 温度耦合
tcoupl                 = V-rescale
tc-grps                = Protein Non-Protein
tau_t                  = 0.1 0.1
ref_t                  = {params.temperature} {params.temperature}

; 压力耦合
pcoupl                 = Parrinello-Rahman
pcoupltype             = isotropic
tau_p                  = 2.0
ref_p                  = {params.pressure}
compressibility        = 4.5e-5

; 约束
constraints            = all-bonds
constraint_algorithm   = lincs

; van der Waals
vdwtype               = Cut-off
rvdw                  = 1.0
rvdw-switch           = 0.8

; 静电
coulombtype           = PME
rcoulomb              = 1.0
        """
        with open(file_path, 'w') as f:
            f.write(content.strip()) 