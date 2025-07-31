# -*- coding: utf-8 -*-
"""
数据库维护工具
提供数据库备份、还原、优化、监控等维护功能
"""

import os
import json
import logging
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

from sqlalchemy import text, func
from sqlalchemy.exc import SQLAlchemyError

from .connection import db_manager
from .models import MonitoringSession, SystemPerformance, AppPerformance, NetworkStats, FPSData, PowerConsumption
from .data_storage import data_storage

logger = logging.getLogger(__name__)

class DatabaseMaintenanceTools:
    """数据库维护工具类"""
    
    def __init__(self):
        self.db_manager = db_manager
        self.data_storage = data_storage
        
    # ==================== 数据库备份和还原 ====================
    
    def backup_database(self, backup_path: str = None, compress: bool = True) -> Dict[str, Any]:
        """备份整个数据库"""
        try:
            if not backup_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_dir = os.path.join(os.path.dirname(__file__), '..', 'backups')
                os.makedirs(backup_dir, exist_ok=True)
                backup_path = os.path.join(backup_dir, f"metrics_backup_{timestamp}.sql")
            
            config = self.db_manager.config
            
            # 构建mysqldump命令
            cmd = [
                'mysqldump',
                f'--host={config["host"]}',
                f'--port={config["port"]}',
                f'--user={config["username"]}',
                f'--password={config["password"]}',
                '--single-transaction',
                '--routines',
                '--triggers',
                '--add-drop-database',
                '--create-options',
                config['database']
            ]
            
            logger.info(f"开始备份数据库到: {backup_path}")
            
            with open(backup_path, 'w', encoding='utf-8') as f:
                process = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)
            
            if process.returncode != 0:
                raise RuntimeError(f"备份失败: {process.stderr}")
            
            backup_info = {
                'success': True,
                'backup_path': backup_path,
                'backup_time': datetime.now(),
                'file_size_mb': round(os.path.getsize(backup_path) / 1024 / 1024, 2)
            }
            
            # 压缩备份文件
            if compress:
                compressed_path = f"{backup_path}.gz"
                import gzip
                with open(backup_path, 'rb') as f_in:
                    with gzip.open(compressed_path, 'wb') as f_out:
                        f_out.writelines(f_in)
                
                os.remove(backup_path)
                backup_info['backup_path'] = compressed_path
                backup_info['compressed'] = True
                backup_info['file_size_mb'] = round(os.path.getsize(compressed_path) / 1024 / 1024, 2)
            
            logger.info(f"数据库备份完成: {backup_info['backup_path']}")
            return backup_info
            
        except Exception as e:
            logger.error(f"数据库备份失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def restore_database(self, backup_path: str) -> Dict[str, Any]:
        """从备份文件还原数据库"""
        try:
            if not os.path.exists(backup_path):
                raise FileNotFoundError(f"备份文件不存在: {backup_path}")
            
            config = self.db_manager.config
            
            # 检查是否为压缩文件
            is_compressed = backup_path.endswith('.gz')
            
            if is_compressed:
                import gzip
                # 解压文件
                temp_path = backup_path[:-3]  # 移除.gz扩展名
                with gzip.open(backup_path, 'rb') as f_in:
                    with open(temp_path, 'wb') as f_out:
                        f_out.write(f_in.read())
                backup_path = temp_path
            
            # 构建mysql命令
            cmd = [
                'mysql',
                f'--host={config["host"]}',
                f'--port={config["port"]}',
                f'--user={config["username"]}',
                f'--password={config["password"]}',
                config['database']
            ]
            
            logger.info(f"开始从备份文件还原数据库: {backup_path}")
            
            with open(backup_path, 'r', encoding='utf-8') as f:
                process = subprocess.run(cmd, stdin=f, stderr=subprocess.PIPE, text=True)
            
            if process.returncode != 0:
                raise RuntimeError(f"还原失败: {process.stderr}")
            
            # 清理临时文件
            if is_compressed and os.path.exists(backup_path):
                os.remove(backup_path)
            
            logger.info("数据库还原完成")
            return {
                'success': True,
                'restore_time': datetime.now(),
                'restored_from': backup_path
            }
            
        except Exception as e:
            logger.error(f"数据库还原失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def export_session_data(self, session_id: int, export_path: str = None, 
                           format: str = 'json') -> Dict[str, Any]:
        """导出指定会话的数据"""
        try:
            if not export_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                export_dir = os.path.join(os.path.dirname(__file__), '..', 'exports')
                os.makedirs(export_dir, exist_ok=True)
                export_path = os.path.join(export_dir, f"session_{session_id}_{timestamp}.{format}")
            
            # 获取会话数据
            session_data = self.data_storage.get_session_data(session_id)
            if not session_data:
                raise ValueError(f"未找到会话 {session_id} 的数据")
            
            if format.lower() == 'json':
                with open(export_path, 'w', encoding='utf-8') as f:
                    json.dump(session_data, f, indent=2, ensure_ascii=False, default=str)
            
            elif format.lower() == 'csv':
                import pandas as pd
                
                # 将不同类型的数据分别导出为CSV
                export_dir = os.path.splitext(export_path)[0]
                os.makedirs(export_dir, exist_ok=True)
                
                for data_type, data in session_data.items():
                    if data_type == 'session_info':
                        continue
                    
                    if isinstance(data, dict):
                        for package_name, package_data in data.items():
                            if isinstance(package_data, list):
                                df = pd.DataFrame(package_data)
                                csv_path = os.path.join(export_dir, f"{data_type}_{package_name}.csv")
                                df.to_csv(csv_path, index=False)
                    elif isinstance(data, list):
                        df = pd.DataFrame(data)
                        csv_path = os.path.join(export_dir, f"{data_type}.csv")
                        df.to_csv(csv_path, index=False)
                
                export_path = export_dir
            
            else:
                raise ValueError(f"不支持的导出格式: {format}")
            
            export_info = {
                'success': True,
                'export_path': export_path,
                'export_time': datetime.now(),
                'session_id': session_id,
                'format': format
            }
            
            logger.info(f"会话数据导出完成: {export_path}")
            return export_info
            
        except Exception as e:
            logger.error(f"导出会话数据失败: {e}")
            return {'success': False, 'error': str(e)}
    
    # ==================== 数据库优化 ====================
    
    def optimize_database_performance(self) -> Dict[str, Any]:
        """优化数据库性能"""
        try:
            self.db_manager.connect()
            optimization_results = {}
            
            with self.db_manager.get_session() as session:
                # 1. 更新表统计信息
                tables = [
                    'monitoring_sessions', 'system_performance', 'app_performance',
                    'network_stats', 'fps_data', 'power_consumption', 'app_configs'
                ]
                
                for table in tables:
                    try:
                        session.execute(text(f"ANALYZE TABLE {table}"))
                        logger.debug(f"已分析表: {table}")
                    except Exception as e:
                        logger.warning(f"分析表 {table} 失败: {e}")
                
                optimization_results['analyze_completed'] = True
                
                # 2. 优化表
                for table in tables:
                    try:
                        session.execute(text(f"OPTIMIZE TABLE {table}"))
                        logger.debug(f"已优化表: {table}")
                    except Exception as e:
                        logger.warning(f"优化表 {table} 失败: {e}")
                
                optimization_results['optimize_completed'] = True
                
                # 3. 检查索引使用情况
                index_stats = session.execute(text("""
                    SELECT 
                        table_schema,
                        table_name,
                        index_name,
                        cardinality,
                        nullable
                    FROM information_schema.statistics 
                    WHERE table_schema = DATABASE()
                    ORDER BY table_name, cardinality DESC
                """)).fetchall()
                
                optimization_results['index_stats'] = [
                    {
                        'table_name': row[1],
                        'index_name': row[2],
                        'cardinality': row[3],
                        'nullable': row[4]
                    } for row in index_stats
                ]
                
                # 4. 获取表大小信息
                table_sizes = session.execute(text("""
                    SELECT 
                        table_name,
                        ROUND(((data_length + index_length) / 1024 / 1024), 2) AS 'size_mb',
                        table_rows
                    FROM information_schema.tables 
                    WHERE table_schema = DATABASE()
                    ORDER BY (data_length + index_length) DESC
                """)).fetchall()
                
                optimization_results['table_sizes'] = [
                    {
                        'table_name': row[0],
                        'size_mb': float(row[1]) if row[1] else 0,
                        'row_count': row[2] if row[2] else 0
                    } for row in table_sizes
                ]
                
                optimization_results['optimization_time'] = datetime.now()
                logger.info("数据库性能优化完成")
                return optimization_results
                
        except Exception as e:
            logger.error(f"数据库性能优化失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def check_database_health(self) -> Dict[str, Any]:
        """检查数据库健康状态"""
        try:
            self.db_manager.connect()
            health_report = {
                'overall_status': 'healthy',
                'issues': [],
                'recommendations': [],
                'check_time': datetime.now()
            }
            
            with self.db_manager.get_session() as session:
                # 1. 检查连接状态
                if not self.db_manager.is_connected():
                    health_report['overall_status'] = 'critical'
                    health_report['issues'].append('数据库连接失败')
                    return health_report
                
                # 2. 检查表空间使用情况
                db_size = session.execute(text("""
                    SELECT ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'size_mb'
                    FROM information_schema.tables 
                    WHERE table_schema = DATABASE()
                """)).scalar()
                
                if db_size and db_size > 1000:  # 超过1GB
                    health_report['issues'].append(f'数据库大小较大: {db_size}MB')
                    health_report['recommendations'].append('考虑清理过期数据或增加数据保留策略')
                
                # 3. 检查数据量
                data_counts = {}
                tables = [
                    ('monitoring_sessions', MonitoringSession),
                    ('system_performance', SystemPerformance),
                    ('app_performance', AppPerformance),
                    ('network_stats', NetworkStats),
                    ('fps_data', FPSData),
                    ('power_consumption', PowerConsumption)
                ]
                
                for table_name, model_class in tables:
                    count = session.query(func.count(model_class.id)).scalar()
                    data_counts[table_name] = count
                    
                    # 检查数据量是否过大
                    if count > 100000:  # 超过10万条记录
                        health_report['issues'].append(f'{table_name}表数据量过大: {count}条记录')
                        health_report['recommendations'].append(f'考虑清理{table_name}表的历史数据')
                
                health_report['data_counts'] = data_counts
                
                # 4. 检查索引效率
                slow_queries = session.execute(text("""
                    SELECT query_time, lock_time, rows_examined, rows_sent, sql_text
                    FROM mysql.slow_log 
                    WHERE start_time > DATE_SUB(NOW(), INTERVAL 1 DAY)
                    ORDER BY query_time DESC 
                    LIMIT 10
                """)).fetchall()
                
                if slow_queries:
                    health_report['issues'].append(f'发现{len(slow_queries)}个慢查询')
                    health_report['recommendations'].append('检查慢查询日志并优化相关索引')
                
                # 5. 检查过期数据
                retention_days = self.db_manager.config.get('data_retention_days', 3)
                cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
                
                old_sessions_count = session.query(func.count(MonitoringSession.id)).filter(
                    MonitoringSession.start_time < cutoff_date
                ).scalar()
                
                if old_sessions_count > 0:
                    health_report['issues'].append(f'存在{old_sessions_count}个过期的监控会话')
                    health_report['recommendations'].append('运行数据清理任务删除过期数据')
                
                # 6. 设置总体状态
                if len(health_report['issues']) == 0:
                    health_report['overall_status'] = 'healthy'
                elif len(health_report['issues']) <= 2:
                    health_report['overall_status'] = 'warning'
                else:
                    health_report['overall_status'] = 'critical'
                
                health_report['database_size_mb'] = db_size
                logger.info(f"数据库健康检查完成，状态: {health_report['overall_status']}")
                return health_report
                
        except Exception as e:
            logger.error(f"数据库健康检查失败: {e}")
            return {
                'overall_status': 'error',
                'error': str(e),
                'check_time': datetime.now()
            }
    
    # ==================== 数据清理 ====================
    
    def cleanup_database(self, retention_days: int = None, 
                        dry_run: bool = False) -> Dict[str, Any]:
        """清理数据库中的过期数据"""
        try:
            if retention_days is None:
                retention_days = self.db_manager.config.get('data_retention_days', 3)
            
            cleanup_results = {
                'dry_run': dry_run,
                'retention_days': retention_days,
                'deleted_counts': {},
                'cleanup_time': datetime.now()
            }
            
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
            
            self.db_manager.connect()
            with self.db_manager.get_session() as session:
                # 查找要删除的会话
                old_sessions = session.query(MonitoringSession).filter(
                    MonitoringSession.start_time < cutoff_date
                ).all()
                
                if not old_sessions:
                    cleanup_results['message'] = '没有找到需要清理的过期数据'
                    return cleanup_results
                
                # 统计要删除的数据
                for old_session in old_sessions:
                    session_id = old_session.id
                    
                    # 统计各类数据数量
                    system_count = session.query(func.count(SystemPerformance.id)).filter(
                        SystemPerformance.session_id == session_id
                    ).scalar()
                    
                    app_count = session.query(func.count(AppPerformance.id)).filter(
                        AppPerformance.session_id == session_id
                    ).scalar()
                    
                    network_count = session.query(func.count(NetworkStats.id)).filter(
                        NetworkStats.session_id == session_id
                    ).scalar()
                    
                    fps_count = session.query(func.count(FPSData.id)).filter(
                        FPSData.session_id == session_id
                    ).scalar()
                    
                    power_count = session.query(func.count(PowerConsumption.id)).filter(
                        PowerConsumption.session_id == session_id
                    ).scalar()
                    
                    # 累加到总计数
                    cleanup_results['deleted_counts']['system_performance'] = \
                        cleanup_results['deleted_counts'].get('system_performance', 0) + system_count
                    cleanup_results['deleted_counts']['app_performance'] = \
                        cleanup_results['deleted_counts'].get('app_performance', 0) + app_count
                    cleanup_results['deleted_counts']['network_stats'] = \
                        cleanup_results['deleted_counts'].get('network_stats', 0) + network_count
                    cleanup_results['deleted_counts']['fps_data'] = \
                        cleanup_results['deleted_counts'].get('fps_data', 0) + fps_count
                    cleanup_results['deleted_counts']['power_consumption'] = \
                        cleanup_results['deleted_counts'].get('power_consumption', 0) + power_count
                
                cleanup_results['deleted_counts']['monitoring_sessions'] = len(old_sessions)
                
                # 如果不是试运行，执行删除操作
                if not dry_run:
                    for old_session in old_sessions:
                        session.delete(old_session)  # 级联删除相关数据
                    
                    logger.info(f"清理了 {len(old_sessions)} 个过期监控会话及相关数据")
                else:
                    logger.info(f"试运行: 将清理 {len(old_sessions)} 个过期监控会话及相关数据")
                
                return cleanup_results
                
        except Exception as e:
            logger.error(f"数据库清理失败: {e}")
            return {'success': False, 'error': str(e)}
    
    # ==================== 监控和报告 ====================
    
    def generate_maintenance_report(self) -> Dict[str, Any]:
        """生成数据库维护报告"""
        try:
            report = {
                'report_time': datetime.now(),
                'database_info': self.db_manager.get_database_info(),
                'health_check': self.check_database_health(),
                'statistics': self.data_storage.get_database_stats()
            }
            
            # 添加维护建议
            recommendations = []
            
            # 基于健康检查结果的建议
            if report['health_check']['overall_status'] != 'healthy':
                recommendations.extend(report['health_check'].get('recommendations', []))
            
            # 基于数据库大小的建议
            db_size = report['database_info'].get('size_mb', 0)
            if db_size > 500:
                recommendations.append('数据库大小较大，建议定期备份')
            if db_size > 1000:
                recommendations.append('考虑增加数据归档策略')
            
            # 基于数据量的建议
            total_data_points = sum(report['statistics'].get('data_points', {}).values())
            if total_data_points > 1000000:
                recommendations.append('数据点数量较多，建议优化查询性能')
            
            report['maintenance_recommendations'] = recommendations
            
            logger.info("维护报告生成完成")
            return report
            
        except Exception as e:
            logger.error(f"生成维护报告失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def schedule_maintenance_task(self, task_type: str, **kwargs) -> Dict[str, Any]:
        """调度维护任务"""
        try:
            task_result = {'task_type': task_type, 'start_time': datetime.now()}
            
            if task_type == 'backup':
                result = self.backup_database(**kwargs)
                task_result.update(result)
                
            elif task_type == 'cleanup':
                result = self.cleanup_database(**kwargs)
                task_result.update(result)
                
            elif task_type == 'optimize':
                result = self.optimize_database_performance()
                task_result.update(result)
                
            elif task_type == 'health_check':
                result = self.check_database_health()
                task_result.update(result)
                
            else:
                raise ValueError(f"不支持的维护任务类型: {task_type}")
            
            task_result['end_time'] = datetime.now()
            task_result['duration_seconds'] = (
                task_result['end_time'] - task_result['start_time']
            ).total_seconds()
            
            logger.info(f"维护任务 {task_type} 完成")
            return task_result
            
        except Exception as e:
            logger.error(f"维护任务 {task_type} 失败: {e}")
            return {'success': False, 'error': str(e), 'task_type': task_type}


# 全局数据库维护工具实例
db_maintenance = DatabaseMaintenanceTools()