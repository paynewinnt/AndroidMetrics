# -*- coding: utf-8 -*-
"""
优化的配置管理模块
支持动态配置调整和性能优化参数管理
"""

import json
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import threading

logger = logging.getLogger(__name__)

class OptimizedConfigManager:
    """优化的配置管理器"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        self.configs = {}
        self.lock = threading.Lock()
        
        # 默认优化配置
        self.default_configs = {
            'performance': {
                'adb_timeout': 8,
                'adb_retry_count': 1,
                'max_parallel_commands': 8,
                'cache_timeout': 30,
                'cache_l1_size': 100,
                'cache_l2_size': 500,
                'collection_intervals': {
                    'system_performance': 3.0,
                    'app_basic': 2.0,
                    'app_detailed': 5.0,
                    'network_stats': 4.0,
                    'device_info': 60.0
                }
            },
            'database': {
                'pool_size': 10,
                'max_overflow': 20,
                'pool_timeout': 30,
                'pool_recycle': 3600,
                'batch_size': 50,
                'flush_interval': 5.0,
                'connection_pool_max_size': 20,
                'enable_batch_processing': True
            },
            'gui': {
                'update_frequency': 10,  # FPS
                'max_data_points': 1200,
                'ui_debounce_skip': 2,
                'max_updates_per_cycle': 3,
                'chart_update_interval': 3,
                'cleanup_interval': 60
            },
            'monitoring': {
                'base_sample_interval': 3.0,
                'adaptive_adjustment': True,
                'max_interval_multiplier': 2.0,
                'min_interval_multiplier': 0.5,
                'optimization_interval': 30.0,
                'enable_performance_tracking': True
            },
            'alerts': {
                'adb_collection_time_threshold': 5.0,
                'database_write_time_threshold': 2.0,
                'ui_update_time_threshold': 0.1,
                'memory_usage_threshold_mb': 500,
                'cache_hit_rate_threshold': 0.3,
                'error_rate_threshold': 0.05,
                'queue_size_threshold': 100,
                'alert_cooldown_seconds': 300
            }
        }
        
        self.ensure_config_dir()
        self.load_all_configs()
    
    def ensure_config_dir(self):
        """确保配置目录存在"""
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir, exist_ok=True)
    
    def load_all_configs(self):
        """加载所有配置"""
        configs_to_save = []
        
        with self.lock:
            for config_name, default_config in self.default_configs.items():
                config_file = os.path.join(self.config_dir, f"{config_name}.json")
                
                if os.path.exists(config_file):
                    try:
                        with open(config_file, 'r', encoding='utf-8') as f:
                            loaded_config = json.load(f)
                            # 合并默认配置和已加载配置
                            self.configs[config_name] = self._merge_configs(
                                default_config, loaded_config
                            )
                    except Exception as e:
                        logger.error(f"加载配置文件失败 {config_file}: {e}")
                        self.configs[config_name] = default_config.copy()
                        configs_to_save.append(config_name)
                else:
                    # 使用默认配置并标记需要保存
                    self.configs[config_name] = default_config.copy()
                    configs_to_save.append(config_name)
        
        # 在锁外保存配置，避免死锁
        for config_name in configs_to_save:
            try:
                self.save_config(config_name)
            except Exception as e:
                logger.error(f"保存默认配置失败 {config_name}: {e}")
    
    def _merge_configs(self, default: Dict, loaded: Dict) -> Dict:
        """递归合并配置"""
        result = default.copy()
        
        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def get_config(self, config_name: str, key: str = None) -> Any:
        """获取配置值"""
        with self.lock:
            if config_name not in self.configs:
                return None
            
            if key is None:
                return self.configs[config_name].copy()
            
            # 支持嵌套键访问，如 "database.pool_size"
            keys = key.split('.')
            value = self.configs[config_name]
            
            try:
                for k in keys:
                    value = value[k]
                return value
            except (KeyError, TypeError):
                return None
    
    def set_config(self, config_name: str, key: str, value: Any, save: bool = True):
        """设置配置值"""
        with self.lock:
            if config_name not in self.configs:
                self.configs[config_name] = {}
            
            # 支持嵌套键设置
            keys = key.split('.')
            config = self.configs[config_name]
            
            # 导航到最后一级
            for k in keys[:-1]:
                if k not in config:
                    config[k] = {}
                config = config[k]
            
            # 设置值
            config[keys[-1]] = value
            
            if save:
                self.save_config(config_name)
    
    def save_config(self, config_name: str):
        """保存配置到文件"""
        try:
            config_file = os.path.join(self.config_dir, f"{config_name}.json")
            
            with self.lock:
                config_data = self.configs.get(config_name, {})
            
            # 添加元数据
            config_data['_metadata'] = {
                'saved_at': datetime.now().isoformat(),
                'version': '1.0'
            }
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
                
            logger.debug(f"配置已保存: {config_file}")
            
        except Exception as e:
            logger.error(f"保存配置失败 {config_name}: {e}")
    
    def save_all_configs(self):
        """保存所有配置"""
        for config_name in self.configs:
            self.save_config(config_name)
    
    def get_performance_config(self) -> Dict[str, Any]:
        """获取性能配置"""
        return self.get_config('performance')
    
    def get_database_config(self) -> Dict[str, Any]:
        """获取数据库配置"""
        return self.get_config('database')
    
    def get_gui_config(self) -> Dict[str, Any]:
        """获取GUI配置"""
        return self.get_config('gui')
    
    def get_monitoring_config(self) -> Dict[str, Any]:
        """获取监控配置"""
        return self.get_config('monitoring')
    
    def get_alerts_config(self) -> Dict[str, Any]:
        """获取告警配置"""
        return self.get_config('alerts')
    
    def optimize_for_performance(self):
        """优化配置以获得最佳性能"""
        logger.info("正在优化配置以获得最佳性能...")
        
        # 性能优化配置
        performance_optimizations = {
            'performance.adb_timeout': 6,
            'performance.max_parallel_commands': 10,
            'performance.cache_timeout': 45,
            'performance.collection_intervals.system_performance': 4.0,
            'performance.collection_intervals.app_basic': 3.0,
            'database.batch_size': 75,
            'database.flush_interval': 3.0,
            'database.pool_size': 15,
            'gui.update_frequency': 8,
            'gui.ui_debounce_skip': 3,
            'monitoring.base_sample_interval': 4.0
        }
        
        for key, value in performance_optimizations.items():
            config_name, config_key = key.split('.', 1)
            self.set_config(config_name, config_key, value, save=False)
        
        self.save_all_configs()
        logger.info("性能优化配置已应用")
    
    def optimize_for_accuracy(self):
        """优化配置以获得最高精度"""
        logger.info("正在优化配置以获得最高精度...")
        
        accuracy_optimizations = {
            'performance.collection_intervals.system_performance': 2.0,
            'performance.collection_intervals.app_basic': 1.5,
            'database.batch_size': 25,
            'database.flush_interval': 2.0,
            'gui.update_frequency': 15,
            'gui.ui_debounce_skip': 1,
            'monitoring.base_sample_interval': 2.0
        }
        
        for key, value in accuracy_optimizations.items():
            config_name, config_key = key.split('.', 1)
            self.set_config(config_name, config_key, value, save=False)
        
        self.save_all_configs()
        logger.info("精度优化配置已应用")
    
    def optimize_for_resource_saving(self):
        """优化配置以节省资源"""
        logger.info("正在优化配置以节省资源...")
        
        resource_optimizations = {
            'performance.cache_timeout': 60,
            'performance.collection_intervals.system_performance': 5.0,
            'performance.collection_intervals.app_basic': 4.0,
            'performance.collection_intervals.app_detailed': 8.0,
            'database.batch_size': 100,
            'database.flush_interval': 8.0,
            'database.pool_size': 5,
            'gui.update_frequency': 5,
            'gui.max_data_points': 600,
            'gui.ui_debounce_skip': 4,
            'monitoring.base_sample_interval': 5.0
        }
        
        for key, value in resource_optimizations.items():
            config_name, config_key = key.split('.', 1)
            self.set_config(config_name, config_key, value, save=False)
        
        self.save_all_configs()
        logger.info("资源节省配置已应用")
    
    def reset_to_defaults(self, config_name: str = None):
        """重置为默认配置"""
        with self.lock:
            if config_name:
                if config_name in self.default_configs:
                    self.configs[config_name] = self.default_configs[config_name].copy()
                    self.save_config(config_name)
                    logger.info(f"已重置 {config_name} 配置为默认值")
            else:
                for name, default_config in self.default_configs.items():
                    self.configs[name] = default_config.copy()
                self.save_all_configs()
                logger.info("已重置所有配置为默认值")
    
    def export_config(self, file_path: str):
        """导出所有配置"""
        try:
            export_data = {
                'exported_at': datetime.now().isoformat(),
                'configs': {}
            }
            
            with self.lock:
                export_data['configs'] = self.configs.copy()
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"配置已导出到: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"导出配置失败: {e}")
            return False
    
    def import_config(self, file_path: str):
        """导入配置"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            if 'configs' in import_data:
                with self.lock:
                    for config_name, config_data in import_data['configs'].items():
                        if config_name in self.default_configs:
                            # 移除元数据
                            if '_metadata' in config_data:
                                del config_data['_metadata']
                            
                            self.configs[config_name] = self._merge_configs(
                                self.default_configs[config_name], config_data
                            )
                
                self.save_all_configs()
                logger.info(f"配置已从 {file_path} 导入")
                return True
            else:
                logger.error("导入文件格式不正确")
                return False
                
        except Exception as e:
            logger.error(f"导入配置失败: {e}")
            return False

# 全局配置管理实例
optimized_config = OptimizedConfigManager()