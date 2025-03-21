import os
import time
import logging
import psutil
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from .models import SimulationStatus, SimulationStep
from .workflow_manager import WorkflowManager

logger = logging.getLogger(__name__)

class ResourceUsage:
    """资源使用情况"""
    def __init__(self):
        self.cpu_percent = 0.0
        self.memory_percent = 0.0
        self.disk_usage = 0.0
        self.gpu_usage = None  # 如果有GPU
        
    def to_dict(self) -> Dict:
        return {
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "disk_usage": self.disk_usage,
            "gpu_usage": self.gpu_usage
        }

class SimulationProgress:
    """模拟进度"""
    def __init__(self):
        self.current_step = 0
        self.total_steps = 0
        self.elapsed_time = 0.0
        self.estimated_time = 0.0
        self.performance = 0.0  # ns/day
        
    def to_dict(self) -> Dict:
        return {
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "elapsed_time": self.elapsed_time,
            "estimated_time": self.estimated_time,
            "performance": self.performance
        }

class WorkflowMonitor:
    """工作流程监控器"""
    
    def __init__(self, workflow_manager: WorkflowManager):
        self.workflow_manager = workflow_manager
        self.monitored_workflows = {}
        
    def start_monitoring(self, workflow_id: str):
        """开始监控工作流程"""
        if workflow_id in self.monitored_workflows:
            return
            
        self.monitored_workflows[workflow_id] = {
            "start_time": datetime.now(),
            "last_check": datetime.now(),
            "resource_usage": ResourceUsage(),
            "progress": SimulationProgress()
        }
        
        logger.info(f"开始监控工作流程: {workflow_id}")
        
    def stop_monitoring(self, workflow_id: str):
        """停止监控工作流程"""
        if workflow_id in self.monitored_workflows:
            del self.monitored_workflows[workflow_id]
            logger.info(f"停止监控工作流程: {workflow_id}")
            
    def update_status(self, workflow_id: str) -> Optional[Dict]:
        """更新工作流程状态"""
        if workflow_id not in self.monitored_workflows:
            return None
            
        monitor_data = self.monitored_workflows[workflow_id]
        current_time = datetime.now()
        
        # 更新资源使用情况
        resource_usage = monitor_data["resource_usage"]
        resource_usage.cpu_percent = psutil.cpu_percent()
        resource_usage.memory_percent = psutil.virtual_memory().percent
        resource_usage.disk_usage = psutil.disk_usage('/').percent
        
        # 更新进度信息
        progress = monitor_data["progress"]
        workflow = self.workflow_manager.get_workflow(workflow_id)
        if workflow and workflow.status:
            progress.current_step = workflow.status.current_step
            progress.total_steps = workflow.status.total_steps
            
            # 计算经过时间
            elapsed = (current_time - monitor_data["start_time"]).total_seconds()
            progress.elapsed_time = elapsed
            
            # 估算剩余时间
            if progress.current_step > 0:
                progress.estimated_time = (progress.total_steps - progress.current_step) * \
                    (elapsed / progress.current_step)
                    
            # 计算性能
            time_diff = (current_time - monitor_data["last_check"]).total_seconds()
            if time_diff > 0:
                steps_diff = progress.current_step - monitor_data.get("last_step", 0)
                progress.performance = steps_diff / time_diff * 86400  # 转换为ns/day
                
        monitor_data["last_check"] = current_time
        monitor_data["last_step"] = progress.current_step
        
        return {
            "workflow_id": workflow_id,
            "timestamp": current_time.isoformat(),
            "resource_usage": resource_usage.to_dict(),
            "progress": progress.to_dict()
        }
        
    def get_log_updates(self, workflow_id: str, last_position: int = 0) -> List[str]:
        """获取日志更新"""
        logs = self.workflow_manager.get_workflow_logs(workflow_id)
        return logs[last_position:]
        
    def check_errors(self, workflow_id: str) -> List[str]:
        """检查错误"""
        errors = []
        logs = self.workflow_manager.get_workflow_logs(workflow_id)
        
        error_keywords = ["ERROR", "FATAL", "FAILED", "Segmentation fault"]
        for log in logs:
            if any(keyword in log for keyword in error_keywords):
                errors.append(log.strip())
                
        return errors
        
    def get_checkpoint_status(self, workflow_id: str) -> Dict[SimulationStep, bool]:
        """获取检查点状态"""
        checkpoints = self.workflow_manager.get_workflow_checkpoints(workflow_id)
        return {step: bool(files) for step, files in checkpoints.items()}
        
    def get_performance_stats(self, workflow_id: str) -> Dict:
        """获取性能统计"""
        if workflow_id not in self.monitored_workflows:
            return {}
            
        monitor_data = self.monitored_workflows[workflow_id]
        progress = monitor_data["progress"]
        
        return {
            "average_performance": progress.performance,
            "total_elapsed_time": progress.elapsed_time,
            "estimated_completion_time": progress.estimated_time
        }
        
    def get_resource_usage_history(self, workflow_id: str) -> List[Dict]:
        """获取资源使用历史"""
        # 这里可以实现从日志或数据库中读取历史数据
        # 当前版本仅返回最新数据
        if workflow_id not in self.monitored_workflows:
            return []
            
        monitor_data = self.monitored_workflows[workflow_id]
        return [monitor_data["resource_usage"].to_dict()] 