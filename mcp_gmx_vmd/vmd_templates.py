from typing import Dict, List, Optional

class VMDTemplates:
    @staticmethod
    def load_trajectory(structure_file: str, trajectory_file: str) -> str:
        """加载结构和轨迹文件"""
        return f"""
        mol new {structure_file} type pdb waitfor all
        mol addfile {trajectory_file} type xtc waitfor all
        """
    
    @staticmethod
    def set_representation(
        selection: str = "protein",
        rep_type: str = "NewCartoon",
        color_method: str = "Structure"
    ) -> str:
        """设置分子表示方式"""
        return f"""
        mol delrep 0 top
        mol selection {selection}
        mol representation {rep_type}
        mol color {color_method}
        mol addrep top
        """
    
    @staticmethod
    def center_view() -> str:
        """居中视图"""
        return """
        display resetview
        display projection Orthographic
        mol center top
        """
    
    @staticmethod
    def save_state(filename: str) -> str:
        """保存当前状态"""
        return f"""
        render Tachyon {filename}
        """
    
    @staticmethod
    def calculate_contacts(
        sel1: str,
        sel2: str,
        cutoff: float = 3.5
    ) -> str:
        """计算原子接触"""
        return f"""
        set sel1 [atomselect top "{sel1}"]
        set sel2 [atomselect top "{sel2}"]
        set nf [molinfo top get numframes]
        set outfile [open "contacts.dat" w]
        
        for {{set i 0}} {{$i < $nf}} {{incr i}} {{
            $sel1 frame $i
            $sel2 frame $i
            set contacts [measure contacts {cutoff} $sel1 $sel2]
            puts $outfile "$i [llength [lindex $contacts 0]]"
        }}
        close $outfile
        """
    
    @staticmethod
    def calculate_rmsd(ref_frame: int = 0, selection: str = "protein and name CA") -> str:
        """计算RMSD"""
        return f"""
        set sel [atomselect top "{selection}"]
        set ref [atomselect top "{selection}" frame {ref_frame}]
        set nf [molinfo top get numframes]
        set outfile [open "rmsd.dat" w]
        
        for {{set i 0}} {{$i < $nf}} {{incr i}} {{
            $sel frame $i
            set rmsd [measure rmsd $sel $ref]
            puts $outfile "$i $rmsd"
        }}
        close $outfile
        """
    
    @staticmethod
    def calculate_secondary_structure() -> str:
        """计算二级结构"""
        return """
        package require ssrestraints
        set sel [atomselect top "protein"]
        set nf [molinfo top get numframes]
        set outfile [open "secondary_structure.dat" w]
        
        for {set i 0} {$i < $nf} {incr i} {
            $sel frame $i
            set ss [measure sasa 1.4 $sel]
            puts $outfile "$i $ss"
        }
        close $outfile
        """
    
    @staticmethod
    def create_movie(
        filename: str,
        start_frame: int = 0,
        end_frame: Optional[int] = None,
        rotation: bool = True
    ) -> str:
        """创建动画"""
        movie_script = f"""
        set filename "{filename}"
        set start {start_frame}
        """
        
        if end_frame is not None:
            movie_script += f"set end {end_frame}\n"
        else:
            movie_script += "set end [molinfo top get numframes]\n"
            
        if rotation:
            movie_script += """
            for {set i $start} {$i < $end} {incr i} {
                animate goto $i
                rotate y by 1
                render TachyonInternal $filename.$i.tga
            }
            """
        else:
            movie_script += """
            for {set i $start} {$i < $end} {incr i} {
                animate goto $i
                render TachyonInternal $filename.$i.tga
            }
            """
            
        return movie_script
    
    @staticmethod
    def set_custom_visualization(commands: List[str]) -> str:
        """执行自定义可视化命令"""
        return "\n".join(commands)

# 预定义的可视化样式
VISUALIZATION_STYLES: Dict[str, Dict[str, str]] = {
    "protein_cartoon": {
        "selection": "protein",
        "representation": "NewCartoon",
        "color_method": "Structure"
    },
    "protein_surface": {
        "selection": "protein",
        "representation": "Surface",
        "color_method": "ResType"
    },
    "ligand_licorice": {
        "selection": "not protein and not water",
        "representation": "Licorice",
        "color_method": "Name"
    },
    "water_points": {
        "selection": "water",
        "representation": "Points",
        "color_method": "Name"
    }
} 