# -*- coding: utf-8 -*-
"""
数据库操作工具类
提供高级数据库操作和业务逻辑
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc, text
from sqlalchemy.exc import SQLAlchemyError

from .connection import db_manager
from .data_storage import data_storage
from .models import (
    MonitoringSession, SystemPerformance, AppPerformance,
    NetworkStats, FPSData, PowerConsumption, AppConfig
)
from .exceptions import (
    DatabaseException, ConnectionError, DataValidationError,
    SessionNotFoundError, QueryExecutionError, handle_database_errors,
    validate_session_id, require_connection, create_success_response
)

logger = logging.getLogger(__name__)

class DatabaseOperations:
    """数据库操作工具类"""
    
    def __init__(self):
        self.db_manager = db_manager
        self.data_storage = data_storage
        
    # ==================== 高级查询操作 ====================
    
    @handle_database_errors("获取性能趋势")
    @validate_session_id
    def get_performance_trends(self, session_id: int, package_name: str = None, 
                              hours: int = 24) -> Dict[str, Any]:
        """获取性能趋势数据"""
        # 验证输入参数
        if hours <= 0 or hours > 168:  # 最大7天
            raise DataValidationError("小时数必须在1-168之间")
        
        if package_name:
            package_name = package_name.strip()
            if not package_name:
                raise DataValidationError("包名不能为空")
        
        self.db_manager.connect()
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        with self.db_manager.get_session() as session:
            # 首先验证会话是否存在
            session_exists = session.query(MonitoringSession).filter(
                MonitoringSession.id == session_id
            ).first()
            
            if not session_exists:
                raise SessionNotFoundError(session_id)
            
            trends = {}
            
            # 系统性能趋势
            if not package_name:
                system_trends = session.query(
                    func.date_trunc('hour', SystemPerformance.timestamp).label('hour'),
                    func.avg(SystemPerformance.cpu_usage).label('avg_cpu'),
                    func.avg(SystemPerformance.memory_used).label('avg_memory'),
                    func.avg(SystemPerformance.battery_level).label('avg_battery')
                ).filter(
                    SystemPerformance.session_id == session_id,
                    SystemPerformance.timestamp >= start_time,
                    SystemPerformance.timestamp <= end_time
                ).group_by('hour').order_by('hour').all()
                
                trends['system'] = [
                    {
                        'hour': t.hour,
                        'avg_cpu_usage': float(t.avg_cpu or 0),
                        'avg_memory_used': float(t.avg_memory or 0),
                        'avg_battery_level': float(t.avg_battery or 0)
                    } for t in system_trends
                ]
            
            # 应用性能趋势
            app_query = session.query(
                func.date_trunc('hour', AppPerformance.timestamp).label('hour'),
                AppPerformance.package_name,
                func.avg(AppPerformance.cpu_usage).label('avg_cpu'),
                func.avg(AppPerformance.memory_pss).label('avg_memory')
            ).filter(
                AppPerformance.session_id == session_id,
                AppPerformance.timestamp >= start_time,
                AppPerformance.timestamp <= end_time
            )
            
            if package_name:
                app_query = app_query.filter(AppPerformance.package_name == package_name)
            
            app_trends = app_query.group_by('hour', AppPerformance.package_name).order_by('hour').all()
            
            trends['apps'] = {}
            for t in app_trends:
                if t.package_name not in trends['apps']:
                    trends['apps'][t.package_name] = []
                
                trends['apps'][t.package_name].append({
                    'hour': t.hour,
                    'avg_cpu_usage': float(t.avg_cpu or 0),
                    'avg_memory_pss': float(t.avg_memory or 0)
                })
            
            return create_success_response(trends, "性能趋势数据获取成功")
    
    def get_top_consumers(self, session_id: int, metric: str = 'cpu', 
                         limit: int = 10) -> List[Dict[str, Any]]:
        """获取资源消耗TOP应用"""
        try:
            self.db_manager.connect()
            
            with self.db_manager.get_session() as session:
                if metric == 'cpu':
                    query = session.query(
                        AppPerformance.package_name,
                        func.avg(AppPerformance.cpu_usage).label('avg_value'),
                        func.max(AppPerformance.cpu_usage).label('max_value'),
                        func.count(AppPerformance.id).label('data_points')
                    ).filter(AppPerformance.session_id == session_id)
                    
                elif metric == 'memory':
                    query = session.query(
                        AppPerformance.package_name,
                        func.avg(AppPerformance.memory_pss).label('avg_value'),
                        func.max(AppPerformance.memory_pss).label('max_value'),
                        func.count(AppPerformance.id).label('data_points')
                    ).filter(AppPerformance.session_id == session_id)
                    
                elif metric == 'network':
                    query = session.query(
                        NetworkStats.package_name,
                        func.sum(NetworkStats.rx_bytes + NetworkStats.tx_bytes).label('total_bytes'),
                        func.avg(NetworkStats.rx_bytes + NetworkStats.tx_bytes).label('avg_value'),
                        func.count(NetworkStats.id).label('data_points')
                    ).filter(NetworkStats.session_id == session_id)
                    
                else:
                    return []
                
                if metric == 'network':
                    results = query.group_by(NetworkStats.package_name).order_by(
                        desc('total_bytes')
                    ).limit(limit).all()
                    
                    return [
                        {
                            'package_name': r.package_name,
                            'total_bytes': float(r.total_bytes or 0),
                            'avg_bytes_per_sample': float(r.avg_value or 0),
                            'data_points': r.data_points
                        } for r in results
                    ]
                else:
                    results = query.group_by(AppPerformance.package_name).order_by(
                        desc('avg_value')
                    ).limit(limit).all()
                    
                    return [
                        {
                            'package_name': r.package_name,
                            'avg_value': float(r.avg_value or 0),
                            'max_value': float(r.max_value or 0),
                            'data_points': r.data_points
                        } for r in results
                    ]
                
        except Exception as e:
            logger.error(f"获取TOP消耗应用失败: {e}")
            return []
    
    @handle_database_errors("获取会话摘要")
    @validate_session_id
    def get_session_summary(self, session_id: int) -> Dict[str, Any]:
        """获取会话详细摘要"""
        self.db_manager.connect()
        
        with self.db_manager.get_session() as session:
            # 获取会话基本信息
            monitoring_session = session.query(MonitoringSession).filter(
                MonitoringSession.id == session_id
            ).first()
            
            if not monitoring_session:
                raise SessionNotFoundError(session_id)
            
            summary = {
                'session_info': {
                    'id': monitoring_session.id,
                    'session_name': monitoring_session.session_name,
                    'device_id': monitoring_session.device_id,
                    'start_time': monitoring_session.start_time,
                    'end_time': monitoring_session.end_time,
                    'status': monitoring_session.status,
                    'selected_apps': monitoring_session.get_selected_apps()
                }
            }
            
            # 数据点统计
            summary['data_counts'] = {
                'system_performance': session.query(func.count(SystemPerformance.id)).filter(
                    SystemPerformance.session_id == session_id
                ).scalar(),
                'app_performance': session.query(func.count(AppPerformance.id)).filter(
                    AppPerformance.session_id == session_id
                ).scalar(),
                'network_stats': session.query(func.count(NetworkStats.id)).filter(
                    NetworkStats.session_id == session_id
                ).scalar(),
                'fps_data': session.query(func.count(FPSData.id)).filter(
                    FPSData.session_id == session_id
                ).scalar(),
                'power_consumption': session.query(func.count(PowerConsumption.id)).filter(
                    PowerConsumption.session_id == session_id
                ).scalar()
            }
            
            # 监控的应用列表
            monitored_apps = session.query(AppPerformance.package_name).filter(
                AppPerformance.session_id == session_id
            ).distinct().all()
            summary['monitored_packages'] = [app.package_name for app in monitored_apps]
            
            # 系统性能摘要
            system_summary = session.query(
                func.avg(SystemPerformance.cpu_usage).label('avg_cpu'),
                func.max(SystemPerformance.cpu_usage).label('max_cpu'),
                func.avg(SystemPerformance.memory_used).label('avg_memory'),
                func.max(SystemPerformance.memory_used).label('max_memory'),
                func.min(SystemPerformance.battery_level).label('min_battery'),
                func.max(SystemPerformance.battery_level).label('max_battery'),
                func.avg(SystemPerformance.cpu_temperature).label('avg_temp')
            ).filter(SystemPerformance.session_id == session_id).first()
            
            if system_summary:
                summary['system_summary'] = {
                    'avg_cpu_usage': float(system_summary.avg_cpu or 0),
                    'max_cpu_usage': float(system_summary.max_cpu or 0),
                    'avg_memory_used': float(system_summary.avg_memory or 0),
                    'max_memory_used': float(system_summary.max_memory or 0),
                    'min_battery_level': float(system_summary.min_battery or 0),
                    'max_battery_level': float(system_summary.max_battery or 0),
                    'avg_cpu_temperature': float(system_summary.avg_temp or 0)
                }
            
            # 应用性能摘要
            app_summaries = session.query(
                AppPerformance.package_name,
                func.avg(AppPerformance.cpu_usage).label('avg_cpu'),
                func.max(AppPerformance.cpu_usage).label('max_cpu'),
                func.avg(AppPerformance.memory_pss).label('avg_memory'),
                func.max(AppPerformance.memory_pss).label('max_memory')
            ).filter(AppPerformance.session_id == session_id).group_by(
                AppPerformance.package_name
            ).all()
            
            summary['app_summaries'] = {}
            for app_sum in app_summaries:
                summary['app_summaries'][app_sum.package_name] = {
                    'avg_cpu_usage': float(app_sum.avg_cpu or 0),
                    'max_cpu_usage': float(app_sum.max_cpu or 0),
                    'avg_memory_pss': float(app_sum.avg_memory or 0),
                    'max_memory_pss': float(app_sum.max_memory or 0)
                }
            
            return create_success_response(summary, "会话摘要获取成功")
    
    # ==================== 数据分析操作 ====================
    
    def detect_performance_anomalies(self, session_id: int, threshold_multiplier: float = 2.0) -> List[Dict[str, Any]]:
        """检测性能异常"""
        try:
            self.db_manager.connect()
            
            anomalies = []
            
            with self.db_manager.get_session() as session:
                # 检测CPU异常
                cpu_stats = session.query(
                    func.avg(SystemPerformance.cpu_usage).label('avg_cpu'),
                    func.stddev(SystemPerformance.cpu_usage).label('stddev_cpu')
                ).filter(SystemPerformance.session_id == session_id).first()
                
                if cpu_stats.avg_cpu and cpu_stats.stddev_cpu:
                    threshold = cpu_stats.avg_cpu + (cpu_stats.stddev_cpu * threshold_multiplier)
                    
                    cpu_anomalies = session.query(SystemPerformance).filter(
                        SystemPerformance.session_id == session_id,
                        SystemPerformance.cpu_usage > threshold
                    ).all()
                    
                    for anomaly in cpu_anomalies:
                        anomalies.append({
                            'type': 'high_cpu',
                            'timestamp': anomaly.timestamp,
                            'value': anomaly.cpu_usage,
                            'threshold': threshold,
                            'description': f'CPU使用率异常高: {anomaly.cpu_usage:.1f}%'
                        })
                
                # 检测内存异常
                memory_stats = session.query(
                    func.avg(SystemPerformance.memory_used).label('avg_memory'),
                    func.stddev(SystemPerformance.memory_used).label('stddev_memory')
                ).filter(SystemPerformance.session_id == session_id).first()
                
                if memory_stats.avg_memory and memory_stats.stddev_memory:
                    threshold = memory_stats.avg_memory + (memory_stats.stddev_memory * threshold_multiplier)
                    
                    memory_anomalies = session.query(SystemPerformance).filter(
                        SystemPerformance.session_id == session_id,
                        SystemPerformance.memory_used > threshold
                    ).all()
                    
                    for anomaly in memory_anomalies:
                        anomalies.append({
                            'type': 'high_memory',
                            'timestamp': anomaly.timestamp,
                            'value': anomaly.memory_used,
                            'threshold': threshold,
                            'description': f'内存使用异常高: {anomaly.memory_used:.1f}MB'
                        })
                
                # 按时间排序
                anomalies.sort(key=lambda x: x['timestamp'])
                
                return anomalies
                
        except Exception as e:
            logger.error(f"检测性能异常失败: {e}")
            return []
    
    def generate_performance_report(self, session_id: int) -> Dict[str, Any]:
        """生成性能报告"""
        try:
            # 获取会话摘要
            summary = self.get_session_summary(session_id)
            if not summary:
                return {}
            
            # 获取TOP消耗应用
            top_cpu_apps = self.get_top_consumers(session_id, 'cpu', 5)
            top_memory_apps = self.get_top_consumers(session_id, 'memory', 5)
            top_network_apps = self.get_top_consumers(session_id, 'network', 5)
            
            # 检测异常
            anomalies = self.detect_performance_anomalies(session_id)
            
            # 生成建议
            recommendations = self._generate_recommendations(summary, top_cpu_apps, top_memory_apps, anomalies)
            
            report = {
                'session_summary': summary,
                'top_consumers': {
                    'cpu': top_cpu_apps,
                    'memory': top_memory_apps,
                    'network': top_network_apps
                },
                'anomalies': anomalies,
                'recommendations': recommendations,
                'generated_at': datetime.utcnow()
            }
            
            return report
            
        except Exception as e:
            logger.error(f"生成性能报告失败: {e}")
            return {}
    
    def _generate_recommendations(self, summary: Dict, top_cpu: List, top_memory: List, anomalies: List) -> List[str]:
        """生成性能优化建议"""
        recommendations = []
        
        try:
            system_summary = summary.get('system_summary', {})
            
            # CPU使用率建议
            avg_cpu = system_summary.get('avg_cpu_usage', 0)
            if avg_cpu > 80:
                recommendations.append("系统CPU使用率较高，建议关闭不必要的应用")
            elif avg_cpu > 60:
                recommendations.append("系统CPU使用率偏高，注意监控性能")
            
            # 内存使用建议
            max_memory = system_summary.get('max_memory_used', 0)
            if max_memory > 1500:  # MB
                recommendations.append("内存使用量较高，建议清理后台应用")
            
            # 电池建议
            min_battery = system_summary.get('min_battery_level', 100)
            if min_battery < 20:
                recommendations.append("电池电量过低，建议减少高耗能应用使用")
            
            # 温度建议
            avg_temp = system_summary.get('avg_cpu_temperature', 0)
            if avg_temp > 70:
                recommendations.append("CPU温度较高，建议降低使用强度或改善散热")
            
            # TOP应用建议
            if top_cpu and len(top_cpu) > 0:
                highest_cpu_app = top_cpu[0]
                if highest_cpu_app['avg_value'] > 30:
                    recommendations.append(f"应用 {highest_cpu_app['package_name']} CPU使用率较高，建议优化")
            
            if top_memory and len(top_memory) > 0:
                highest_memory_app = top_memory[0]
                if highest_memory_app['avg_value'] > 200:  # MB
                    recommendations.append(f"应用 {highest_memory_app['package_name']} 内存使用较高，建议优化")
            
            # 异常建议
            if len(anomalies) > 10:
                recommendations.append("检测到多次性能异常，建议详细分析应用行为")
            
            return recommendations
            
        except Exception as e:
            logger.error(f"生成建议失败: {e}")
            return ["生成建议时出现错误"]
    
    # ==================== 数据维护操作 ====================
    
    @handle_database_errors("数据库优化")
    def optimize_database(self) -> Dict[str, Any]:
        """优化数据库性能"""
        self.db_manager.connect()
        
        with self.db_manager.get_session() as session:
            # 执行数据库优化操作
            optimization_results = {}
            
            try:
                # 更新表统计信息
                tables_to_analyze = [
                    "monitoring_sessions", "system_performance", "app_performance",
                    "network_stats", "fps_data", "power_consumption"
                ]
                
                for table in tables_to_analyze:
                    session.execute(text(f"ANALYZE TABLE {table}"))
                
                optimization_results['analyze_completed'] = True
                
                # 获取索引使用情况
                index_usage = session.execute(text("""
                    SELECT table_name, index_name, cardinality 
                    FROM information_schema.statistics 
                    WHERE table_schema = DATABASE()
                    ORDER BY cardinality DESC
                """)).fetchall()
                
                optimization_results['index_info'] = [
                    {
                        'table_name': row[0],
                        'index_name': row[1],
                        'cardinality': row[2]
                    } for row in index_usage
                ]
                
                optimization_results['optimization_time'] = datetime.utcnow()
                
                return create_success_response(optimization_results, "数据库优化完成")
                
            except Exception as e:
                raise QueryExecutionError(f"数据库优化操作失败: {str(e)}")
    
    @handle_database_errors("备份会话数据")
    @validate_session_id
    def backup_session_data(self, session_id: int, backup_path: str) -> bool:
        """备份会话数据"""
        import json
        import os
        
        # 验证备份路径
        if not backup_path or not isinstance(backup_path, str):
            raise DataValidationError("备份路径不能为空")
        
        backup_dir = os.path.dirname(backup_path)
        if backup_dir and not os.path.exists(backup_dir):
            try:
                os.makedirs(backup_dir, exist_ok=True)
            except OSError as e:
                raise DataValidationError(f"无法创建备份目录: {str(e)}")
        
        # 获取完整会话数据
        session_data = self.data_storage.get_session_data(session_id)
        
        if not session_data or not session_data.get('success', True):
            raise SessionNotFoundError(session_id)
        
        # 导出为JSON文件
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False, default=str)
        except IOError as e:
            raise DataValidationError(f"无法写入备份文件: {str(e)}")
        
        logger.info(f"会话 {session_id} 数据已备份到 {backup_path}")
        return create_success_response(message=f"会话数据已备份到 {backup_path}")
    
    # ==================== 兼容性方法 ====================
    
    def create_monitoring_session(self, session_name: str, config_data: dict, device_id: str = None) -> int:
        """创建监控会话（兼容旧接口）"""
        logger.warning("create_monitoring_session is deprecated, use data_storage.create_monitoring_session instead")
        
        session_id = self.data_storage.create_monitoring_session(
            session_name=session_name,
            device_id=device_id or 'unknown',
            config=config_data
        )
        return session_id if session_id else -1
    
    def end_monitoring_session(self, session_id: int):
        """结束监控会话（兼容旧接口）"""
        logger.warning("end_monitoring_session is deprecated, use data_storage.end_monitoring_session instead")
        
        return self.data_storage.end_monitoring_session(session_id)
    
    def get_monitoring_sessions(self, limit: int = 50):
        """获取监控会话列表（兼容旧接口）"""
        logger.warning("get_monitoring_sessions is deprecated, use data_storage.get_monitoring_sessions instead")
        
        sessions_data = self.data_storage.get_monitoring_sessions(limit=limit)
        
        # 转换为旧格式
        sessions = []
        for session_data in sessions_data:
            # 这里需要创建一个兼容对象或者直接返回字典
            sessions.append(session_data)
        
        return sessions


# 全局数据库操作实例
db_operations = DatabaseOperations()