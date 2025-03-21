import asyncio
import os
import tempfile
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
from typing import Dict, List, Optional, Tuple, Union
import logging

from .models import AnalysisParams, AnalysisResult, AnalysisType
from .gromacs import run_gromacs_command, Context, GromacsCmdResult

logger = logging.getLogger(__name__)

class AnalysisError(Exception):
    """分析过程中的错误"""
    pass

async def analyze_trajectory(ctx: Context, params: AnalysisParams) -> AnalysisResult:
    """分析分子动力学轨迹"""
    analysis_funcs = {
        AnalysisType.RMSD: analyze_rmsd,
        AnalysisType.RMSF: analyze_rmsf,
        AnalysisType.RADIUS_OF_GYRATION: analyze_gyrate,
        AnalysisType.SECONDARY_STRUCTURE: analyze_secondary_structure,
        AnalysisType.HYDROGEN_BONDS: analyze_hbonds,
        AnalysisType.DISTANCE: analyze_distance,
        AnalysisType.ANGLE: analyze_angle,
        AnalysisType.DENSITY: analyze_density
    }
    
    if params.analysis_type not in analysis_funcs:
        raise AnalysisError(f"不支持的分析类型: {params.analysis_type}")
        
    return await analysis_funcs[params.analysis_type](ctx, params)

async def analyze_rmsd(ctx: Context, params: AnalysisParams) -> AnalysisResult:
    """分析RMSD"""
    try:
        # 详细的调试日志
        logger.info("=" * 80)
        logger.info(f"开始RMSD分析，参数详情:")
        logger.info(f"  轨迹文件: {params.trajectory_file}")
        logger.info(f"  结构文件: {params.structure_file}")
        logger.info(f"  选择: {params.selection}")
        logger.info(f"  起始时间: {params.begin_time}")
        logger.info(f"  结束时间: {params.end_time}")
        logger.info(f"  时间步长: {params.dt}")
        logger.info(f"  输出前缀: {params.output_prefix}")
        logger.info(f"  工作目录: {ctx.working_dir}")
        
        # 检查文件路径
        trajectory_file = params.trajectory_file
        structure_file = params.structure_file
        
        traj_path = os.path.join(ctx.working_dir, trajectory_file)
        struct_path = os.path.join(ctx.working_dir, structure_file)
        
        logger.info(f"完整轨迹文件路径: {traj_path}")
        logger.info(f"完整结构文件路径: {struct_path}")
        
        # 检查文件是否存在
        if not os.path.exists(traj_path):
            error_msg = f"轨迹文件不存在: {traj_path}"
            logger.error(error_msg)
            raise AnalysisError(error_msg)
            
        if not os.path.exists(struct_path):
            error_msg = f"结构文件不存在: {struct_path}"
            logger.error(error_msg)
            raise AnalysisError(error_msg)
            
        logger.info("文件检查通过，开始准备RMSD分析命令")
        
        # 创建命令参数列表，只包含必要参数
        rmsd_cmd_args = [
            "-s", structure_file,
            "-f", trajectory_file,
            "-o", f"{params.output_prefix}_rmsd.xvg"
        ]
        
        # 只有当用户明确指定了非默认值时，才添加这些参数
        if params.begin_time != 0:
            rmsd_cmd_args.extend(["-b", str(params.begin_time)])
            
        if params.end_time != -1:
            rmsd_cmd_args.extend(["-e", str(params.end_time)])
            
        if params.dt != 1:
            rmsd_cmd_args.extend(["-dt", str(params.dt)])
        
        # 提供索引组选择作为输入数据
        # 对于蛋白质RMSD，通常选择"Protein"组进行叠合和计算
        # 假设这是索引文件中的第1组 (在GROMACS索引中，索引从0开始)
        # 第一个1表示用于叠合的组，第二个1表示用于RMSD计算的组
        input_data = "1\n1\n"
        
        logger.info(f"执行RMSD计算命令: gmx rms {' '.join(rmsd_cmd_args)}")
        logger.info(f"为RMSD计算提供索引组选择: {input_data.strip().replace('\\n', ' ')}")
        
        rmsd_result = await run_gromacs_command(ctx, "rms", rmsd_cmd_args, input_data)
        
        logger.info(f"RMSD命令执行结果: success={rmsd_result.success}")
        logger.info(f"RMSD命令标准输出: {rmsd_result.stdout[:500]}...")
        logger.info(f"RMSD命令错误输出: {rmsd_result.stderr[:500]}...")
        
        if not rmsd_result.success:
            error_msg = f"RMSD计算失败: {rmsd_result.stderr}"
            logger.error(error_msg)
            raise AnalysisError(error_msg)
            
        logger.info(f"RMSD计算成功，输出文件: {params.output_prefix}_rmsd.xvg")
        
        # 检查输出文件是否存在
        xvg_file = os.path.join(ctx.working_dir, f"{params.output_prefix}_rmsd.xvg")
        logger.info(f"检查RMSD输出文件: {xvg_file}")
        
        if not os.path.exists(xvg_file):
            error_msg = f"RMSD输出文件不存在: {xvg_file}"
            logger.error(error_msg)
            raise AnalysisError(error_msg)
            
        # 读取数据
        logger.info(f"开始读取RMSD数据文件")
        try:
            data = read_xvg_file(xvg_file)
            time = data[:, 0]
            rmsd = data[:, 1]
            
            logger.info(f"成功读取数据，包含{len(time)}个数据点")
        except Exception as e:
            error_msg = f"读取RMSD数据文件失败: {str(e)}"
            logger.error(error_msg)
            raise AnalysisError(error_msg)
        
        # 计算统计信息
        stats = {
            "mean": float(np.mean(rmsd)),
            "std": float(np.std(rmsd)),
            "min": float(np.min(rmsd)),
            "max": float(np.max(rmsd))
        }
        
        logger.info(f"RMSD统计信息: 均值={stats['mean']:.4f}, 标准差={stats['std']:.4f}")
        
        # 生成图表
        plot_file = os.path.join(ctx.working_dir, f"{params.output_prefix}_rmsd.png")
        logger.info(f"生成RMSD图表: {plot_file}")
        try:
            plot_rmsd(time, rmsd, plot_file)
            logger.info(f"图表生成成功")
        except Exception as e:
            error_msg = f"生成RMSD图表失败: {str(e)}"
            logger.error(error_msg)
            # 继续执行，不因图表生成失败而中断整个分析
        
        # 构建命令日志
        command_log = [rmsd_result.command]
        
        logger.info("RMSD分析完成，准备返回结果")
        
        return AnalysisResult(
            analysis_type=AnalysisType.RMSD,
            data={"time": time.tolist(), "rmsd": rmsd.tolist()},
            statistics=stats,
            output_files={
                "xvg": f"{params.output_prefix}_rmsd.xvg",
                "plot": os.path.basename(plot_file)
            },
            plots={"rmsd": os.path.basename(plot_file)},
            command_log=command_log
        )
        
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"RMSD分析失败: {str(e)}")
        logger.error(f"异常堆栈: {tb}")
        raise AnalysisError(f"RMSD分析失败: {str(e)}")

async def analyze_rmsf(ctx: Context, params: AnalysisParams) -> AnalysisResult:
    """分析RMSF"""
    try:
        # 详细的调试日志
        logger.info("=" * 80)
        logger.info(f"开始RMSF分析，参数详情:")
        logger.info(f"  轨迹文件: {params.trajectory_file}")
        logger.info(f"  结构文件: {params.structure_file}")
        logger.info(f"  选择: {params.selection}")
        logger.info(f"  起始时间: {params.begin_time}")
        logger.info(f"  结束时间: {params.end_time}")
        logger.info(f"  时间步长: {params.dt}")
        logger.info(f"  输出前缀: {params.output_prefix}")
        logger.info(f"  工作目录: {ctx.working_dir}")
        
        # 检查文件路径
        trajectory_file = params.trajectory_file
        structure_file = params.structure_file
        
        traj_path = os.path.join(ctx.working_dir, trajectory_file)
        struct_path = os.path.join(ctx.working_dir, structure_file)
        
        # 检查文件是否存在
        if not os.path.exists(traj_path):
            error_msg = f"轨迹文件不存在: {traj_path}"
            logger.error(error_msg)
            raise AnalysisError(error_msg)
            
        if not os.path.exists(struct_path):
            error_msg = f"结构文件不存在: {struct_path}"
            logger.error(error_msg)
            raise AnalysisError(error_msg)
            
        logger.info("文件检查通过，开始准备RMSF分析命令")
        
        # 创建命令参数列表，只包含必要参数
        rmsf_cmd_args = [
            "-s", structure_file,
            "-f", trajectory_file,
            "-o", f"{params.output_prefix}_rmsf.xvg",
            "-res"  # 按残基计算
        ]
        
        # 只有当用户明确指定了非默认值时，才添加这些参数
        if params.begin_time != 0:
            rmsf_cmd_args.extend(["-b", str(params.begin_time)])
            
        if params.end_time != -1:
            rmsf_cmd_args.extend(["-e", str(params.end_time)])
            
        if params.dt != 1:
            rmsf_cmd_args.extend(["-dt", str(params.dt)])
            
        # 提供索引组选择作为输入数据
        # 对于蛋白质RMSF，通常选择"Protein"或"C-alpha"组进行计算
        input_data = "1\n"  # 选择第1组(Protein)
        
        logger.info(f"执行RMSF计算命令: gmx rmsf {' '.join(rmsf_cmd_args)}")
        logger.info(f"为RMSF计算提供索引组选择: {input_data.strip()}")
        
        rmsf_result = await run_gromacs_command(ctx, "rmsf", rmsf_cmd_args, input_data)
        
        logger.info(f"RMSF命令执行结果: success={rmsf_result.success}")
        if not rmsf_result.success:
            error_msg = f"RMSF计算失败: {rmsf_result.stderr}"
            logger.error(error_msg)
            raise AnalysisError(error_msg)
            
        logger.info(f"RMSF计算成功，输出文件: {params.output_prefix}_rmsf.xvg")
        
        # 检查输出文件是否存在
        xvg_file = os.path.join(ctx.working_dir, f"{params.output_prefix}_rmsf.xvg")
        if not os.path.exists(xvg_file):
            error_msg = f"RMSF输出文件不存在: {xvg_file}"
            logger.error(error_msg)
            raise AnalysisError(error_msg)
            
        # 读取数据
        logger.info(f"开始读取RMSF数据文件")
        try:
            data = read_xvg_file(xvg_file)
            residues = data[:, 0]
            rmsf = data[:, 1]
            
            logger.info(f"成功读取数据，包含{len(residues)}个残基数据点")
        except Exception as e:
            error_msg = f"读取RMSF数据文件失败: {str(e)}"
            logger.error(error_msg)
            raise AnalysisError(error_msg)
        
        # 计算统计信息
        stats = {
            "mean": float(np.mean(rmsf)),
            "std": float(np.std(rmsf)),
            "min": float(np.min(rmsf)),
            "max": float(np.max(rmsf))
        }
        
        logger.info(f"RMSF统计信息: 均值={stats['mean']:.4f}, 标准差={stats['std']:.4f}")
        
        # 生成图表
        plot_file = os.path.join(ctx.working_dir, f"{params.output_prefix}_rmsf.png")
        logger.info(f"生成RMSF图表: {plot_file}")
        try:
            plot_rmsf(residues, rmsf, plot_file)
            logger.info(f"图表生成成功")
        except Exception as e:
            error_msg = f"生成RMSF图表失败: {str(e)}"
            logger.error(error_msg)
            # 继续执行，不因图表生成失败而中断整个分析
        
        logger.info("RMSF分析完成，准备返回结果")
        
        return AnalysisResult(
            analysis_type=AnalysisType.RMSF,
            data={"residues": residues.tolist(), "rmsf": rmsf.tolist()},
            statistics=stats,
            output_files={
                "xvg": f"{params.output_prefix}_rmsf.xvg",
                "plot": os.path.basename(plot_file)
            },
            plots={"rmsf": os.path.basename(plot_file)},
            command_log=[rmsf_result.command]
        )
        
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"RMSF分析失败: {str(e)}")
        logger.error(f"异常堆栈: {tb}")
        raise AnalysisError(f"RMSF分析失败: {str(e)}")

async def analyze_gyrate(ctx: Context, params: AnalysisParams) -> AnalysisResult:
    """分析回旋半径"""
    try:
        # 创建索引文件
        make_ndx_result = await run_gromacs_command(ctx, "make_ndx", [
            "-f", params.structure_file,
            "-o", "index.ndx"
        ])
        
        # 计算回旋半径
        gyrate_result = await run_gromacs_command(ctx, "gyrate", [
            "-s", params.structure_file,
            "-f", params.trajectory_file,
            "-n", "index.ndx",
            "-o", f"{params.output_prefix}_gyrate.xvg",
            "-sel", params.selection,
            "-b", str(params.begin_time),
            "-e", str(params.end_time),
            "-dt", str(params.dt)
        ])
        
        # 读取数据
        data = read_xvg_file(f"{params.output_prefix}_gyrate.xvg")
        time = data[:, 0]
        rg = data[:, 1]  # 总回旋半径
        rg_x = data[:, 2]  # X方向
        rg_y = data[:, 3]  # Y方向
        rg_z = data[:, 4]  # Z方向
        
        # 计算统计信息
        stats = {
            "mean": float(np.mean(rg)),
            "std": float(np.std(rg)),
            "min": float(np.min(rg)),
            "max": float(np.max(rg)),
            "mean_x": float(np.mean(rg_x)),
            "mean_y": float(np.mean(rg_y)),
            "mean_z": float(np.mean(rg_z))
        }
        
        # 生成图表
        plot_file = f"{params.output_prefix}_gyrate.png"
        plot_gyrate(time, rg, rg_x, rg_y, rg_z, plot_file)
        
        return AnalysisResult(
            analysis_type=AnalysisType.RADIUS_OF_GYRATION,
            data={
                "time": time.tolist(),
                "rg": rg.tolist(),
                "rg_x": rg_x.tolist(),
                "rg_y": rg_y.tolist(),
                "rg_z": rg_z.tolist()
            },
            statistics=stats,
            output_files={
                "xvg": f"{params.output_prefix}_gyrate.xvg",
                "plot": plot_file
            },
            plots={"gyrate": plot_file},
            command_log=[make_ndx_result.command, gyrate_result.command]
        )
        
    except Exception as e:
        raise AnalysisError(f"回旋半径分析失败: {str(e)}")

async def analyze_secondary_structure(ctx: Context, params: AnalysisParams) -> AnalysisResult:
    """分析二级结构"""
    try:
        # 计算二级结构
        dssp_result = await run_gromacs_command(ctx, "do_dssp", [
            "-s", params.structure_file,
            "-f", params.trajectory_file,
            "-o", f"{params.output_prefix}_ss.xpm",
            "-sc", f"{params.output_prefix}_ss.xvg",
            "-b", str(params.begin_time),
            "-e", str(params.end_time),
            "-dt", str(params.dt)
        ])
        
        # 读取数据
        data = read_xvg_file(f"{params.output_prefix}_ss.xvg")
        time = data[:, 0]
        helix = data[:, 1]  # α螺旋
        sheet = data[:, 2]  # β折叠
        coil = data[:, 3]  # 无规卷曲
        
        # 计算统计信息
        stats = {
            "mean_helix": float(np.mean(helix)),
            "mean_sheet": float(np.mean(sheet)),
            "mean_coil": float(np.mean(coil)),
            "std_helix": float(np.std(helix)),
            "std_sheet": float(np.std(sheet)),
            "std_coil": float(np.std(coil))
        }
        
        # 生成图表
        plot_file = f"{params.output_prefix}_ss.png"
        plot_secondary_structure(time, helix, sheet, coil, plot_file)
        
        return AnalysisResult(
            analysis_type=AnalysisType.SECONDARY_STRUCTURE,
            data={
                "time": time.tolist(),
                "helix": helix.tolist(),
                "sheet": sheet.tolist(),
                "coil": coil.tolist()
            },
            statistics=stats,
            output_files={
                "xpm": f"{params.output_prefix}_ss.xpm",
                "xvg": f"{params.output_prefix}_ss.xvg",
                "plot": plot_file
            },
            plots={"secondary_structure": plot_file},
            command_log=[dssp_result.command]
        )
        
    except Exception as e:
        raise AnalysisError(f"二级结构分析失败: {str(e)}")

async def analyze_hbonds(ctx: Context, params: AnalysisParams) -> AnalysisResult:
    """分析氢键"""
    try:
        # 计算氢键
        hbond_result = await run_gromacs_command(ctx, "hbond", [
            "-s", params.structure_file,
            "-f", params.trajectory_file,
            "-num", f"{params.output_prefix}_hbnum.xvg",
            "-dist", f"{params.output_prefix}_hbdist.xvg",
            "-ang", f"{params.output_prefix}_hbang.xvg",
            "-sel", params.selection,
            "-b", str(params.begin_time),
            "-e", str(params.end_time),
            "-dt", str(params.dt)
        ])
        
        # 读取数据
        num_data = read_xvg_file(f"{params.output_prefix}_hbnum.xvg")
        dist_data = read_xvg_file(f"{params.output_prefix}_hbdist.xvg")
        ang_data = read_xvg_file(f"{params.output_prefix}_hbang.xvg")
        
        time = num_data[:, 0]
        num_hbonds = num_data[:, 1]
        distances = dist_data[:, 1]
        angles = ang_data[:, 1]
        
        # 计算统计信息
        stats = {
            "mean_hbonds": float(np.mean(num_hbonds)),
            "std_hbonds": float(np.std(num_hbonds)),
            "min_hbonds": float(np.min(num_hbonds)),
            "max_hbonds": float(np.max(num_hbonds)),
            "mean_distance": float(np.mean(distances)),
            "mean_angle": float(np.mean(angles))
        }
        
        # 生成图表
        num_plot = f"{params.output_prefix}_hbnum.png"
        dist_plot = f"{params.output_prefix}_hbdist.png"
        ang_plot = f"{params.output_prefix}_hbang.png"
        
        plot_hbonds_number(time, num_hbonds, num_plot)
        plot_hbonds_distribution(distances, dist_plot, "Distance")
        plot_hbonds_distribution(angles, ang_plot, "Angle")
        
        return AnalysisResult(
            analysis_type=AnalysisType.HYDROGEN_BONDS,
            data={
                "time": time.tolist(),
                "num_hbonds": num_hbonds.tolist(),
                "distances": distances.tolist(),
                "angles": angles.tolist()
            },
            statistics=stats,
            output_files={
                "num_xvg": f"{params.output_prefix}_hbnum.xvg",
                "dist_xvg": f"{params.output_prefix}_hbdist.xvg",
                "ang_xvg": f"{params.output_prefix}_hbang.xvg"
            },
            plots={
                "number": num_plot,
                "distance": dist_plot,
                "angle": ang_plot
            },
            command_log=[hbond_result.command]
        )
        
    except Exception as e:
        raise AnalysisError(f"氢键分析失败: {str(e)}")

async def analyze_distance(ctx: Context, params: AnalysisParams) -> AnalysisResult:
    """分析原子间距离"""
    try:
        # 创建索引文件
        make_ndx_result = await run_gromacs_command(ctx, "make_ndx", [
            "-f", params.structure_file,
            "-o", "index.ndx"
        ])
        
        # 计算距离
        distance_result = await run_gromacs_command(ctx, "distance", [
            "-s", params.structure_file,
            "-f", params.trajectory_file,
            "-n", "index.ndx",
            "-oall", f"{params.output_prefix}_dist.xvg",
            "-sel", params.selection,
            "-b", str(params.begin_time),
            "-e", str(params.end_time),
            "-dt", str(params.dt)
        ])
        
        # 读取数据
        data = read_xvg_file(f"{params.output_prefix}_dist.xvg")
        time = data[:, 0]
        distance = data[:, 1]
        
        # 计算统计信息
        stats = {
            "mean": float(np.mean(distance)),
            "std": float(np.std(distance)),
            "min": float(np.min(distance)),
            "max": float(np.max(distance))
        }
        
        # 生成图表
        plot_file = f"{params.output_prefix}_dist.png"
        plot_distance(time, distance, plot_file)
        
        return AnalysisResult(
            analysis_type=AnalysisType.DISTANCE,
            data={
                "time": time.tolist(),
                "distance": distance.tolist()
            },
            statistics=stats,
            output_files={
                "xvg": f"{params.output_prefix}_dist.xvg",
                "plot": plot_file
            },
            plots={"distance": plot_file},
            command_log=[make_ndx_result.command, distance_result.command]
        )
        
    except Exception as e:
        raise AnalysisError(f"距离分析失败: {str(e)}")

async def analyze_angle(ctx: Context, params: AnalysisParams) -> AnalysisResult:
    """分析原子间角度"""
    try:
        # 创建索引文件
        make_ndx_result = await run_gromacs_command(ctx, "make_ndx", [
            "-f", params.structure_file,
            "-o", "index.ndx"
        ])
        
        # 计算角度
        angle_result = await run_gromacs_command(ctx, "angle", [
            "-f", params.trajectory_file,
            "-n", "index.ndx",
            "-ov", f"{params.output_prefix}_angle.xvg",
            "-all",
            "-b", str(params.begin_time),
            "-e", str(params.end_time),
            "-dt", str(params.dt)
        ])
        
        # 读取数据
        data = read_xvg_file(f"{params.output_prefix}_angle.xvg")
        time = data[:, 0]
        angle = data[:, 1]
        
        # 计算统计信息
        stats = {
            "mean": float(np.mean(angle)),
            "std": float(np.std(angle)),
            "min": float(np.min(angle)),
            "max": float(np.max(angle))
        }
        
        # 生成图表
        plot_file = f"{params.output_prefix}_angle.png"
        plot_angle(time, angle, plot_file)
        
        return AnalysisResult(
            analysis_type=AnalysisType.ANGLE,
            data={
                "time": time.tolist(),
                "angle": angle.tolist()
            },
            statistics=stats,
            output_files={
                "xvg": f"{params.output_prefix}_angle.xvg",
                "plot": plot_file
            },
            plots={"angle": plot_file},
            command_log=[make_ndx_result.command, angle_result.command]
        )
        
    except Exception as e:
        raise AnalysisError(f"角度分析失败: {str(e)}")

async def analyze_density(ctx: Context, params: AnalysisParams) -> AnalysisResult:
    """分析密度分布"""
    try:
        # 创建索引文件
        make_ndx_result = await run_gromacs_command(ctx, "make_ndx", [
            "-f", params.structure_file,
            "-o", "index.ndx"
        ])
        
        # 计算密度
        density_result = await run_gromacs_command(ctx, "density", [
            "-s", params.structure_file,
            "-f", params.trajectory_file,
            "-n", "index.ndx",
            "-o", f"{params.output_prefix}_density.xvg",
            "-sel", params.selection,
            "-b", str(params.begin_time),
            "-e", str(params.end_time),
            "-dt", str(params.dt),
            "-d", "Z"  # 沿Z轴计算密度
        ])
        
        # 读取数据
        data = read_xvg_file(f"{params.output_prefix}_density.xvg")
        position = data[:, 0]  # nm
        density = data[:, 1]   # kg/m^3
        
        # 计算统计信息
        stats = {
            "mean": float(np.mean(density)),
            "std": float(np.std(density)),
            "min": float(np.min(density)),
            "max": float(np.max(density)),
            "total": float(np.sum(density) * (position[1] - position[0]))  # 总密度
        }
        
        # 生成图表
        plot_file = f"{params.output_prefix}_density.png"
        plot_density(position, density, plot_file)
        
        return AnalysisResult(
            analysis_type=AnalysisType.DENSITY,
            data={
                "position": position.tolist(),
                "density": density.tolist()
            },
            statistics=stats,
            output_files={
                "xvg": f"{params.output_prefix}_density.xvg",
                "plot": plot_file
            },
            plots={"density": plot_file},
            command_log=[make_ndx_result.command, density_result.command]
        )
        
    except Exception as e:
        raise AnalysisError(f"密度分析失败: {str(e)}")

def read_xvg_file(file_path: str) -> np.ndarray:
    """读取XVG文件数据
    
    Args:
        file_path: XVG文件路径
        
    Returns:
        np.ndarray: 包含数据的NumPy数组
        
    Raises:
        Exception: 读取文件失败
    """
    logger.info(f"开始读取XVG文件: {file_path}")
    
    if not os.path.exists(file_path):
        error_msg = f"XVG文件不存在: {file_path}"
        logger.error(error_msg)
        raise Exception(error_msg)
        
    try:
        data = []
        with open(file_path, 'r') as f:
            line_count = 0
            data_line_count = 0
            for line in f:
                line_count += 1
                if line.startswith(('#', '@')):
                    continue
                    
                try:
                    values = [float(x) for x in line.split()]
                    data.append(values)
                    data_line_count += 1
                except ValueError as e:
                    logger.warning(f"第{line_count}行数据格式错误: {line.strip()}, 错误信息: {str(e)}")
                    continue
        
        if not data:
            error_msg = f"XVG文件不包含有效数据: {file_path}"
            logger.error(error_msg)
            raise Exception(error_msg)
            
        logger.info(f"成功读取XVG文件, 总行数: {line_count}, 有效数据行数: {data_line_count}")
        return np.array(data)
    except Exception as e:
        error_msg = f"读取XVG文件失败: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)

def plot_rmsd(time: np.ndarray, rmsd: np.ndarray, output_file: str):
    """绘制RMSD图"""
    plt.figure(figsize=(10, 6))
    plt.plot(time, rmsd)
    plt.xlabel('Time (ps)')
    plt.ylabel('RMSD (nm)')
    plt.title('RMSD vs Time')
    plt.grid(True)
    plt.savefig(output_file)
    plt.close()

def plot_rmsf(residues: np.ndarray, rmsf: np.ndarray, output_file: str):
    """绘制RMSF图"""
    plt.figure(figsize=(10, 6))
    plt.plot(residues, rmsf)
    plt.xlabel('Residue Number')
    plt.ylabel('RMSF (nm)')
    plt.title('RMSF per Residue')
    plt.grid(True)
    plt.savefig(output_file)
    plt.close()

def plot_gyrate(time: np.ndarray, rg: np.ndarray, rg_x: np.ndarray, 
                rg_y: np.ndarray, rg_z: np.ndarray, output_file: str):
    """绘制回旋半径图"""
    plt.figure(figsize=(10, 6))
    plt.plot(time, rg, label='Total')
    plt.plot(time, rg_x, label='X')
    plt.plot(time, rg_y, label='Y')
    plt.plot(time, rg_z, label='Z')
    plt.xlabel('Time (ps)')
    plt.ylabel('Radius of Gyration (nm)')
    plt.title('Radius of Gyration vs Time')
    plt.legend()
    plt.grid(True)
    plt.savefig(output_file)
    plt.close()

def plot_secondary_structure(time: np.ndarray, helix: np.ndarray, 
                           sheet: np.ndarray, coil: np.ndarray, output_file: str):
    """绘制二级结构图"""
    plt.figure(figsize=(10, 6))
    plt.stackplot(time, [helix, sheet, coil], 
                 labels=['α-helix', 'β-sheet', 'Coil'],
                 colors=['red', 'blue', 'gray'])
    plt.xlabel('Time (ps)')
    plt.ylabel('Fraction')
    plt.title('Secondary Structure Evolution')
    plt.legend()
    plt.grid(True)
    plt.savefig(output_file)
    plt.close()

def plot_hbonds_number(time: np.ndarray, num_hbonds: np.ndarray, output_file: str):
    """绘制氢键数量随时间的变化"""
    plt.figure(figsize=(10, 6))
    plt.plot(time, num_hbonds)
    plt.xlabel('Time (ps)')
    plt.ylabel('Number of Hydrogen Bonds')
    plt.title('Hydrogen Bonds vs Time')
    plt.grid(True)
    plt.savefig(output_file)
    plt.close()

def plot_hbonds_distribution(data: np.ndarray, output_file: str, data_type: str):
    """绘制氢键距离或角度分布"""
    plt.figure(figsize=(10, 6))
    plt.hist(data, bins=50, density=True)
    plt.xlabel(f'Hydrogen Bond {data_type}')
    plt.ylabel('Probability Density')
    plt.title(f'Hydrogen Bond {data_type} Distribution')
    plt.grid(True)
    plt.savefig(output_file)
    plt.close()

def plot_distance(time: np.ndarray, distance: np.ndarray, output_file: str):
    """绘制距离随时间的变化"""
    plt.figure(figsize=(10, 6))
    plt.plot(time, distance)
    plt.xlabel('Time (ps)')
    plt.ylabel('Distance (nm)')
    plt.title('Distance vs Time')
    plt.grid(True)
    plt.savefig(output_file)
    plt.close()

def plot_angle(time: np.ndarray, angle: np.ndarray, output_file: str):
    """绘制角度随时间的变化"""
    plt.figure(figsize=(10, 6))
    plt.plot(time, angle)
    plt.xlabel('Time (ps)')
    plt.ylabel('Angle (degrees)')
    plt.title('Angle vs Time')
    plt.grid(True)
    plt.savefig(output_file)
    plt.close()

def plot_density(position: np.ndarray, density: np.ndarray, output_file: str):
    """绘制密度分布"""
    plt.figure(figsize=(10, 6))
    plt.plot(position, density)
    plt.xlabel('Position (nm)')
    plt.ylabel('Density (kg/m³)')
    plt.title('Density Profile')
    plt.grid(True)
    plt.savefig(output_file)
    plt.close()

# 分析函数映射
ANALYSIS_FUNCTIONS = {
    AnalysisType.RMSD: analyze_rmsd,
    AnalysisType.RMSF: analyze_rmsf,
    AnalysisType.RADIUS_OF_GYRATION: analyze_gyrate,
    AnalysisType.SECONDARY_STRUCTURE: analyze_secondary_structure,
    AnalysisType.HYDROGEN_BONDS: analyze_hbonds,
    AnalysisType.DISTANCE: analyze_distance,
    AnalysisType.ANGLE: analyze_angle,
    AnalysisType.DENSITY: analyze_density,
} 