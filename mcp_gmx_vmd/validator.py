import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from .models import (
    CompleteSimulationParams,
    EnergyMinimizationParams,
    EquilibrationParams,
    ProductionParams
)

logger = logging.getLogger(__name__)

class ValidationError(Exception):
    """参数验证错误"""
    pass

class ParameterValidator:
    """参数验证器"""
    
    @staticmethod
    def validate_minimization(params: EnergyMinimizationParams) -> List[str]:
        """验证能量最小化参数"""
        warnings = []
        
        # 检查积分器
        if params.integrator not in ["steep", "cg"]:
            warnings.append("建议使用最陡下降法(steep)或共轭梯度法(cg)进行能量最小化")
            
        # 检查最大力
        if params.emtol > 2000:
            warnings.append("最大力阈值过大，可能导致最小化不充分")
        elif params.emtol < 100:
            warnings.append("最大力阈值过小，可能导致最小化时间过长")
            
        # 检查步数
        if params.nsteps < 10000:
            warnings.append("最小化步数可能不足，建议至少10000步")
        elif params.nsteps > 100000:
            warnings.append("最小化步数过多，可能不必要")
            
        return warnings
    
    @staticmethod
    def validate_equilibration(params: EquilibrationParams) -> List[str]:
        """验证平衡模拟参数"""
        warnings = []
        
        # 检查NVT步数
        if params.nvt_steps < 25000:
            warnings.append("NVT平衡步数可能不足，建议至少25000步")
            
        # 检查NPT步数
        if params.npt_steps < 25000:
            warnings.append("NPT平衡步数可能不足，建议至少25000步")
            
        # 检查温度
        if params.temperature < 273 or params.temperature > 373:
            warnings.append("温度设置不在常见范围内(273-373K)")
            
        # 检查压力
        if params.pressure != 1.0:
            warnings.append("压力不是标准大气压(1.0 bar)")
            
        return warnings
    
    @staticmethod
    def validate_production(params: ProductionParams) -> List[str]:
        """验证生产模拟参数"""
        warnings = []
        
        # 检查模拟时长
        total_time = params.nsteps * params.dt  # ps
        if total_time < 1000:  # 1 ns
            warnings.append("生产模拟时间可能过短，建议至少1 ns")
            
        # 检查时间步长
        if params.dt > 0.002:
            warnings.append("时间步长过大，可能导致不稳定")
        elif params.dt < 0.0005:
            warnings.append("时间步长过小，计算效率低")
            
        # 检查温度
        if params.temperature < 273 or params.temperature > 373:
            warnings.append("温度设置不在常见范围内(273-373K)")
            
        # 检查压力
        if params.pressure != 1.0:
            warnings.append("压力不是标准大气压(1.0 bar)")
            
        return warnings
    
    @staticmethod
    def validate_complete_params(params: CompleteSimulationParams) -> Dict[str, List[str]]:
        """验证完整的模拟参数"""
        warnings = {}
        
        # 检查结构文件
        structure_file = Path(params.structure_file)
        if not structure_file.exists():
            raise ValidationError(f"结构文件不存在: {params.structure_file}")
        if structure_file.suffix not in [".pdb", ".gro"]:
            warnings["structure"] = ["建议使用PDB或GRO格式的结构文件"]
            
        # 检查力场
        if params.force_field not in ["amber99sb-ildn", "charmm36", "gromos54a7", "opls-aa"]:
            warnings["force_field"] = ["使用的力场不是常见的蛋白质力场"]
            
        # 检查水模型
        if params.water_model not in ["tip3p", "tip4p", "spc", "spce"]:
            warnings["water_model"] = ["使用的水模型不是常见的水模型"]
            
        # 验证各阶段参数
        warnings["minimization"] = ParameterValidator.validate_minimization(params.minimization)
        warnings["equilibration"] = ParameterValidator.validate_equilibration(params.equilibration)
        warnings["production"] = ParameterValidator.validate_production(params.production)
        
        return warnings

class ParameterOptimizer:
    """参数优化器"""
    
    @staticmethod
    def optimize_minimization(params: EnergyMinimizationParams) -> Tuple[EnergyMinimizationParams, List[str]]:
        """优化能量最小化参数"""
        optimized = EnergyMinimizationParams(
            integrator="steep",  # 最陡下降法通常是最好的选择
            emtol=1000.0,       # 合理的最大力阈值
            nsteps=50000        # 适中的步数
        )
        
        changes = []
        if params.integrator != optimized.integrator:
            changes.append(f"将积分器从{params.integrator}改为{optimized.integrator}")
        if params.emtol != optimized.emtol:
            changes.append(f"将最大力阈值从{params.emtol}调整为{optimized.emtol}")
        if params.nsteps != optimized.nsteps:
            changes.append(f"将步数从{params.nsteps}调整为{optimized.nsteps}")
            
        return optimized, changes
    
    @staticmethod
    def optimize_equilibration(params: EquilibrationParams) -> Tuple[EquilibrationParams, List[str]]:
        """优化平衡模拟参数"""
        optimized = EquilibrationParams(
            nvt_steps=50000,    # 足够的NVT平衡
            npt_steps=50000,    # 足够的NPT平衡
            temperature=300,     # 室温
            pressure=1.0        # 标准大气压
        )
        
        changes = []
        if params.nvt_steps != optimized.nvt_steps:
            changes.append(f"将NVT步数从{params.nvt_steps}调整为{optimized.nvt_steps}")
        if params.npt_steps != optimized.npt_steps:
            changes.append(f"将NPT步数从{params.npt_steps}调整为{optimized.npt_steps}")
        if params.temperature != optimized.temperature:
            changes.append(f"将温度从{params.temperature}调整为{optimized.temperature}")
        if params.pressure != optimized.pressure:
            changes.append(f"将压力从{params.pressure}调整为{optimized.pressure}")
            
        return optimized, changes
    
    @staticmethod
    def optimize_production(params: ProductionParams) -> Tuple[ProductionParams, List[str]]:
        """优化生产模拟参数"""
        optimized = ProductionParams(
            nsteps=500000,      # 1 ns
            dt=0.002,           # 2 fs
            temperature=300,     # 室温
            pressure=1.0        # 标准大气压
        )
        
        changes = []
        if params.nsteps != optimized.nsteps:
            changes.append(f"将步数从{params.nsteps}调整为{optimized.nsteps}")
        if params.dt != optimized.dt:
            changes.append(f"将时间步长从{params.dt}调整为{optimized.dt}")
        if params.temperature != optimized.temperature:
            changes.append(f"将温度从{params.temperature}调整为{optimized.temperature}")
        if params.pressure != optimized.pressure:
            changes.append(f"将压力从{params.pressure}调整为{optimized.pressure}")
            
        return optimized, changes
    
    @staticmethod
    def optimize_complete_params(params: CompleteSimulationParams) -> Tuple[CompleteSimulationParams, Dict[str, List[str]]]:
        """优化完整的模拟参数"""
        optimized = CompleteSimulationParams(
            structure_file=params.structure_file,
            topology_file=params.topology_file,
            force_field="amber99sb-ildn",  # 推荐的力场
            water_model="tip3p"            # 推荐的水模型
        )
        
        changes = {}
        
        # 优化力场和水模型
        if params.force_field != optimized.force_field:
            changes["force_field"] = [f"将力场从{params.force_field}改为{optimized.force_field}"]
        if params.water_model != optimized.water_model:
            changes["water_model"] = [f"将水模型从{params.water_model}改为{optimized.water_model}"]
            
        # 优化各阶段参数
        optimized.minimization, changes["minimization"] = ParameterOptimizer.optimize_minimization(params.minimization)
        optimized.equilibration, changes["equilibration"] = ParameterOptimizer.optimize_equilibration(params.equilibration)
        optimized.production, changes["production"] = ParameterOptimizer.optimize_production(params.production)
        
        return optimized, changes 