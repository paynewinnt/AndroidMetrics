import json
import os
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        self.database_config_path = os.path.join(config_dir, "database.json")
        self.monitoring_config_path = os.path.join(config_dir, "monitoring.json")
        
        self._database_config = None
        self._monitoring_config = None
        self._configs = {}  # 用于通用配置存储
        
    def load_database_config(self) -> Dict[str, Any]:
        if self._database_config is None:
            try:
                with open(self.database_config_path, 'r', encoding='utf-8') as f:
                    self._database_config = json.load(f)
                logger.info("Database configuration loaded successfully")
            except FileNotFoundError:
                logger.error(f"Database config file not found: {self.database_config_path}")
                self._database_config = self._get_default_database_config()
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in database config: {e}")
                self._database_config = self._get_default_database_config()
                
        return self._database_config.copy()
        
    def load_monitoring_config(self) -> Dict[str, Any]:
        if self._monitoring_config is None:
            try:
                with open(self.monitoring_config_path, 'r', encoding='utf-8') as f:
                    self._monitoring_config = json.load(f)
                logger.info("Monitoring configuration loaded successfully")
            except FileNotFoundError:
                logger.error(f"Monitoring config file not found: {self.monitoring_config_path}")
                self._monitoring_config = self._get_default_monitoring_config()
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in monitoring config: {e}")
                self._monitoring_config = self._get_default_monitoring_config()
                
        return self._monitoring_config.copy()
        
    def save_monitoring_config(self, config: Dict[str, Any]) -> bool:
        try:
            os.makedirs(os.path.dirname(self.monitoring_config_path), exist_ok=True)
            with open(self.monitoring_config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self._monitoring_config = config.copy()
            logger.info("Monitoring configuration saved successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to save monitoring config: {e}")
            return False
            
    def get_mysql_connection_string(self) -> str:
        db_config = self.load_database_config()
        mysql_config = db_config.get('mysql', {})
        
        connection_string = (
            f"mysql+pymysql://{mysql_config.get('username', 'root')}:"
            f"{mysql_config.get('password', '')}@"
            f"{mysql_config.get('host', 'localhost')}:"
            f"{mysql_config.get('port', 3306)}/"
            f"{mysql_config.get('database', 'android_metrics')}"
            f"?charset={mysql_config.get('charset', 'utf8mb4')}"
        )
        
        return connection_string
        
    def get_monitoring_presets(self) -> List[Dict[str, Any]]:
        config = self.load_monitoring_config()
        return config.get('presets', [])
        
    def save_monitoring_preset(self, preset: Dict[str, Any]) -> bool:
        try:
            config = self.load_monitoring_config()
            presets = config.get('presets', [])
            
            # Find existing preset with same name
            existing_index = None
            for i, existing_preset in enumerate(presets):
                if existing_preset.get('name') == preset.get('name'):
                    existing_index = i
                    break
                    
            if existing_index is not None:
                presets[existing_index] = preset
                logger.info(f"Updated existing preset: {preset.get('name')}")
            else:
                presets.append(preset)
                logger.info(f"Added new preset: {preset.get('name')}")
                
            config['presets'] = presets
            return self.save_monitoring_config(config)
            
        except Exception as e:
            logger.error(f"Failed to save monitoring preset: {e}")
            return False
            
    def delete_monitoring_preset(self, preset_name: str) -> bool:
        try:
            config = self.load_monitoring_config()
            presets = config.get('presets', [])
            
            original_length = len(presets)
            presets = [p for p in presets if p.get('name') != preset_name]
            
            if len(presets) < original_length:
                config['presets'] = presets
                self.save_monitoring_config(config)
                logger.info(f"Deleted preset: {preset_name}")
                return True
            else:
                logger.warning(f"Preset not found: {preset_name}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete monitoring preset: {e}")
            return False
            
    def get_adb_commands(self) -> Dict[str, str]:
        config = self.load_monitoring_config()
        return config.get('adb', {}).get('commands', {})
        
    def get_monitoring_settings(self) -> Dict[str, Any]:
        config = self.load_monitoring_config()
        return config.get('monitoring', {})
        
    def get_thresholds(self) -> Dict[str, float]:
        config = self.load_monitoring_config()
        return config.get('thresholds', {})
        
    def get_data_retention_days(self) -> int:
        db_config = self.load_database_config()
        return db_config.get('data_retention', {}).get('days', 3)
        
    def _get_default_database_config(self) -> Dict[str, Any]:
        return {
            "mysql": {
                "host": "localhost",
                "port": 3306,
                "username": "metrics_user",
                "password": "metrics_pass",
                "database": "android_metrics",
                "charset": "utf8mb4"
            },
            "connection_pool": {
                "pool_size": 10,
                "max_overflow": 20,
                "pool_timeout": 30,
                "pool_recycle": 3600
            },
            "data_retention": {
                "days": 3,
                "auto_cleanup": True
            }
        }
        
    def _get_default_monitoring_config(self) -> Dict[str, Any]:
        return {
            "monitoring": {
                "sample_interval": 2,
                "duration_minutes": 60,
                "max_apps": 5,
                "auto_start": False
            },
            "thresholds": {
                "cpu_max": 90,
                "memory_max": 80,
                "network_max": 1000,
                "fps_min": 30
            },
            "presets": [
                {
                    "name": "Default",
                    "packages": [],
                    "sample_interval": 2,
                    "duration_minutes": 60
                }
            ],
            "adb": {
                "timeout": 10,
                "retry_count": 3,
                "commands": {
                    "list_packages": "shell pm list packages -3",
                    "cpu_info": "shell dumpsys cpuinfo",
                    "mem_info": "shell dumpsys meminfo",
                    "battery_stats": "shell dumpsys batterystats",
                    "network_stats": "shell cat /proc/net/xt_qtaguid/stats"
                }
            }
        }
        
    def reload_configs(self):
        self._database_config = None
        self._monitoring_config = None
        logger.info("Configuration cache cleared, will reload on next access")
        
    def set(self, section: str, config: Dict[str, Any]) -> None:
        """设置配置"""
        self._configs[section] = config
        
    def get(self, section: str, default: Any = None) -> Any:
        """获取配置"""
        return self._configs.get(section, default)