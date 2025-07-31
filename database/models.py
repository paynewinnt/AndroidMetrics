# -*- coding: utf-8 -*-
"""
数据库模型定义
定义了AndroidMetrics监控系统的所有数据表结构
"""

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)
Base = declarative_base()

class MonitoringSession(Base):
    """监控会话表"""
    __tablename__ = 'monitoring_sessions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_name = Column(String(255), nullable=False, index=True)
    device_id = Column(String(100), nullable=True, index=True)
    start_time = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    end_time = Column(DateTime, nullable=True)
    status = Column(String(20), default='running', nullable=False)  # running, completed, error
    config_json = Column(Text, nullable=True)  # JSON格式配置数据
    selected_apps = Column(Text, nullable=True)  # JSON格式的应用列表
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # 关系定义
    system_performance = relationship("SystemPerformance", back_populates="session", cascade="all, delete-orphan")
    app_performance = relationship("AppPerformance", back_populates="session", cascade="all, delete-orphan")
    network_stats = relationship("NetworkStats", back_populates="session", cascade="all, delete-orphan")
    fps_data = relationship("FPSData", back_populates="session", cascade="all, delete-orphan")
    power_consumption = relationship("PowerConsumption", back_populates="session", cascade="all, delete-orphan")
    
    def set_config(self, config_dict):
        """设置配置数据"""
        self.config_json = json.dumps(config_dict, ensure_ascii=False, default=str)
    
    def get_config(self):
        """获取配置数据"""
        try:
            return json.loads(self.config_json) if self.config_json else {}
        except json.JSONDecodeError:
            logger.error(f"Failed to parse config JSON for session {self.id}")
            return {}
    
    def set_selected_apps(self, apps_list):
        """设置选中的应用列表"""
        self.selected_apps = json.dumps(apps_list, ensure_ascii=False)
    
    def get_selected_apps(self):
        """获取选中的应用列表"""
        try:
            return json.loads(self.selected_apps) if self.selected_apps else []
        except json.JSONDecodeError:
            logger.error(f"Failed to parse selected apps JSON for session {self.id}")
            return []

class SystemPerformance(Base):
    """系统性能数据表"""
    __tablename__ = 'system_performance'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey('monitoring_sessions.id', ondelete='CASCADE'), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # CPU指标
    cpu_usage = Column(Float, nullable=True)  # CPU使用率 %
    cpu_temperature = Column(Float, nullable=True)  # CPU温度 °C
    load_1min = Column(Float, nullable=True)  # 1分钟平均负载
    load_5min = Column(Float, nullable=True)  # 5分钟平均负载
    load_15min = Column(Float, nullable=True)  # 15分钟平均负载
    
    # 内存指标 (MB)
    memory_total = Column(Float, nullable=True)  # 总内存
    memory_available = Column(Float, nullable=True)  # 可用内存
    memory_used = Column(Float, nullable=True)  # 已用内存
    memory_cached = Column(Float, nullable=True)  # 缓存内存
    memory_buffers = Column(Float, nullable=True)  # 缓存内存
    
    # 存储指标 (MB)
    storage_total = Column(Float, nullable=True)  # 总存储空间
    storage_available = Column(Float, nullable=True)  # 可用存储空间
    storage_used = Column(Float, nullable=True)  # 已用存储空间
    
    # 电池指标
    battery_level = Column(Float, nullable=True)  # 电池电量 %
    battery_temperature = Column(Float, nullable=True)  # 电池温度 °C
    battery_voltage = Column(Float, nullable=True)  # 电池电압 V
    battery_health = Column(Integer, nullable=True)  # 电池健康状态
    battery_status = Column(Integer, nullable=True)  # 电池状态
    
    # 网络指标 (bytes)
    network_rx_bytes = Column(Float, nullable=True)  # 接收字节数
    network_tx_bytes = Column(Float, nullable=True)  # 发送字节数
    
    # 屏幕指标
    screen_brightness = Column(Float, nullable=True)  # 屏幕亮度
    screen_on = Column(Boolean, nullable=True)  # 屏幕是否开启
    
    session = relationship("MonitoringSession", back_populates="system_performance")
    
    # 添加索引
    __table_args__ = (
        Index('idx_system_session_time', 'session_id', 'timestamp'),
    )

class AppPerformance(Base):
    """应用性能数据表"""
    __tablename__ = 'app_performance'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey('monitoring_sessions.id', ondelete='CASCADE'), nullable=False)
    package_name = Column(String(255), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # CPU指标
    cpu_usage = Column(Float, nullable=True)  # CPU使用率 %
    cpu_time_user = Column(Float, nullable=True)  # 用户态CPU时间
    cpu_time_system = Column(Float, nullable=True)  # 系统态CPU时间
    
    # 内存指标 (MB)
    memory_pss = Column(Float, nullable=True)  # PSS内存
    memory_rss = Column(Float, nullable=True)  # RSS内存
    memory_vss = Column(Float, nullable=True)  # VSS内存
    memory_uss = Column(Float, nullable=True)  # USS内存
    memory_java = Column(Float, nullable=True)  # Java堆内存
    memory_native = Column(Float, nullable=True)  # Native内存
    memory_graphics = Column(Float, nullable=True)  # 图形内存
    
    # 进程指标
    threads_count = Column(Integer, nullable=True)  # 线程数
    open_files = Column(Integer, nullable=True)  # 打开文件数
    
    session = relationship("MonitoringSession", back_populates="app_performance")
    
    # 添加索引
    __table_args__ = (
        Index('idx_app_session_package_time', 'session_id', 'package_name', 'timestamp'),
    )

class NetworkStats(Base):
    """网络统计数据表"""
    __tablename__ = 'network_stats'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey('monitoring_sessions.id', ondelete='CASCADE'), nullable=False)
    package_name = Column(String(255), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # 网络流量指标 (bytes)
    rx_bytes = Column(Float, nullable=True)  # 接收字节数
    tx_bytes = Column(Float, nullable=True)  # 发送字节数
    rx_packets = Column(Integer, nullable=True)  # 接收包数
    tx_packets = Column(Integer, nullable=True)  # 发送包数
    
    # 网络连接指标
    connection_count = Column(Integer, nullable=True)  # 连接数量
    tcp_connections = Column(Integer, nullable=True)  # TCP连接数
    udp_connections = Column(Integer, nullable=True)  # UDP连接数
    
    session = relationship("MonitoringSession", back_populates="network_stats")
    
    # 添加索引
    __table_args__ = (
        Index('idx_network_session_package_time', 'session_id', 'package_name', 'timestamp'),
    )

class FPSData(Base):
    """FPS数据表"""
    __tablename__ = 'fps_data'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey('monitoring_sessions.id', ondelete='CASCADE'), nullable=False)
    package_name = Column(String(255), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # FPS指标
    fps = Column(Float, nullable=True)  # 帧率
    frame_time_avg = Column(Float, nullable=True)  # 平均帧时间 ms
    frame_time_max = Column(Float, nullable=True)  # 最大帧时间 ms
    frame_time_99p = Column(Float, nullable=True)  # 99%帧时间 ms
    
    # 帧统计
    total_frames = Column(Integer, nullable=True)  # 总帧数
    dropped_frames = Column(Integer, nullable=True)  # 丢帧数
    jank_frames = Column(Integer, nullable=True)  # 卡顿帧数
    
    # GPU指标
    gpu_usage = Column(Float, nullable=True)  # GPU使用率 %
    gpu_temperature = Column(Float, nullable=True)  # GPU温度 °C
    
    session = relationship("MonitoringSession", back_populates="fps_data")
    
    # 添加索引
    __table_args__ = (
        Index('idx_fps_session_package_time', 'session_id', 'package_name', 'timestamp'),
    )

class PowerConsumption(Base):
    """功耗数据表"""
    __tablename__ = 'power_consumption'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey('monitoring_sessions.id', ondelete='CASCADE'), nullable=False)
    package_name = Column(String(255), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # 功耗指标 (mW)
    power_usage = Column(Float, nullable=True)  # 总功耗
    cpu_power = Column(Float, nullable=True)  # CPU功耗
    gpu_power = Column(Float, nullable=True)  # GPU功耗
    display_power = Column(Float, nullable=True)  # 显示功耗
    camera_power = Column(Float, nullable=True)  # 摄像头功耗
    
    # 无线功耗
    wifi_power = Column(Float, nullable=True)  # WiFi功耗
    bluetooth_power = Column(Float, nullable=True)  # 蓝牙功耗
    cellular_power = Column(Float, nullable=True)  # 蜂窝网络功耗
    
    # 系统功耗
    audio_power = Column(Float, nullable=True)  # 音频功耗
    video_power = Column(Float, nullable=True)  # 视频功耗
    
    # 唤醒锁和警报
    wakelock_count = Column(Integer, nullable=True)  # 唤醒锁数量
    wakelock_time = Column(Float, nullable=True)  # 唤醒锁时间 ms
    alarm_count = Column(Integer, nullable=True)  # 警报数量
    
    session = relationship("MonitoringSession", back_populates="power_consumption")
    
    # 添加索引
    __table_args__ = (
        Index('idx_power_session_package_time', 'session_id', 'package_name', 'timestamp'),
    )

class AppConfig(Base):
    """应用配置表"""
    __tablename__ = 'app_configs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    package_name = Column(String(255), unique=True, nullable=False, index=True)
    app_name = Column(String(255), nullable=True)
    version_name = Column(String(100), nullable=True)
    version_code = Column(Integer, nullable=True)
    
    # 监控配置
    monitoring_enabled = Column(Boolean, default=True, nullable=False)
    auto_start = Column(Boolean, default=False, nullable=False)
    
    # 显示配置
    color_code = Column(String(7), nullable=True)  # 图表颜色 #RRGGBB
    chart_visible = Column(Boolean, default=True, nullable=False)
    
    # 阈值配置
    cpu_threshold = Column(Float, nullable=True)  # CPU告警阈值 %
    memory_threshold = Column(Float, nullable=True)  # 内存告警阈值 MB
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_monitored = Column(DateTime, nullable=True)  # 最后监控时间

class DatabaseManager:
    """数据库管理器（已弃用，使用connection.py中的DatabaseConnectionManager）"""
    
    def __init__(self, connection_string):
        logger.warning("DatabaseManager is deprecated, use DatabaseConnectionManager instead")
        self.engine = create_engine(connection_string, echo=False)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
    def create_tables(self):
        Base.metadata.create_all(bind=self.engine)
        
    def get_session(self):
        return self.SessionLocal()
        
    def close_connection(self):
        self.engine.dispose()