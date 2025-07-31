# -*- coding: utf-8 -*-
"""
数据库连接管理器
负责MySQL连接的创建、维护和释放
"""

import os
import json
import logging
from typing import Optional, Dict, Any, Tuple
from contextlib import contextmanager

import time
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool, QueuePool
from sqlalchemy.exc import SQLAlchemyError, OperationalError
try:
    import pymysql
    PYMYSQL_AVAILABLE = True
except ImportError:
    PYMYSQL_AVAILABLE = False
import threading
from queue import Queue, Empty

from .models import Base

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OptimizedConnectionPool:
    """优化的数据库连接池"""
    def __init__(self, connection_manager, max_size: int = 20):
        self.connection_manager = connection_manager
        self.max_size = max_size
        self.pool = Queue(maxsize=max_size)
        self.active_connections = set()
        self.lock = threading.Lock()
        
        # 预创建连接
        self._initialize_pool()
    
    def _initialize_pool(self):
        """初始化连接池"""
        # 延迟初始化，等待SessionLocal可用
        if not hasattr(self.connection_manager, 'SessionLocal') or self.connection_manager.SessionLocal is None:
            logger.debug("SessionLocal未就绪，跳过连接池预初始化")
            return
            
        # 检查数据库是否已连接
        if not self.connection_manager.is_connected():
            logger.debug("数据库未连接，跳过连接池预初始化")
            return
            
        for _ in range(min(5, self.max_size)):  # 预创建5个连接
            try:
                session = self.connection_manager.SessionLocal()
                # 测试连接有效性
                session.execute(text("SELECT 1"))
                self.pool.put(session, block=False)
                logger.debug("连接池预创建1个连接")
            except Exception as e:
                logger.error(f"初始化连接池失败: {e}")
                break
        
        logger.info(f"连接池初始化完成，预创建了 {self.pool.qsize()} 个连接")
    
    def get_session(self):
        """从连接池获取会话"""
        # 确保SessionLocal可用
        if not hasattr(self.connection_manager, 'SessionLocal') or self.connection_manager.SessionLocal is None:
            raise RuntimeError("数据库未初始化，SessionLocal不可用")
            
        try:
            session = self.pool.get(block=True, timeout=5)
            with self.lock:
                self.active_connections.add(session)
            return session
        except Empty:
            # 连接池为空，创建新连接
            if len(self.active_connections) < self.max_size:
                try:
                    session = self.connection_manager.SessionLocal()
                    # 测试新连接
                    session.execute(text("SELECT 1"))
                    with self.lock:
                        self.active_connections.add(session)
                    return session
                except Exception as e:
                    logger.error(f"创建新数据库连接失败: {e}")
                    raise RuntimeError(f"无法创建数据库连接: {e}")
            else:
                raise RuntimeError("连接池已满，无法获取新连接")
    
    def return_session(self, session):
        """返还会话到连接池"""
        with self.lock:
            if session in self.active_connections:
                self.active_connections.remove(session)
        
        try:
            if not self.pool.full():
                # 重置会话状态
                session.rollback()
                session.expunge_all()
                self.pool.put(session, block=False)
            else:
                session.close()
        except Exception as e:
            logger.error(f"返还连接失败: {e}")
            session.close()
    
    def close_all(self):
        """关闭所有连接"""
        with self.lock:
            # 关闭活跃连接
            for session in list(self.active_connections):
                session.close()
            self.active_connections.clear()
        
        # 关闭池中连接
        while not self.pool.empty():
            try:
                session = self.pool.get(block=False)
                session.close()
            except Empty:
                break

class DatabaseConnectionManager:
    """优化的数据库连接管理器"""
    
    def __init__(self, config_file: str = None):
        self.config_file = config_file or os.path.join(os.path.dirname(__file__), '..', 'config', 'database.json')
        self.engine: Optional[Engine] = None
        self.SessionLocal: Optional[sessionmaker] = None
        self.config: Dict[str, Any] = {}
        self.connection_pool: Optional[OptimizedConnectionPool] = None
        
        # 批量写入队列
        self.batch_queue = Queue()
        self.batch_thread = None
        self.batch_processing = False
        
        # 加载配置
        self.load_config()
        
    def load_config(self):
        """加载数据库配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    # 如果配置文件中有mysql配置，则使用mysql配置
                    if 'mysql' in config_data:
                        self.config = config_data['mysql'].copy()
                        # 添加其他配置项
                        if 'connection_pool' in config_data:
                            pool_config = config_data['connection_pool']
                            self.config.update({
                                'pool_size': pool_config.get('pool_size', 5),
                                'max_overflow': pool_config.get('max_overflow', 10),
                                'pool_timeout': pool_config.get('pool_timeout', 30),
                                'pool_recycle': pool_config.get('pool_recycle', 3600)
                            })
                        if 'data_retention' in config_data:
                            self.config['data_retention_days'] = config_data['data_retention'].get('days', 3)
                    else:
                        self.config = config_data
            else:
                # 使用默认配置
                self.config = self.get_default_config()
                self.save_config()
                
        except Exception as e:
            logger.error(f"加载数据库配置失败: {e}")
            self.config = self.get_default_config()
            
    def get_default_config(self) -> Dict[str, Any]:
        """获取默认数据库配置"""
        return {
            "host": "localhost",
            "port": 3306,
            "username": "root",
            "password": "",
            "database": "android_metrics",
            "charset": "utf8mb4",
            "pool_size": 5,
            "max_overflow": 10,
            "pool_timeout": 30,
            "pool_recycle": 3600,
            "echo": False,
            "data_retention_days": 3
        }
        
    def save_config(self):
        """保存数据库配置"""
        try:
            config_dir = os.path.dirname(self.config_file)
            os.makedirs(config_dir, exist_ok=True)
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"保存数据库配置失败: {e}")
            
    def update_config(self, new_config: Dict[str, Any]):
        """更新数据库配置"""
        self.config.update(new_config)
        self.save_config()
        
        # 如果已连接，需要重新连接
        if self.engine:
            self.disconnect()
            self.connect()
            
    def get_connection_string(self) -> str:
        """获取数据库连接字符串"""
        return (
            f"mysql+pymysql://{self.config['username']}:{self.config['password']}"
            f"@{self.config['host']}:{self.config['port']}"
            f"/{self.config['database']}"
            f"?charset={self.config['charset']}"
        )
        
    def test_connection(self) -> Tuple[bool, str]:
        """测试数据库连接"""
        try:
            # 创建临时引擎进行测试
            test_engine = create_engine(
                self.get_connection_string(),
                echo=False,
                pool_timeout=10
            )
            
            # 尝试连接
            with test_engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.fetchone()
                
            test_engine.dispose()
            return True, "连接成功"
            
        except OperationalError as e:
            if "Access denied" in str(e):
                return False, "用户名或密码错误"
            elif "Unknown database" in str(e):
                return False, f"数据库 '{self.config['database']}' 不存在"
            elif "Can't connect to MySQL server" in str(e):
                return False, f"无法连接到MySQL服务器 {self.config['host']}:{self.config['port']}"
            else:
                return False, f"数据库连接错误: {str(e)}"
                
        except Exception as e:
            return False, f"连接测试失败: {str(e)}"
            
    def create_database_if_not_exists(self) -> bool:
        """如果数据库不存在则创建"""
        try:
            # 连接到MySQL服务器（不指定数据库）
            server_config = self.config.copy()
            logger.debug(f"Config keys: {list(server_config.keys())}")
            connection_string = (
                f"mysql+pymysql://{server_config['username']}:{server_config['password']}"
                f"@{server_config['host']}:{server_config['port']}"
                f"?charset={server_config['charset']}"
            )
            
            server_engine = create_engine(connection_string, echo=False)
            
            with server_engine.connect() as conn:
                # 检查数据库是否存在
                result = conn.execute(
                    text(f"SHOW DATABASES LIKE '{self.config['database']}'")
                )
                
                if not result.fetchone():
                    # 创建数据库
                    conn.execute(
                        text(f"CREATE DATABASE `{self.config['database']}` "
                             f"CHARACTER SET {self.config['charset']} "
                             f"COLLATE {self.config['charset']}_unicode_ci")
                    )
                    conn.commit()
                    logger.info(f"数据库 '{self.config['database']}' 创建成功")
                    
            server_engine.dispose()
            return True
            
        except Exception as e:
            logger.error(f"创建数据库失败: {e}")
            return False
            
    def connect(self) -> bool:
        """连接到数据库"""
        try:
            if self.engine:
                return True
                
            # 确保数据库存在
            if not self.create_database_if_not_exists():
                return False
                
            # 创建优化的引擎
            self.engine = create_engine(
                self.get_connection_string(),
                echo=self.config.get('echo', False),
                poolclass=QueuePool,
                pool_size=self.config.get('pool_size', 10),
                max_overflow=self.config.get('max_overflow', 20),
                pool_timeout=self.config.get('pool_timeout', 30),
                pool_recycle=self.config.get('pool_recycle', 3600),
                pool_pre_ping=True,  # 自动检测连接状态
                connect_args={
                    'charset': 'utf8mb4',
                    'connect_timeout': 10,
                    'read_timeout': 30,
                    'write_timeout': 30,
                }
            )
            
            # 创建会话工厂
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            
            # 测试连接
            success, message = self.test_connection()
            if not success:
                self.disconnect()
                logger.error(f"数据库连接测试失败: {message}")
                return False
                
            # 创建表结构
            self.create_tables()
            
            # 初始化连接池
            self.connection_pool = OptimizedConnectionPool(self, max_size=20)
            # 延迟初始化连接池
            self.connection_pool._initialize_pool()
            
            # 启动批量处理线程
            self.start_batch_processing()
            
            logger.info("数据库连接成功")
            return True
            
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            self.disconnect()
            return False
            
    def disconnect(self):
        """断开数据库连接"""
        try:
            # 停止批量处理
            self.stop_batch_processing()
            
            # 关闭连接池
            if self.connection_pool:
                self.connection_pool.close_all()
                self.connection_pool = None
            
            if self.engine:
                self.engine.dispose()
                self.engine = None
                
            self.SessionLocal = None
            logger.info("数据库连接已断开")
            
        except Exception as e:
            logger.error(f"断开数据库连接时出错: {e}")
    
    def start_batch_processing(self):
        """启动批量处理线程"""
        if not self.batch_processing:
            self.batch_processing = True
            self.batch_thread = threading.Thread(target=self._batch_worker, daemon=True)
            self.batch_thread.start()
            logger.info("批量处理线程已启动")
    
    def stop_batch_processing(self):
        """停止批量处理线程"""
        if self.batch_processing:
            self.batch_processing = False
            if self.batch_thread and self.batch_thread.is_alive():
                self.batch_thread.join(timeout=5)
            logger.info("批量处理线程已停止")
    
    def _batch_worker(self):
        """批量处理工作线程"""
        batch_data = []
        last_flush_time = time.time()
        batch_size = 50
        flush_interval = 5.0  # 5秒强制刷新
        
        while self.batch_processing:
            try:
                # 尝试从队列获取数据
                try:
                    item = self.batch_queue.get(timeout=1.0)
                    batch_data.append(item)
                except Empty:
                    pass
                
                current_time = time.time()
                
                # 检查是否需要批量提交
                should_flush = (
                    len(batch_data) >= batch_size or
                    (batch_data and current_time - last_flush_time >= flush_interval)
                )
                
                if should_flush and batch_data:
                    self._flush_batch(batch_data)
                    batch_data.clear()
                    last_flush_time = current_time
                    
            except Exception as e:
                logger.error(f"批量处理出错: {e}")
                time.sleep(1)
        
        # 处理剩余数据
        if batch_data:
            self._flush_batch(batch_data)
    
    def _flush_batch(self, batch_data):
        """批量刷新数据到数据库"""
        if not batch_data:
            return
            
        try:
            session = self.connection_pool.get_session()
            try:
                # 按表类型分组数据
                grouped_data = {}
                for item in batch_data:
                    table_name = item['table']
                    if table_name not in grouped_data:
                        grouped_data[table_name] = []
                    grouped_data[table_name].append(item['data'])
                
                # 批量插入每个表的数据
                for table_name, data_list in grouped_data.items():
                    if table_name == 'system_performance':
                        from .models import SystemPerformance
                        session.bulk_insert_mappings(SystemPerformance, data_list)
                    elif table_name == 'app_performance':
                        from .models import AppPerformance
                        session.bulk_insert_mappings(AppPerformance, data_list)
                    elif table_name == 'network_stats':
                        from .models import NetworkStats
                        session.bulk_insert_mappings(NetworkStats, data_list)
                    elif table_name == 'fps_data':
                        from .models import FPSData
                        session.bulk_insert_mappings(FPSData, data_list)
                    elif table_name == 'power_consumption':
                        from .models import PowerConsumption
                        session.bulk_insert_mappings(PowerConsumption, data_list)
                
                session.commit()
                logger.debug(f"批量提交了 {len(batch_data)} 条数据")
                
            except Exception as e:
                session.rollback()
                logger.error(f"批量提交失败: {e}")
                raise
            finally:
                self.connection_pool.return_session(session)
                
        except Exception as e:
            logger.error(f"批量刷新失败: {e}")
    
    def add_to_batch(self, table_name: str, data: Dict[str, Any]):
        """添加数据到批量处理队列"""
        if self.batch_processing:
            try:
                self.batch_queue.put({
                    'table': table_name,
                    'data': data,
                    'timestamp': time.time()
                }, block=False)
            except:
                logger.warning("批量队列已满，直接写入数据库")
                # 队列满时直接写入
                self._flush_batch([{'table': table_name, 'data': data}])
            
    def create_tables(self):
        """创建数据表"""
        try:
            if not self.engine:
                raise RuntimeError("数据库未连接")
                
            Base.metadata.create_all(bind=self.engine)
            logger.info("数据表创建/更新完成")
            
        except Exception as e:
            logger.error(f"创建数据表失败: {e}")
            raise
            
    @contextmanager
    def get_session(self) -> Session:
        """获取数据库会话的上下文管理器"""
        if not self.SessionLocal:
            raise RuntimeError("数据库未连接，请先调用 connect() 方法")
            
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"数据库操作失败: {e}")
            raise
        finally:
            session.close()
            
    def get_session_sync(self) -> Session:
        """获取同步数据库会话（需要手动管理）"""
        if not self.SessionLocal:
            raise RuntimeError("数据库未连接，请先调用 connect() 方法")
            
        return self.SessionLocal()
        
    def is_connected(self) -> bool:
        """检查是否已连接到数据库"""
        if not self.engine:
            return False
            
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except:
            return False
            
    def get_database_info(self) -> Dict[str, Any]:
        """获取数据库信息"""
        if not self.is_connected():
            return {"connected": False}
            
        try:
            with self.engine.connect() as conn:
                # 获取数据库版本
                version_result = conn.execute(text("SELECT VERSION()"))
                version = version_result.fetchone()[0]
                
                # 获取数据库大小
                size_result = conn.execute(text(
                    f"SELECT ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'DB Size in MB' "
                    f"FROM information_schema.tables "
                    f"WHERE table_schema = '{self.config['database']}'"
                ))
                size = size_result.fetchone()[0] or 0
                
                # 获取表数量
                table_result = conn.execute(text(
                    f"SELECT COUNT(*) FROM information_schema.tables "
                    f"WHERE table_schema = '{self.config['database']}'"
                ))
                table_count = table_result.fetchone()[0]
                
                return {
                    "connected": True,
                    "database": self.config['database'],
                    "host": self.config['host'],
                    "port": self.config['port'],
                    "version": version,
                    "size_mb": float(size),
                    "table_count": table_count,
                    "retention_days": self.config.get('data_retention_days', 3)
                }
                
        except Exception as e:
            logger.error(f"获取数据库信息失败: {e}")
            return {"connected": False, "error": str(e)}
            
    def cleanup_old_data(self) -> int:
        """清理过期数据"""
        if not self.is_connected():
            return 0
            
        try:
            retention_days = self.config.get('data_retention_days', 3)
            
            with self.get_session() as session:
                # 清理过期的监控会话
                from .models import MonitoringSession
                from datetime import datetime, timedelta
                
                cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
                
                deleted_count = session.query(MonitoringSession).filter(
                    MonitoringSession.start_time < cutoff_date
                ).delete(synchronize_session=False)
                
                logger.info(f"清理了 {deleted_count} 条过期监控记录")
                return deleted_count
                
        except Exception as e:
            logger.error(f"清理过期数据失败: {e}")
            return 0
            
    def __enter__(self):
        """上下文管理器入口"""
        if not self.connect():
            raise RuntimeError("无法连接到数据库")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.disconnect()


# 全局数据库连接管理器实例
db_manager = DatabaseConnectionManager()