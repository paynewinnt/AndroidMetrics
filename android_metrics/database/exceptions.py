# -*- coding: utf-8 -*-
"""
数据库异常处理模块
定义了数据库操作相关的异常类和错误处理工具
"""

import logging
import traceback
from typing import Any, Dict, Optional, Callable
from functools import wraps
from contextlib import contextmanager

from sqlalchemy.exc import (
    SQLAlchemyError, OperationalError, IntegrityError, 
    DataError, DatabaseError, DisconnectionError
)

logger = logging.getLogger(__name__)

# ==================== 自定义异常类 ====================

class DatabaseException(Exception):
    """数据库操作基础异常"""
    
    def __init__(self, message: str, error_code: str = None, 
                 original_error: Exception = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.original_error = original_error
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'error_type': self.__class__.__name__,
            'message': self.message,
            'error_code': self.error_code,
            'original_error': str(self.original_error) if self.original_error else None
        }

class ConnectionError(DatabaseException):
    """数据库连接异常"""
    
    def __init__(self, message: str = "数据库连接失败", **kwargs):
        super().__init__(message, error_code="DB_CONNECTION_ERROR", **kwargs)

class ConfigurationError(DatabaseException):
    """数据库配置异常"""
    
    def __init__(self, message: str = "数据库配置错误", **kwargs):
        super().__init__(message, error_code="DB_CONFIG_ERROR", **kwargs)

class DataValidationError(DatabaseException):
    """数据验证异常"""
    
    def __init__(self, message: str = "数据验证失败", **kwargs):
        super().__init__(message, error_code="DATA_VALIDATION_ERROR", **kwargs)

class SessionNotFoundError(DatabaseException):
    """监控会话未找到异常"""
    
    def __init__(self, session_id: int, **kwargs):
        message = f"监控会话 {session_id} 未找到"
        super().__init__(message, error_code="SESSION_NOT_FOUND", **kwargs)
        self.session_id = session_id

class DataStorageError(DatabaseException):
    """数据存储异常"""
    
    def __init__(self, message: str = "数据存储失败", **kwargs):
        super().__init__(message, error_code="DATA_STORAGE_ERROR", **kwargs)

class QueryExecutionError(DatabaseException):
    """查询执行异常"""
    
    def __init__(self, message: str = "查询执行失败", **kwargs):
        super().__init__(message, error_code="QUERY_EXECUTION_ERROR", **kwargs)

class MaintenanceError(DatabaseException):
    """数据库维护异常"""
    
    def __init__(self, message: str = "数据库维护失败", **kwargs):
        super().__init__(message, error_code="MAINTENANCE_ERROR", **kwargs)

# ==================== 错误处理工具 ====================

class DatabaseErrorHandler:
    """数据库错误处理器"""
    
    @staticmethod
    def handle_sqlalchemy_error(error: SQLAlchemyError) -> DatabaseException:
        """处理SQLAlchemy异常"""
        error_msg = str(error)
        
        if isinstance(error, OperationalError):
            if "Access denied" in error_msg:
                return ConnectionError("数据库访问被拒绝，请检查用户名和密码", original_error=error)
            elif "Unknown database" in error_msg:
                return ConnectionError("数据库不存在", original_error=error)
            elif "Can't connect to MySQL server" in error_msg:
                return ConnectionError("无法连接到MySQL服务器", original_error=error)
            elif "Lost connection" in error_msg:
                return ConnectionError("数据库连接丢失", original_error=error)
            else:
                return ConnectionError(f"数据库操作错误: {error_msg}", original_error=error)
                
        elif isinstance(error, IntegrityError):
            if "Duplicate entry" in error_msg:
                return DataValidationError("数据重复，违反唯一约束", original_error=error)
            elif "foreign key constraint" in error_msg.lower():
                return DataValidationError("外键约束违反", original_error=error)
            else:
                return DataValidationError(f"数据完整性错误: {error_msg}", original_error=error)
                
        elif isinstance(error, DataError):
            return DataValidationError(f"数据格式错误: {error_msg}", original_error=error)
            
        elif isinstance(error, DisconnectionError):
            return ConnectionError(f"数据库连接断开: {error_msg}", original_error=error)
            
        else:
            return DatabaseException(f"数据库未知错误: {error_msg}", 
                                   error_code="DB_UNKNOWN_ERROR", original_error=error)
    
    @staticmethod
    def log_error(error: Exception, context: str = ""):
        """记录错误日志"""
        error_info = {
            'error_type': type(error).__name__,
            'error_message': str(error),
            'context': context,
            'traceback': traceback.format_exc()
        }
        
        if isinstance(error, DatabaseException):
            error_info.update(error.to_dict())
        
        logger.error(f"数据库错误 - {context}: {error_info}")
    
    @staticmethod
    def create_error_response(error: Exception, operation: str = "") -> Dict[str, Any]:
        """创建统一的错误响应"""
        if isinstance(error, DatabaseException):
            return {
                'success': False,
                'error': error.to_dict(),
                'operation': operation
            }
        else:
            return {
                'success': False,
                'error': {
                    'error_type': type(error).__name__,
                    'message': str(error),
                    'error_code': 'UNKNOWN_ERROR'
                },
                'operation': operation
            }

# ==================== 装饰器 ====================

def handle_database_errors(operation_name: str = "", 
                          return_value: Any = None,
                          raise_on_error: bool = False):
    """数据库错误处理装饰器"""
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
                
            except DatabaseException as e:
                # 自定义数据库异常，直接处理
                context = operation_name or func.__name__
                DatabaseErrorHandler.log_error(e, context)
                
                if raise_on_error:
                    raise e
                
                return DatabaseErrorHandler.create_error_response(e, context)
                
            except SQLAlchemyError as e:
                # SQLAlchemy异常，转换为自定义异常
                db_error = DatabaseErrorHandler.handle_sqlalchemy_error(e)
                context = operation_name or func.__name__
                DatabaseErrorHandler.log_error(db_error, context)
                
                if raise_on_error:
                    raise db_error
                
                return DatabaseErrorHandler.create_error_response(db_error, context)
                
            except Exception as e:
                # 其他异常
                context = operation_name or func.__name__
                DatabaseErrorHandler.log_error(e, context)
                
                if raise_on_error:
                    raise DatabaseException(f"操作失败: {str(e)}", 
                                          error_code="OPERATION_ERROR", 
                                          original_error=e)
                
                return DatabaseErrorHandler.create_error_response(e, context)
        
        return wrapper
    return decorator

def validate_session_id(func: Callable) -> Callable:
    """验证会话ID的装饰器"""
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        # 查找session_id参数
        session_id = None
        
        # 检查位置参数
        if len(args) > 1 and isinstance(args[1], int):
            session_id = args[1]
        
        # 检查关键字参数
        if 'session_id' in kwargs:
            session_id = kwargs['session_id']
        
        if session_id is not None:
            if not isinstance(session_id, int) or session_id <= 0:
                raise DataValidationError(f"无效的会话ID: {session_id}")
        
        return func(*args, **kwargs)
    
    return wrapper

def require_connection(func: Callable) -> Callable:
    """要求数据库连接的装饰器"""
    
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if hasattr(self, 'db_manager'):
            if not self.db_manager.is_connected():
                try:
                    success = self.db_manager.connect()
                    if not success:
                        raise ConnectionError("无法建立数据库连接")
                except Exception as e:
                    raise ConnectionError("数据库连接失败", original_error=e)
        
        return func(self, *args, **kwargs)
    
    return wrapper

# ==================== 上下文管理器 ====================

@contextmanager
def database_transaction(db_manager, operation_name: str = ""):
    """数据库事务上下文管理器"""
    if not db_manager.is_connected():
        success = db_manager.connect()
        if not success:
            raise ConnectionError("无法建立数据库连接")
    
    session = None
    try:
        session = db_manager.get_session_sync()
        yield session
        session.commit()
        
    except SQLAlchemyError as e:
        if session:
            session.rollback()
        db_error = DatabaseErrorHandler.handle_sqlalchemy_error(e)
        DatabaseErrorHandler.log_error(db_error, operation_name)
        raise db_error
        
    except Exception as e:
        if session:
            session.rollback()
        DatabaseErrorHandler.log_error(e, operation_name)
        raise DatabaseException(f"事务执行失败: {str(e)}", 
                              error_code="TRANSACTION_ERROR", 
                              original_error=e)
    finally:
        if session:
            session.close()

@contextmanager
def safe_database_operation(operation_name: str = ""):
    """安全的数据库操作上下文管理器"""
    try:
        yield
    except DatabaseException as e:
        DatabaseErrorHandler.log_error(e, operation_name)
        raise
    except SQLAlchemyError as e:
        db_error = DatabaseErrorHandler.handle_sqlalchemy_error(e)
        DatabaseErrorHandler.log_error(db_error, operation_name)
        raise db_error
    except Exception as e:
        DatabaseErrorHandler.log_error(e, operation_name)
        raise DatabaseException(f"操作失败: {str(e)}", 
                              error_code="OPERATION_ERROR", 
                              original_error=e)

# ==================== 工具函数 ====================

def validate_data_dict(data: Dict[str, Any], required_fields: list = None, 
                      field_types: Dict[str, type] = None) -> None:
    """验证数据字典"""
    if not isinstance(data, dict):
        raise DataValidationError("数据必须是字典格式")
    
    # 检查必需字段
    if required_fields:
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            raise DataValidationError(f"缺少必需字段: {missing_fields}")
    
    # 检查字段类型
    if field_types:
        for field, expected_type in field_types.items():
            if field in data and data[field] is not None:
                if not isinstance(data[field], expected_type):
                    raise DataValidationError(
                        f"字段 {field} 类型错误，期望 {expected_type.__name__}，"
                        f"实际 {type(data[field]).__name__}"
                    )

def sanitize_string_input(value: str, max_length: int = None) -> str:
    """清理字符串输入"""
    if value is None:
        return None
    
    if not isinstance(value, str):
        value = str(value)
    
    # 移除危险字符
    value = value.strip()
    
    if max_length and len(value) > max_length:
        raise DataValidationError(f"字符串长度超过限制: {max_length}")
    
    return value

def create_success_response(data: Any = None, message: str = "操作成功") -> Dict[str, Any]:
    """创建成功响应"""
    response = {
        'success': True,
        'message': message
    }
    
    if data is not None:
        response['data'] = data
    
    return response