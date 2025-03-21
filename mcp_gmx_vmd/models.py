from enum import Enum
from typing import Dict, List, Optional, Union
from pydantic import BaseModel, Field

class AnalysisType(str, Enum):
    """轨迹分析类型"""
    RMSD = "rmsd"
    RMSF = "rmsf"
    RADIUS_OF_GYRATION = "gyrate"
    SECONDARY_STRUCTURE = "do_dssp"
    HYDROGEN_BONDS = "hbond"
    DISTANCE = "distance"
    ANGLE = "angle"
    DENSITY = "density"

class AnalysisParams(BaseModel):
    """轨迹分析参数"""
    analysis_type: AnalysisType
    trajectory_file: str
    structure_file: str
    output_prefix: str = "analysis"
    selection: str = "protein"  # 分析的原子选择
    begin_time: float = 0  # ps
    end_time: float = -1  # ps
    dt: float = 1  # ps
    
class SimulationConfig(BaseModel):
    """完整的模拟配置"""
    integrator: str = "md"
    nsteps: int = 50000  # 模拟步数
    dt: float = 0.002  # 时间步长(ps)
    temperature: float = 300  # K
    pressure: float = 1.0  # bar
    pbc: str = "xyz"  # 周期性边界条件
    constraints: str = "all-bonds"
    
class SimulationStep(str, Enum):
    """模拟步骤枚举"""
    SYSTEM_PREPARATION = "system_preparation"
    MINIMIZATION = "minimization"
    NVT_EQUILIBRATION = "nvt_equilibration"
    NPT_EQUILIBRATION = "npt_equilibration"
    PRODUCTION = "production"
    ANALYSIS = "analysis"

class SimulationStatus(BaseModel):
    """模拟状态"""
    current_step: Optional[SimulationStep] = None
    completed_steps: List[SimulationStep] = []
    errors: Dict[SimulationStep, str] = {}
    start_time: Optional[str] = None
    end_time: Optional[str] = None

class EnergyMinimizationParams(BaseModel):
    """能量最小化参数"""
    integrator: str = "steep"
    emtol: float = 1000.0  # kJ/mol/nm
    nsteps: int = 50000
    
class EquilibrationParams(BaseModel):
    """平衡模拟参数"""
    nvt_steps: int = 50000  # NVT平衡步数
    npt_steps: int = 50000  # NPT平衡步数
    temperature: float = 300  # K
    pressure: float = 1.0  # bar
    
class ProductionParams(BaseModel):
    """生产模拟参数"""
    nsteps: int = 500000  # 生产模拟步数
    temperature: float = 300  # K
    pressure: float = 1.0  # bar
    dt: float = 0.002  # 时间步长(ps)
    
class CompleteSimulationParams(BaseModel):
    """完整的模拟参数集"""
    structure_file: str
    topology_file: Optional[str] = None
    force_field: str = "amber99sb-ildn"
    water_model: str = "tip3p"
    box_type: str = "cubic"
    box_distance: float = 1.0
    ions_concentration: float = 0.15
    minimization: EnergyMinimizationParams = Field(default_factory=EnergyMinimizationParams)
    equilibration: EquilibrationParams = Field(default_factory=EquilibrationParams)
    production: ProductionParams = Field(default_factory=ProductionParams)

class AnalysisResult(BaseModel):
    """分析结果"""
    analysis_type: AnalysisType
    data: Dict[str, Union[List[float], List[List[float]]]]
    statistics: Dict[str, float]
    output_files: Dict[str, str]
    plots: Dict[str, str]  # 图表文件路径
    command_log: List[str]  # 执行的命令记录 