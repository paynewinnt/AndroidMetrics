# -*- coding: utf-8 -*-
"""
数据存储服务
负责性能监控数据的存储和管理
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func, and_, or_, desc, asc
from contextlib import contextmanager
import time
from collections import deque

from .connection import db_manager
from .models import (
    MonitoringSession, SystemPerformance, AppPerformance,
    NetworkStats, FPSData, PowerConsumption, AppConfig
)
from .exceptions import (
    DatabaseException, ConnectionError, DataValidationError,
    SessionNotFoundError, DataStorageError, handle_database_errors,
    validate_session_id, require_connection, validate_data_dict,
    sanitize_string_input, create_success_response
)

# 配置日志
logger = logging.getLogger(__name__)

class OptimizedDataStorageService:
    """优化的数据存储服务"""
    
    def __init__(self):
        self.db_manager = db_manager
        
        # 批量处理缓冲区
        self.batch_buffers = {
            'system_performance': deque(maxlen=200),
            'app_performance': deque(maxlen=500),
            'network_stats': deque(maxlen=300),
            'fps_data': deque(maxlen=300),
            'power_consumption': deque(maxlen=300)
        }
        
        # 缓冲区最后刷新时间
        self.last_flush_times = {table: time.time() for table in self.batch_buffers}
        
        # 配置参数
        self.batch_size_limits = {
            'system_performance': 50,
            'app_performance': 100,
            'network_stats': 75,
            'fps_data': 75,
            'power_consumption': 75
        }
        
        self.flush_intervals = {
            'system_performance': 5.0,  # 系统数据5秒刷新
            'app_performance': 3.0,     # 应用数据3秒刷新
            'network_stats': 4.0,       # 网络数据4秒刷新
            'fps_data': 4.0,            # FPS数据4秒刷新
            'power_consumption': 6.0    # 功耗数据6秒刷新
        }
        
    def ensure_connection(self):
        """确保数据库连接"""
        if not self.db_manager.is_connected():
            success = self.db_manager.connect()
            if not success:
                raise ConnectionError("数据库连接失败")
    
    # ==================== 监控会话管理 ====================
    
    @handle_database_errors("创建监控会话", raise_on_error=True)
    def create_monitoring_session(self, session_name: str, device_id: str, 
                                 config: Dict[str, Any], selected_apps: List[Dict] = None) -> Optional[int]:
        """创建监控会话"""
        # 验证输入参数
        session_name = sanitize_string_input(session_name, 255)
        device_id = sanitize_string_input(device_id, 100)
        
        if not session_name:
            raise DataValidationError("会话名称不能为空")
        
        if not isinstance(config, dict):
            raise DataValidationError("配置数据必须是字典格式")
        
        self.ensure_connection()
        
        with self.db_manager.get_session() as session:
            monitoring_session = MonitoringSession(
                session_name=session_name,
                device_id=device_id,
                start_time=datetime.utcnow(),
                status='running'
            )
            
            # 设置配置和应用列表
            monitoring_session.set_config(config)
            if selected_apps:
                if not isinstance(selected_apps, list):
                    raise DataValidationError("选中的应用列表必须是数组格式")
                monitoring_session.set_selected_apps(selected_apps)
            
            session.add(monitoring_session)
            session.flush()  # 获取ID
            
            session_id = monitoring_session.id
            logger.info(f"创建监控会话: {session_name} (ID: {session_id})")
            return session_id
            
    @handle_database_errors("结束监控会话")
    @validate_session_id
    def end_monitoring_session(self, session_id: int, status: str = 'completed') -> bool:
        """结束监控会话"""
        # 验证状态参数
        valid_statuses = ['completed', 'error', 'cancelled']
        if status not in valid_statuses:
            raise DataValidationError(f"无效的状态: {status}，允许的状态: {valid_statuses}")
        
        self.ensure_connection()
        
        with self.db_manager.get_session() as session:
            monitoring_session = session.query(MonitoringSession).filter(
                MonitoringSession.id == session_id
            ).first()
            
            if not monitoring_session:
                raise SessionNotFoundError(session_id)
            
            monitoring_session.end_time = datetime.utcnow()
            monitoring_session.status = status
            
            logger.info(f"结束监控会话 ID: {session_id}, 状态: {status}")
            return create_success_response(message=f"监控会话 {session_id} 已结束")
    
    def get_monitoring_sessions(self, limit: int = 100, offset: int = 0, 
                               status: str = None) -> List[Dict[str, Any]]:
        """获取监控会话列表"""
        try:
            self.ensure_connection()
            
            with self.db_manager.get_session() as session:
                query = session.query(MonitoringSession)
                
                if status:
                    query = query.filter(MonitoringSession.status == status)
                
                sessions = query.order_by(
                    MonitoringSession.start_time.desc()
                ).limit(limit).offset(offset).all()
                
                result = []
                for s in sessions:
                    duration = None
                    if s.end_time and s.start_time:
                        duration = (s.end_time - s.start_time).total_seconds()
                    
                    result.append({
                        'id': s.id,
                        'session_name': s.session_name,
                        'device_id': s.device_id,
                        'start_time': s.start_time,
                        'end_time': s.end_time,
                        'status': s.status,
                        'duration_seconds': duration,
                        'selected_apps': s.get_selected_apps(),
                        'config': s.get_config()
                    })
                    
                return result
                
        except Exception as e:
            logger.error(f"获取监控会话列表失败: {e}")
            return []
    
    # ==================== 数据存储 ====================
            
    def store_system_performance_optimized(self, session_id: int, data: Dict[str, Any]) -> bool:
        """优化的系统性能数据存储"""
        try:
            # 准备数据
            perf_data = {
                'session_id': session_id,
                'timestamp': data.get('timestamp', datetime.utcnow()),
                'cpu_usage': data.get('cpu_usage'),
                'cpu_temperature': data.get('cpu_temperature'),
                'load_1min': data.get('load_1min'),
                'load_5min': data.get('load_5min'),
                'load_15min': data.get('load_15min'),
                'memory_total': data.get('memory_total'),
                'memory_available': data.get('memory_available'),
                'memory_used': data.get('memory_used'),
                'memory_cached': data.get('memory_cached'),
                'memory_buffers': data.get('memory_buffers'),
                'storage_total': data.get('storage_total'),
                'storage_available': data.get('storage_available'),
                'storage_used': data.get('storage_used'),
                'battery_level': data.get('battery_level'),
                'battery_temperature': data.get('battery_temperature'),
                'battery_voltage': data.get('battery_voltage'),
                'battery_health': data.get('battery_health'),
                'battery_status': data.get('battery_status'),
                'network_rx_bytes': data.get('network_rx_bytes'),
                'network_tx_bytes': data.get('network_tx_bytes'),
                'screen_brightness': data.get('screen_brightness'),
                'screen_on': data.get('screen_on')
            }
            
            return self._add_to_batch('system_performance', perf_data)
            
        except Exception as e:
            logger.error(f"存储系统性能数据失败: {e}")
            return False
    
    def _add_to_batch(self, table_name: str, data: Dict[str, Any]) -> bool:
        """添加数据到批量缓冲区"""
        try:
            # 添加到缓冲区
            self.batch_buffers[table_name].append(data)
            
            current_time = time.time()
            
            # 检查是否需要刷新
            should_flush = (
                len(self.batch_buffers[table_name]) >= self.batch_size_limits[table_name] or
                current_time - self.last_flush_times[table_name] >= self.flush_intervals[table_name]
            )
            
            if should_flush:
                self._flush_buffer(table_name)
                
            return True
            
        except Exception as e:
            logger.error(f"添加数据到批量缓冲区失败 {table_name}: {e}")
            return False
    
    def _flush_buffer(self, table_name: str):
        """刷新指定表的缓冲区"""
        if not self.batch_buffers[table_name]:
            return
            
        try:
            # 将缓冲区数据转移到数据库管理器的批量队列
            buffer_data = list(self.batch_buffers[table_name])
            self.batch_buffers[table_name].clear()
            self.last_flush_times[table_name] = time.time()
            
            # 批量添加到数据库管理器队列
            for data in buffer_data:
                self.db_manager.add_to_batch(table_name, data)
                
            logger.debug(f"刷新了 {len(buffer_data)} 条 {table_name} 数据")
            
        except Exception as e:
            logger.error(f"刷新缓冲区失败 {table_name}: {e}")
    
    def flush_all_buffers(self):
        """刷新所有缓冲区"""
        for table_name in self.batch_buffers:
            self._flush_buffer(table_name)
    
    @handle_database_errors("存储系统性能数据")
    @validate_session_id
    def store_system_performance(self, session_id: int, data: Dict[str, Any]) -> bool:
        """存储系统性能数据 - 优化版本"""
        # 验证数据格式
        validate_data_dict(data, field_types={
            'cpu_usage': (int, float),
            'memory_used': (int, float),
            'battery_level': (int, float)
        })
        
        self.ensure_connection()
        
        # 使用优化的批量存储
        return self.store_system_performance_optimized(session_id, data)
            
    def store_app_performance(self, session_id: int, package_name: str, data: Dict[str, Any]) -> bool:
        """存储应用性能数据"""
        try:
            self.ensure_connection()
            
            with self.db_manager.get_session() as session:
                app_perf = AppPerformance(
                    session_id=session_id,
                    package_name=package_name,
                    timestamp=data.get('timestamp', datetime.utcnow()),
                    
                    # CPU指标
                    cpu_usage=data.get('cpu_usage'),
                    cpu_time_user=data.get('cpu_time_user'),
                    cpu_time_system=data.get('cpu_time_system'),
                    
                    # 内存指标
                    memory_pss=data.get('memory_pss'),
                    memory_rss=data.get('memory_rss'),
                    memory_vss=data.get('memory_vss'),
                    memory_uss=data.get('memory_uss'),
                    memory_java=data.get('memory_java'),
                    memory_native=data.get('memory_native'),
                    memory_graphics=data.get('memory_graphics'),
                    
                    # 进程指标
                    threads_count=data.get('threads_count'),
                    open_files=data.get('open_files')
                )
                
                session.add(app_perf)
                return True
                
        except Exception as e:
            logger.error(f"存储应用性能数据失败: {e}")
            return False
            
    def store_network_stats(self, session_id: int, package_name: str, data: Dict[str, Any]) -> bool:
        """存储网络统计数据"""
        try:
            self.ensure_connection()
            
            with self.db_manager.get_session() as session:
                network_stats = NetworkStats(
                    session_id=session_id,
                    package_name=package_name,
                    timestamp=data.get('timestamp', datetime.utcnow()),
                    
                    # 网络流量指标
                    rx_bytes=data.get('rx_bytes'),
                    tx_bytes=data.get('tx_bytes'),
                    rx_packets=data.get('rx_packets'),
                    tx_packets=data.get('tx_packets'),
                    
                    # 网络连接指标
                    connection_count=data.get('connection_count'),
                    tcp_connections=data.get('tcp_connections'),
                    udp_connections=data.get('udp_connections')
                )
                
                session.add(network_stats)
                return True
                
        except Exception as e:
            logger.error(f"存储网络统计数据失败: {e}")
            return False
            
    def store_fps_data(self, session_id: int, package_name: str, data: Dict[str, Any]) -> bool:
        """存储FPS数据"""
        try:
            self.ensure_connection()
            
            with self.db_manager.get_session() as session:
                fps_data = FPSData(
                    session_id=session_id,
                    package_name=package_name,
                    timestamp=data.get('timestamp', datetime.utcnow()),
                    
                    # FPS指标
                    fps=data.get('fps'),
                    frame_time_avg=data.get('frame_time_avg'),
                    frame_time_max=data.get('frame_time_max'),
                    frame_time_99p=data.get('frame_time_99p'),
                    
                    # 帧统计
                    total_frames=data.get('total_frames'),
                    dropped_frames=data.get('dropped_frames'),
                    jank_frames=data.get('jank_frames'),
                    
                    # GPU指标
                    gpu_usage=data.get('gpu_usage'),
                    gpu_temperature=data.get('gpu_temperature')
                )
                
                session.add(fps_data)
                return True
                
        except Exception as e:
            logger.error(f"存储FPS数据失败: {e}")
            return False
            
    def store_power_consumption(self, session_id: int, package_name: str, data: Dict[str, Any]) -> bool:
        """存储功耗数据"""
        try:
            self.ensure_connection()
            
            with self.db_manager.get_session() as session:
                power_data = PowerConsumption(
                    session_id=session_id,
                    package_name=package_name,
                    timestamp=data.get('timestamp', datetime.utcnow()),
                    
                    # 功耗指标
                    power_usage=data.get('power_usage'),
                    cpu_power=data.get('cpu_power'),
                    gpu_power=data.get('gpu_power'),
                    display_power=data.get('display_power'),
                    camera_power=data.get('camera_power'),
                    
                    # 无线功耗
                    wifi_power=data.get('wifi_power'),
                    bluetooth_power=data.get('bluetooth_power'),
                    cellular_power=data.get('cellular_power'),
                    
                    # 系统功耗
                    audio_power=data.get('audio_power'),
                    video_power=data.get('video_power'),
                    
                    # 唤醒锁和警报
                    wakelock_count=data.get('wakelock_count'),
                    wakelock_time=data.get('wakelock_time'),
                    alarm_count=data.get('alarm_count')
                )
                
                session.add(power_data)
                return True
                
        except Exception as e:
            logger.error(f"存储功耗数据失败: {e}")
            return False
    
    def store_batch_data(self, session_id: int, batch_data: Dict[str, Any]) -> Dict[str, bool]:
        """批量存储监控数据"""
        results = {
            'system_performance': False,
            'app_performance': False,
            'network_stats': False,
            'fps_data': False,
            'power_consumption': False
        }
        
        try:
            self.ensure_connection()
            
            # 存储系统性能数据
            if 'system' in batch_data and batch_data['system']:
                results['system_performance'] = self.store_system_performance(
                    session_id, batch_data['system']
                )
                
            # 存储应用数据
            if 'apps' in batch_data and batch_data['apps']:
                app_success = []
                network_success = []
                fps_success = []
                power_success = []
                
                for app_data in batch_data['apps']:
                    package_name = app_data.get('package_name')
                    if not package_name:
                        continue
                    
                    # 存储应用性能数据
                    app_success.append(
                        self.store_app_performance(session_id, package_name, app_data)
                    )
                    
                    # 存储网络数据
                    if any(key in app_data for key in ['rx_bytes', 'tx_bytes']):
                        network_success.append(
                            self.store_network_stats(session_id, package_name, app_data)
                        )
                    
                    # 存储FPS数据
                    if 'fps' in app_data:
                        fps_success.append(
                            self.store_fps_data(session_id, package_name, app_data)
                        )
                    
                    # 存储功耗数据
                    if any(key in app_data for key in ['power_usage', 'cpu_power']):
                        power_success.append(
                            self.store_power_consumption(session_id, package_name, app_data)
                        )
                
                results['app_performance'] = all(app_success) if app_success else True
                results['network_stats'] = all(network_success) if network_success else True
                results['fps_data'] = all(fps_success) if fps_success else True
                results['power_consumption'] = all(power_success) if power_success else True
                
            return results
            
        except Exception as e:
            logger.error(f"批量存储数据失败: {e}")
            return results
    
    # ==================== 数据查询 ====================
    
    @handle_database_errors("获取会话数据")
    @validate_session_id
    def get_session_data(self, session_id: int, data_types: List[str] = None, 
                        start_time: datetime = None, end_time: datetime = None,
                        package_names: List[str] = None) -> Dict[str, Any]:
        """获取指定会话的数据"""
        try:
            self.ensure_connection()
            
            if data_types is None:
                data_types = ['session_info', 'system', 'apps', 'network', 'fps', 'power']
            
            with self.db_manager.get_session() as session:
                # 获取会话信息
                monitoring_session = session.query(MonitoringSession).filter(
                    MonitoringSession.id == session_id
                ).first()
                
                if not monitoring_session:
                    return {}
                
                result = {}
                
                # 会话基本信息
                if 'session_info' in data_types:
                    duration = None
                    if monitoring_session.end_time and monitoring_session.start_time:
                        duration = (monitoring_session.end_time - monitoring_session.start_time).total_seconds()
                    
                    result['session_info'] = {
                        'id': monitoring_session.id,
                        'session_name': monitoring_session.session_name,
                        'device_id': monitoring_session.device_id,
                        'start_time': monitoring_session.start_time,
                        'end_time': monitoring_session.end_time,
                        'status': monitoring_session.status,
                        'duration_seconds': duration,
                        'selected_apps': monitoring_session.get_selected_apps(),
                        'config': monitoring_session.get_config()
                    }
                
                # 构建时间过滤条件
                time_filters = []
                if start_time:
                    time_filters.append(lambda table: table.timestamp >= start_time)
                if end_time:
                    time_filters.append(lambda table: table.timestamp <= end_time)
                
                # 获取系统性能数据
                if 'system' in data_types:
                    query = session.query(SystemPerformance).filter(
                        SystemPerformance.session_id == session_id
                    )
                    
                    for time_filter in time_filters:
                        query = query.filter(time_filter(SystemPerformance))
                    
                    system_data = query.order_by(SystemPerformance.timestamp).all()
                    
                    result['system_performance'] = [
                        {
                            'timestamp': d.timestamp,
                            'cpu_usage': d.cpu_usage,
                            'cpu_temperature': d.cpu_temperature,
                            'memory_total': d.memory_total,
                            'memory_available': d.memory_available,
                            'memory_used': d.memory_used,
                            'battery_level': d.battery_level,
                            'battery_temperature': d.battery_temperature,
                            'network_rx_bytes': d.network_rx_bytes,
                            'network_tx_bytes': d.network_tx_bytes,
                            'screen_brightness': d.screen_brightness,
                            'screen_on': d.screen_on
                        } for d in system_data
                    ]
                
                # 获取应用性能数据
                if 'apps' in data_types:
                    query = session.query(AppPerformance).filter(
                        AppPerformance.session_id == session_id
                    )
                    
                    if package_names:
                        query = query.filter(AppPerformance.package_name.in_(package_names))
                    
                    for time_filter in time_filters:
                        query = query.filter(time_filter(AppPerformance))
                    
                    app_data = query.order_by(AppPerformance.timestamp).all()
                    
                    # 按包名分组
                    apps_data = {}
                    for d in app_data:
                        if d.package_name not in apps_data:
                            apps_data[d.package_name] = []
                        
                        apps_data[d.package_name].append({
                            'timestamp': d.timestamp,
                            'cpu_usage': d.cpu_usage,
                            'memory_pss': d.memory_pss,
                            'memory_rss': d.memory_rss,
                            'memory_java': d.memory_java,
                            'memory_native': d.memory_native,
                            'threads_count': d.threads_count
                        })
                    
                    result['app_performance'] = apps_data
                
                # 获取网络数据
                if 'network' in data_types:
                    query = session.query(NetworkStats).filter(
                        NetworkStats.session_id == session_id
                    )
                    
                    if package_names:
                        query = query.filter(NetworkStats.package_name.in_(package_names))
                    
                    for time_filter in time_filters:
                        query = query.filter(time_filter(NetworkStats))
                    
                    network_data = query.order_by(NetworkStats.timestamp).all()
                    
                    network_data_dict = {}
                    for d in network_data:
                        if d.package_name not in network_data_dict:
                            network_data_dict[d.package_name] = []
                        
                        network_data_dict[d.package_name].append({
                            'timestamp': d.timestamp,
                            'rx_bytes': d.rx_bytes,
                            'tx_bytes': d.tx_bytes,
                            'rx_packets': d.rx_packets,
                            'tx_packets': d.tx_packets,
                            'connection_count': d.connection_count
                        })
                    
                    result['network_stats'] = network_data_dict
                
                # 获取FPS数据
                if 'fps' in data_types:
                    query = session.query(FPSData).filter(
                        FPSData.session_id == session_id
                    )
                    
                    if package_names:
                        query = query.filter(FPSData.package_name.in_(package_names))
                    
                    for time_filter in time_filters:
                        query = query.filter(time_filter(FPSData))
                    
                    fps_data = query.order_by(FPSData.timestamp).all()
                    
                    fps_data_dict = {}
                    for d in fps_data:
                        if d.package_name not in fps_data_dict:
                            fps_data_dict[d.package_name] = []
                        
                        fps_data_dict[d.package_name].append({
                            'timestamp': d.timestamp,
                            'fps': d.fps,
                            'frame_time_avg': d.frame_time_avg,
                            'frame_time_max': d.frame_time_max,
                            'dropped_frames': d.dropped_frames,
                            'total_frames': d.total_frames,
                            'gpu_usage': d.gpu_usage
                        })
                    
                    result['fps_data'] = fps_data_dict
                
                # 获取功耗数据
                if 'power' in data_types:
                    query = session.query(PowerConsumption).filter(
                        PowerConsumption.session_id == session_id
                    )
                    
                    if package_names:
                        query = query.filter(PowerConsumption.package_name.in_(package_names))
                    
                    for time_filter in time_filters:
                        query = query.filter(time_filter(PowerConsumption))
                    
                    power_data = query.order_by(PowerConsumption.timestamp).all()
                    
                    power_data_dict = {}
                    for d in power_data:
                        if d.package_name not in power_data_dict:
                            power_data_dict[d.package_name] = []
                        
                        power_data_dict[d.package_name].append({
                            'timestamp': d.timestamp,
                            'power_usage': d.power_usage,
                            'cpu_power': d.cpu_power,
                            'gpu_power': d.gpu_power,
                            'display_power': d.display_power,
                            'wifi_power': d.wifi_power,
                            'wakelock_count': d.wakelock_count,
                            'alarm_count': d.alarm_count
                        })
                    
                    result['power_consumption'] = power_data_dict
                
                return result
                
        except Exception as e:
            logger.error(f"获取会话数据失败: {e}")
            return {}
    
    def get_session_statistics(self, session_id: int, package_name: str = None) -> Dict[str, Any]:
        """获取会话统计信息"""
        try:
            self.ensure_connection()
            
            with self.db_manager.get_session() as session:
                stats = {}
                
                # 系统性能统计
                system_stats = session.query(
                    func.count(SystemPerformance.id).label('count'),
                    func.avg(SystemPerformance.cpu_usage).label('avg_cpu'),
                    func.max(SystemPerformance.cpu_usage).label('max_cpu'),
                    func.avg(SystemPerformance.memory_used).label('avg_memory'),
                    func.max(SystemPerformance.memory_used).label('max_memory'),
                    func.min(SystemPerformance.battery_level).label('min_battery'),
                    func.max(SystemPerformance.battery_level).label('max_battery')
                ).filter(SystemPerformance.session_id == session_id).first()
                
                stats['system'] = {
                    'data_points': system_stats.count or 0,
                    'avg_cpu_usage': float(system_stats.avg_cpu or 0),
                    'max_cpu_usage': float(system_stats.max_cpu or 0),
                    'avg_memory_used': float(system_stats.avg_memory or 0),
                    'max_memory_used': float(system_stats.max_memory or 0),
                    'min_battery_level': float(system_stats.min_battery or 0),
                    'max_battery_level': float(system_stats.max_battery or 0)
                }
                
                # 应用性能统计
                app_query = session.query(
                    AppPerformance.package_name,
                    func.count(AppPerformance.id).label('count'),
                    func.avg(AppPerformance.cpu_usage).label('avg_cpu'),
                    func.max(AppPerformance.cpu_usage).label('max_cpu'),
                    func.avg(AppPerformance.memory_pss).label('avg_memory'),
                    func.max(AppPerformance.memory_pss).label('max_memory')
                ).filter(AppPerformance.session_id == session_id)
                
                if package_name:
                    app_query = app_query.filter(AppPerformance.package_name == package_name)
                else:
                    app_query = app_query.group_by(AppPerformance.package_name)
                
                app_stats = app_query.all()
                
                if package_name:
                    # 单个应用的统计
                    if app_stats:
                        stat = app_stats[0]
                        stats['app'] = {
                            'package_name': stat.package_name,
                            'data_points': stat.count or 0,
                            'avg_cpu_usage': float(stat.avg_cpu or 0),
                            'max_cpu_usage': float(stat.max_cpu or 0),
                            'avg_memory_pss': float(stat.avg_memory or 0),
                            'max_memory_pss': float(stat.max_memory or 0)
                        }
                else:
                    # 所有应用的统计
                    stats['apps'] = {}
                    for stat in app_stats:
                        stats['apps'][stat.package_name] = {
                            'data_points': stat.count or 0,
                            'avg_cpu_usage': float(stat.avg_cpu or 0),
                            'max_cpu_usage': float(stat.max_cpu or 0),
                            'avg_memory_pss': float(stat.avg_memory or 0),
                            'max_memory_pss': float(stat.max_memory or 0)
                        }
                
                # 时间统计
                time_stats = session.query(
                    func.min(SystemPerformance.timestamp).label('start_time'),
                    func.max(SystemPerformance.timestamp).label('end_time')
                ).filter(SystemPerformance.session_id == session_id).first()
                
                if time_stats.start_time and time_stats.end_time:
                    duration = (time_stats.end_time - time_stats.start_time).total_seconds()
                    stats['time'] = {
                        'start_time': time_stats.start_time,
                        'end_time': time_stats.end_time,
                        'duration_seconds': duration
                    }
                
                return stats
                
        except Exception as e:
            logger.error(f"获取会话统计信息失败: {e}")
            return {}
    
    # ==================== 应用配置管理 ====================
    
    def save_app_config(self, package_name: str, **kwargs) -> bool:
        """保存应用配置"""
        try:
            self.ensure_connection()
            
            with self.db_manager.get_session() as session:
                # 查找现有配置
                app_config = session.query(AppConfig).filter(
                    AppConfig.package_name == package_name
                ).first()
                
                if app_config:
                    # 更新现有配置
                    for key, value in kwargs.items():
                        if hasattr(app_config, key):
                            setattr(app_config, key, value)
                    app_config.updated_at = datetime.utcnow()
                else:
                    # 创建新配置
                    app_config = AppConfig(package_name=package_name, **kwargs)
                    session.add(app_config)
                
                logger.debug(f"保存应用配置: {package_name}")
                return True
                
        except Exception as e:
            logger.error(f"保存应用配置失败: {e}")
            return False
    
    def get_app_configs(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """获取应用配置列表"""
        try:
            self.ensure_connection()
            
            with self.db_manager.get_session() as session:
                query = session.query(AppConfig)
                
                if enabled_only:
                    query = query.filter(AppConfig.monitoring_enabled == True)
                
                configs = query.order_by(AppConfig.updated_at.desc()).all()
                
                result = []
                for config in configs:
                    result.append({
                        'package_name': config.package_name,
                        'app_name': config.app_name,
                        'version_name': config.version_name,
                        'monitoring_enabled': config.monitoring_enabled,
                        'auto_start': config.auto_start,
                        'color_code': config.color_code,
                        'chart_visible': config.chart_visible,
                        'cpu_threshold': config.cpu_threshold,
                        'memory_threshold': config.memory_threshold,
                        'last_monitored': config.last_monitored,
                        'updated_at': config.updated_at
                    })
                
                return result
                
        except Exception as e:
            logger.error(f"获取应用配置失败: {e}")
            return []
    
    # ==================== 数据清理和维护 ====================
    
    @handle_database_errors("删除监控会话")
    @validate_session_id
    def delete_session(self, session_id: int) -> bool:
        """删除监控会话及其所有数据"""
        self.ensure_connection()
        
        with self.db_manager.get_session() as session:
            monitoring_session = session.query(MonitoringSession).filter(
                MonitoringSession.id == session_id
            ).first()
            
            if not monitoring_session:
                raise SessionNotFoundError(session_id)
            
            session.delete(monitoring_session)
            logger.info(f"删除监控会话 ID: {session_id}")
            return create_success_response(message=f"监控会话 {session_id} 已删除")
    
    def cleanup_old_data(self, days: int = None) -> Dict[str, int]:
        """清理过期数据"""
        try:
            self.ensure_connection()
            
            if days is None:
                days = self.db_manager.config.get('data_retention_days', 3)
            
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            with self.db_manager.get_session() as session:
                # 获取要删除的会话
                old_sessions = session.query(MonitoringSession).filter(
                    MonitoringSession.start_time < cutoff_date
                ).all()
                
                session_count = len(old_sessions)
                
                # 统计要删除的数据
                data_counts = {}
                for old_session in old_sessions:
                    # 统计各类数据
                    system_count = session.query(func.count(SystemPerformance.id)).filter(
                        SystemPerformance.session_id == old_session.id
                    ).scalar()
                    
                    app_count = session.query(func.count(AppPerformance.id)).filter(
                        AppPerformance.session_id == old_session.id
                    ).scalar()
                    
                    data_counts['system_performance'] = data_counts.get('system_performance', 0) + system_count
                    data_counts['app_performance'] = data_counts.get('app_performance', 0) + app_count
                    
                    # 删除会话（会级联删除相关数据）
                    session.delete(old_session)
                
                data_counts['sessions'] = session_count
                
                logger.info(f"清理了 {session_count} 个过期监控会话及相关数据")
                return data_counts
                
        except Exception as e:
            logger.error(f"清理过期数据失败: {e}")
            return {}
    
    def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        try:
            self.ensure_connection()
            
            with self.db_manager.get_session() as session:
                stats = {}
                
                # 会话统计
                stats['sessions'] = {
                    'total': session.query(func.count(MonitoringSession.id)).scalar(),
                    'running': session.query(func.count(MonitoringSession.id)).filter(
                        MonitoringSession.status == 'running'
                    ).scalar(),
                    'completed': session.query(func.count(MonitoringSession.id)).filter(
                        MonitoringSession.status == 'completed'
                    ).scalar()
                }
                
                # 数据统计
                stats['data_points'] = {
                    'system_performance': session.query(func.count(SystemPerformance.id)).scalar(),
                    'app_performance': session.query(func.count(AppPerformance.id)).scalar(),
                    'network_stats': session.query(func.count(NetworkStats.id)).scalar(),
                    'fps_data': session.query(func.count(FPSData.id)).scalar(),
                    'power_consumption': session.query(func.count(PowerConsumption.id)).scalar()
                }
                
                # 应用统计
                stats['apps'] = {
                    'total_monitored': session.query(func.count(func.distinct(AppPerformance.package_name))).scalar(),
                    'configured': session.query(func.count(AppConfig.id)).scalar(),
                    'enabled': session.query(func.count(AppConfig.id)).filter(
                        AppConfig.monitoring_enabled == True
                    ).scalar()
                }
                
                # 时间范围
                time_range = session.query(
                    func.min(MonitoringSession.start_time).label('earliest'),
                    func.max(MonitoringSession.start_time).label('latest')
                ).first()
                
                if time_range.earliest:
                    stats['time_range'] = {
                        'earliest_session': time_range.earliest,
                        'latest_session': time_range.latest,
                        'total_days': (time_range.latest - time_range.earliest).days if time_range.latest else 0
                    }
                
                return stats
                
        except Exception as e:
            logger.error(f"获取数据库统计信息失败: {e}")
            return {}
    
    def store_monitoring_data(self, session_id: int, data: Dict[str, Any]) -> bool:
        """存储监控数据（对store_batch_data的封装）"""
        try:
            # 将数据转换为批量存储格式
            batch_data = {}
            
            # 处理系统数据
            if 'system' in data:
                batch_data['system'] = data['system']
            
            # 处理应用数据
            if 'apps' in data and isinstance(data['apps'], list):
                batch_data['apps'] = []
                for app_data in data['apps']:
                    if 'app_info' in app_data:
                        # 提取包名并添加到应用数据中
                        package_name = app_data['app_info']['package_name']
                        app_data_copy = app_data.copy()
                        app_data_copy['package_name'] = package_name
                        batch_data['apps'].append(app_data_copy)
            
            # 添加时间戳
            if 'timestamp' in data:
                batch_data['timestamp'] = data['timestamp']
            
            # 调用批量存储方法
            results = self.store_batch_data(session_id, batch_data)
            
            # 如果至少有一个存储成功，则返回True
            return any(results.values())
            
        except Exception as e:
            logger.error(f"存储监控数据失败: {e}")
            return False


# 为了向后兼容，保留原类名
DataStorageService = OptimizedDataStorageService

# 全局数据存储服务实例
data_storage = OptimizedDataStorageService()