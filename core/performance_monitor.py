# -*- coding: utf-8 -*-
"""
性能监控模块
负责监控和分析系统各组件的性能表现
"""

import time
import threading
from collections import defaultdict, deque
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import logging
import json
import os

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.metrics = defaultdict(lambda: deque(maxlen=max_history))
        self.alerts = []
        self.thresholds = {
            'adb_collection_time': 5.0,         # ADB收集时间阈值(秒)
            'database_write_time': 2.0,         # 数据库写入时间阈值(秒)
            'ui_update_time': 0.1,              # UI更新时间阈值(秒)
            'memory_usage_mb': 500,             # 内存使用阈值(MB)
            'cache_hit_rate': 0.3,              # 缓存命中率下限
            'error_rate': 0.05,                 # 错误率上限
            'queue_size': 100                   # 队列大小阈值
        }
        
        self.lock = threading.Lock()
        self.start_time = time.time()
        
        # 性能统计
        self.performance_stats = {
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'avg_response_time': 0.0,
            'max_response_time': 0.0,
            'min_response_time': float('inf')
        }
        
    def record_metric(self, metric_name: str, value: float, timestamp: float = None):
        """记录性能指标"""
        if timestamp is None:
            timestamp = time.time()
            
        with self.lock:
            self.metrics[metric_name].append({
                'value': value,
                'timestamp': timestamp
            })
            
            # 更新统计信息
            self._update_stats(metric_name, value)
            
            # 检查阈值
            self._check_threshold(metric_name, value, timestamp)
    
    def _update_stats(self, metric_name: str, value: float):
        """更新统计信息"""
        if metric_name.endswith('_time'):
            self.performance_stats['total_operations'] += 1
            
            if value > 0:
                self.performance_stats['successful_operations'] += 1
                
                # 更新响应时间统计
                total_ops = self.performance_stats['successful_operations']
                current_avg = self.performance_stats['avg_response_time']
                self.performance_stats['avg_response_time'] = (
                    (current_avg * (total_ops - 1) + value) / total_ops
                )
                
                self.performance_stats['max_response_time'] = max(
                    self.performance_stats['max_response_time'], value
                )
                self.performance_stats['min_response_time'] = min(
                    self.performance_stats['min_response_time'], value
                )
            else:
                self.performance_stats['failed_operations'] += 1
    
    def _check_threshold(self, metric_name: str, value: float, timestamp: float):
        """检查阈值并生成告警"""
        if metric_name in self.thresholds:
            threshold = self.thresholds[metric_name]
            
            # 根据指标类型判断告警条件
            alert_triggered = False
            alert_type = "warning"
            
            if metric_name in ['adb_collection_time', 'database_write_time', 'ui_update_time']:
                if value > threshold:
                    alert_triggered = True
                    alert_type = "performance"
            elif metric_name == 'cache_hit_rate':
                if value < threshold:
                    alert_triggered = True
                    alert_type = "efficiency"
            elif metric_name in ['error_rate', 'queue_size']:
                if value > threshold:
                    alert_triggered = True
                    alert_type = "error" if metric_name == 'error_rate' else "capacity"
            elif metric_name == 'memory_usage_mb':
                if value > threshold:
                    alert_triggered = True
                    alert_type = "resource"
            
            if alert_triggered:
                self._create_alert(metric_name, value, threshold, alert_type, timestamp)
    
    def _create_alert(self, metric_name: str, value: float, threshold: float, 
                     alert_type: str, timestamp: float):
        """创建告警"""
        alert = {
            'timestamp': timestamp,
            'metric': metric_name,
            'value': value,
            'threshold': threshold,
            'type': alert_type,
            'message': f"{metric_name} 超出阈值: {value:.2f} > {threshold:.2f}"
        }
        
        # 避免重复告警（5分钟内相同告警只记录一次）
        recent_alerts = [a for a in self.alerts 
                        if a['metric'] == metric_name and 
                        timestamp - a['timestamp'] < 300]
        
        if not recent_alerts:
            self.alerts.append(alert)
            logger.warning(f"性能告警: {alert['message']}")
            
            # 保持告警历史数量
            if len(self.alerts) > 100:
                self.alerts = self.alerts[-50:]
    
    def get_metric_summary(self, metric_name: str, time_window: int = 300) -> Dict[str, Any]:
        """获取指标摘要信息"""
        with self.lock:
            if metric_name not in self.metrics:
                return {}
                
            current_time = time.time()
            cutoff_time = current_time - time_window
            
            # 获取时间窗口内的数据
            recent_data = [
                item for item in self.metrics[metric_name]
                if item['timestamp'] >= cutoff_time
            ]
            
            if not recent_data:
                return {}
            
            values = [item['value'] for item in recent_data]
            
            return {
                'metric_name': metric_name,
                'count': len(values),
                'avg': sum(values) / len(values),
                'min': min(values),
                'max': max(values),
                'latest': values[-1] if values else 0,
                'time_window_seconds': time_window,
                'threshold': self.thresholds.get(metric_name)
            }
    
    def get_all_metrics_summary(self, time_window: int = 300) -> Dict[str, Any]:
        """获取所有指标的摘要"""
        summary = {}
        
        with self.lock:
            for metric_name in self.metrics.keys():
                summary[metric_name] = self.get_metric_summary(metric_name, time_window)
        
        return summary
    
    def get_recent_alerts(self, count: int = 10) -> List[Dict[str, Any]]:
        """获取最近的告警"""
        with self.lock:
            return self.alerts[-count:] if self.alerts else []
    
    def get_performance_report(self) -> Dict[str, Any]:
        """生成性能报告"""
        current_time = time.time()
        uptime = current_time - self.start_time
        
        with self.lock:
            report = {
                'generated_at': datetime.now().isoformat(),
                'uptime_seconds': uptime,
                'uptime_hours': uptime / 3600,
                'overall_stats': self.performance_stats.copy(),
                'metrics_summary': self.get_all_metrics_summary(),
                'recent_alerts': self.get_recent_alerts(20),
                'thresholds': self.thresholds.copy()
            }
            
            # 计算整体健康分数
            report['health_score'] = self._calculate_health_score()
            
            return report
    
    def _calculate_health_score(self) -> float:
        """计算系统健康分数 (0-100)"""
        score = 100.0
        
        # 基于错误率扣分
        total_ops = self.performance_stats['total_operations']
        if total_ops > 0:
            error_rate = self.performance_stats['failed_operations'] / total_ops
            score -= min(error_rate * 100, 30)  # 最多扣30分
        
        # 基于响应时间扣分
        avg_time = self.performance_stats['avg_response_time']
        if avg_time > 2.0:  # 超过2秒
            score -= min((avg_time - 2.0) * 10, 20)  # 最多扣20分
        
        # 基于告警数量扣分
        recent_alerts = len([
            a for a in self.alerts 
            if time.time() - a['timestamp'] < 3600  # 最近1小时
        ])
        score -= min(recent_alerts * 2, 20)  # 最多扣20分
        
        return max(0.0, score)
    
    def set_threshold(self, metric_name: str, threshold: float):
        """设置告警阈值"""
        with self.lock:
            self.thresholds[metric_name] = threshold
            logger.info(f"设置 {metric_name} 阈值为 {threshold}")
    
    def clear_metrics(self, metric_name: str = None):
        """清理指标数据"""
        with self.lock:
            if metric_name:
                if metric_name in self.metrics:
                    self.metrics[metric_name].clear()
            else:
                self.metrics.clear()
                self.alerts.clear()
                self.performance_stats = {
                    'total_operations': 0,
                    'successful_operations': 0,
                    'failed_operations': 0,
                    'avg_response_time': 0.0,
                    'max_response_time': 0.0,
                    'min_response_time': float('inf')
                }
    
    def export_metrics(self, file_path: str):
        """导出指标数据"""
        try:
            report = self.get_performance_report()
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
                
            logger.info(f"性能指标已导出到: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"导出性能指标失败: {e}")
            return False

class PerformanceDecorator:
    """性能监控装饰器"""
    
    def __init__(self, monitor: PerformanceMonitor, metric_name: str):
        self.monitor = monitor
        self.metric_name = metric_name
    
    def __call__(self, func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                self.monitor.record_metric(self.metric_name, execution_time)
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                self.monitor.record_metric(f"{self.metric_name}_error", execution_time)
                raise
        return wrapper

# 全局性能监控实例
performance_monitor = PerformanceMonitor()

def monitor_performance(metric_name: str):
    """性能监控装饰器函数"""
    return PerformanceDecorator(performance_monitor, metric_name)