import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union
import logging

from .models import (
    CompleteSimulationParams,
    SimulationStatus,
    SimulationStep
)

logger = logging.getLogger(__name__)

class WorkflowMetadata:
    """工作流程元数据"""
    def __init__(
        self,
        workflow_id: str,
        name: str,
        description: Optional[str] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        status: Optional[SimulationStatus] = None,
        params: Optional[CompleteSimulationParams] = None
    ):
        self.workflow_id = workflow_id
        self.name = name
        self.description = description
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or self.created_at
        self.status = status or SimulationStatus()
        self.params = params
        
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status.dict() if self.status else None,
            "params": self.params.dict() if self.params else None
        }
        
    @classmethod
    def from_dict(cls, data: Dict) -> "WorkflowMetadata":
        """从字典创建实例"""
        return cls(
            workflow_id=data["workflow_id"],
            name=data["name"],
            description=data.get("description"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            status=SimulationStatus(**data["status"]) if data.get("status") else None,
            params=CompleteSimulationParams(**data["params"]) if data.get("params") else None
        )

class WorkflowManager:
    """工作流程管理器"""
    
    def __init__(self, workspace_root: Union[str, Path]):
        self.workspace_root = Path(workspace_root)
        self.metadata_dir = self.workspace_root / ".mcp" / "workflows"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        
    def create_workflow(
        self,
        name: str,
        description: Optional[str] = None,
        params: Optional[CompleteSimulationParams] = None
    ) -> str:
        """创建新的工作流程"""
        workflow_id = str(uuid.uuid4())
        metadata = WorkflowMetadata(
            workflow_id=workflow_id,
            name=name,
            description=description,
            params=params
        )
        
        # 创建工作流程目录
        workflow_dir = self.workspace_root / workflow_id
        workflow_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存元数据
        self._save_metadata(metadata)
        
        logger.info(f"创建工作流程: {workflow_id}")
        return workflow_id
        
    def get_workflow(self, workflow_id: str) -> Optional[WorkflowMetadata]:
        """获取工作流程信息"""
        metadata_file = self.metadata_dir / f"{workflow_id}.json"
        if not metadata_file.exists():
            return None
            
        try:
            with open(metadata_file, 'r') as f:
                data = json.load(f)
            return WorkflowMetadata.from_dict(data)
            
        except Exception as e:
            logger.error(f"读取工作流程元数据失败: {str(e)}")
            return None
            
    def list_workflows(self) -> List[WorkflowMetadata]:
        """列出所有工作流程"""
        workflows = []
        for metadata_file in self.metadata_dir.glob("*.json"):
            try:
                with open(metadata_file, 'r') as f:
                    data = json.load(f)
                workflows.append(WorkflowMetadata.from_dict(data))
            except Exception as e:
                logger.error(f"读取工作流程元数据失败 {metadata_file}: {str(e)}")
                continue
        return workflows
        
    def update_workflow(
        self,
        workflow_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[SimulationStatus] = None,
        params: Optional[CompleteSimulationParams] = None
    ) -> bool:
        """更新工作流程信息"""
        metadata = self.get_workflow(workflow_id)
        if not metadata:
            return False
            
        if name:
            metadata.name = name
        if description:
            metadata.description = description
        if status:
            metadata.status = status
        if params:
            metadata.params = params
            
        metadata.updated_at = datetime.now().isoformat()
        
        try:
            self._save_metadata(metadata)
            return True
        except Exception as e:
            logger.error(f"更新工作流程元数据失败: {str(e)}")
            return False
            
    def delete_workflow(self, workflow_id: str) -> bool:
        """删除工作流程"""
        # 删除元数据文件
        metadata_file = self.metadata_dir / f"{workflow_id}.json"
        if metadata_file.exists():
            try:
                metadata_file.unlink()
            except Exception as e:
                logger.error(f"删除工作流程元数据失败: {str(e)}")
                return False
                
        # 删除工作流程目录
        workflow_dir = self.workspace_root / workflow_id
        if workflow_dir.exists():
            try:
                import shutil
                shutil.rmtree(workflow_dir)
            except Exception as e:
                logger.error(f"删除工作流程目录失败: {str(e)}")
                return False
                
        return True
        
    def get_workflow_directory(self, workflow_id: str) -> Optional[Path]:
        """获取工作流程目录"""
        workflow_dir = self.workspace_root / workflow_id
        return workflow_dir if workflow_dir.exists() else None
        
    def _save_metadata(self, metadata: WorkflowMetadata):
        """保存元数据"""
        metadata_file = self.metadata_dir / f"{metadata.workflow_id}.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata.to_dict(), f, indent=2)
            
    def get_workflow_logs(self, workflow_id: str) -> List[str]:
        """获取工作流程日志"""
        workflow_dir = self.get_workflow_directory(workflow_id)
        if not workflow_dir:
            return []
            
        log_dir = workflow_dir / "logs"
        if not log_dir.exists():
            return []
            
        logs = []
        for log_file in sorted(log_dir.glob("*.log")):
            try:
                with open(log_file, 'r') as f:
                    logs.extend(f.readlines())
            except Exception as e:
                logger.error(f"读取日志文件失败 {log_file}: {str(e)}")
                continue
                
        return logs
        
    def get_workflow_checkpoints(self, workflow_id: str) -> Dict[SimulationStep, List[str]]:
        """获取工作流程检查点"""
        workflow_dir = self.get_workflow_directory(workflow_id)
        if not workflow_dir:
            return {}
            
        checkpoint_dir = workflow_dir / "checkpoints"
        if not checkpoint_dir.exists():
            return {}
            
        checkpoints = {}
        for step in SimulationStep:
            step_dir = checkpoint_dir / step.value
            if step_dir.exists():
                checkpoints[step] = [f.name for f in step_dir.iterdir()]
                
        return checkpoints 