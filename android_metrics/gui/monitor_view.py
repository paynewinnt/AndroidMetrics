# -*- coding: utf-8 -*-
import sys
import os
import time
from datetime import datetime
from collections import defaultdict, deque
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                           QScrollArea, QFrame, QGroupBox, QGridLayout,
                           QTableWidget, QTableWidgetItem, QPushButton,
                           QProgressBar, QTextEdit, QSplitter, QTabWidget,
                           QComboBox, QCheckBox, QMessageBox, QFileDialog)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
from PyQt5.QtGui import QFont, QColor
import queue
import threading
import logging

logger = logging.getLogger(__name__)

try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    print("Warning: pyqtgraph not available, using basic charts")

try:
    from .chart_widgets import AdvancedChartWidget, MultiSeriesChartManager
    CHART_WIDGETS_AVAILABLE = True
except ImportError:
    try:
        from gui.chart_widgets import AdvancedChartWidget, MultiSeriesChartManager
        CHART_WIDGETS_AVAILABLE = True
    except ImportError:
        print("Warning: chart_widgets not available")
        CHART_WIDGETS_AVAILABLE = False
        class AdvancedChartWidget:
            def __init__(self, *args, **kwargs): pass
            def add_data_point(self, *args, **kwargs): pass
        class MultiSeriesChartManager:
            def __init__(self, *args, **kwargs): pass

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入数据存储相关模块
try:
    from database.connection import db_manager
    from database.data_storage import data_storage
    DATABASE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Database modules not available: {e}")
    DATABASE_AVAILABLE = False
    # 创建兼容的空对象
    class MockDBManager:
        def is_connected(self): return False
        def connect(self): return False
    class MockDataStorage:
        def store_monitoring_data(self, *args, **kwargs): return False
    db_manager = MockDBManager()
    data_storage = MockDataStorage()

# 导入导出工具（可选）
try:
    from utils.export import data_exporter
    EXPORT_AVAILABLE = True
except ImportError:
    EXPORT_AVAILABLE = False
    class MockExporter:
        def export_data(self, *args, **kwargs): return False
    data_exporter = MockExporter()

class CircularBuffer:
    """环形缓冲区用于存储历史数据"""
    def __init__(self, max_size: int = 1000):
        self.buffer = deque(maxlen=max_size)
        self.timestamps = deque(maxlen=max_size)
        self.max_size = max_size
        
    def add_data(self, timestamp: float, data):
        """添加数据"""
        self.buffer.append(data)
        self.timestamps.append(timestamp)
        
    def get_recent_data(self, seconds: int = 300):
        """获取最近N秒的数据"""
        if not self.timestamps:
            return [], []
            
        cutoff_time = time.time() - seconds
        recent_data = []
        recent_timestamps = []
        
        for i, ts in enumerate(self.timestamps):
            if ts >= cutoff_time:
                recent_data.extend(list(self.buffer)[i:])
                recent_timestamps.extend(list(self.timestamps)[i:])
                break
                
        return recent_timestamps, recent_data
    
    def clear(self):
        """清空缓冲区"""
        self.buffer.clear()
        self.timestamps.clear()
    
    def size(self):
        """获取当前大小"""
        return len(self.buffer)

class OptimizedDataCollectionWorker(QThread):
    """优化的数据收集工作线程"""
    data_collected = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, adb_collector, config):
        super().__init__()
        self.adb_collector = adb_collector
        self.config = config
        self.running = False
        
        # 优化采集间隔
        self.base_interval = self.config.get('sample_interval', 5)  # 基础间隔设置为5秒
        self.adaptive_interval = self.base_interval
        
        # 性能监控
        self.collection_times = deque(maxlen=10)
        self.error_count = 0
        self.last_optimization = time.time()
        
    def run(self):
        """运行数据收集"""
        self.running = True
        
        while self.running:
            collection_start_time = time.time()
            
            try:
                # 智能数据收集 - 使用批量方法
                data = self._collect_data_batch()
                
                if data:
                    self.data_collected.emit(data)
                    self.error_count = 0
                
                # 记录收集时间用于自适应优化
                collection_time = time.time() - collection_start_time
                self.collection_times.append(collection_time)
                
                # 自适应间隔调整
                self._adjust_interval()
                
                # 计算休眠时间
                remaining_time = self.adaptive_interval - collection_time
                if remaining_time > 0:
                    time.sleep(remaining_time)
                else:
                    # 收集时间过长，短暂休眠避免CPU占用过高
                    time.sleep(0.1)
                
            except Exception as e:
                self.error_count += 1
                self.error_occurred.emit(str(e))
                
                # 错误后增加休眠时间
                sleep_time = min(5.0, 0.5 * self.error_count)
                time.sleep(sleep_time)
    
    def _collect_data_batch(self) -> dict:
        """批量收集数据"""
        data = {
            'timestamp': datetime.now(),
            'system': None,
            'apps': []
        }
        
        try:
            # 收集系统数据
            if self.config['metrics'].get('system', False):
                data['system'] = self.adb_collector.get_system_performance()
            
            # 批量收集应用数据
            selected_apps = self.config.get('selected_apps', [])
            if selected_apps:
                package_names = [app['package_name'] for app in selected_apps]
                
                # 使用批量收集方法
                if hasattr(self.adb_collector, 'get_multiple_app_performance'):
                    multi_app_data = self.adb_collector.get_multiple_app_performance(package_names)
                    
                    for app in selected_apps:
                        package_name = app['package_name']
                        if package_name in multi_app_data:
                            app_data = multi_app_data[package_name]
                            app_data['app_info'] = app
                            data['apps'].append(app_data)
                else:
                    # 降级到单个收集
                    for app in selected_apps:
                        app_data = self.adb_collector.get_app_performance(app['package_name'])
                        app_data['app_info'] = app
                        data['apps'].append(app_data)
            
            return data
            
        except Exception as e:
            raise e
    
    def _adjust_interval(self):
        """自适应调整采集间隔"""
        current_time = time.time()
        
        # 每30秒优化一次间隔
        if current_time - self.last_optimization < 30:
            return
            
        if len(self.collection_times) < 5:
            return
            
        avg_collection_time = sum(self.collection_times) / len(self.collection_times)
        
        # 根据平均收集时间调整间隔
        if avg_collection_time > self.base_interval * 0.8:
            # 收集时间过长，增加间隔
            self.adaptive_interval = min(self.adaptive_interval * 1.2, self.base_interval * 2)
        elif avg_collection_time < self.base_interval * 0.3:
            # 收集时间较短，可以缩短间隔
            self.adaptive_interval = max(self.adaptive_interval * 0.9, self.base_interval * 0.5)
        
        self.last_optimization = current_time
    
    def stop(self):
        """停止数据收集"""
        self.running = False
    
    def get_performance_stats(self):
        """获取性能统计"""
        if not self.collection_times:
            return {}
            
        return {
            'avg_collection_time': sum(self.collection_times) / len(self.collection_times),
            'max_collection_time': max(self.collection_times),
            'current_interval': self.adaptive_interval,
            'error_count': self.error_count
        }

# 保持向后兼容
DataCollectionWorker = OptimizedDataCollectionWorker

class MetricDisplayWidget(QWidget):
    """Single metric display component"""
    def __init__(self, title, unit="", color="#2196F3"):
        super().__init__()
        self.title = title
        self.unit = unit
        self.color = color
        self.current_value = 0
        self.max_value = 0
        self.avg_value = 0
        self.sample_count = 0
        
        self.init_ui()
        # 1600px固定窗口，5个指标有充足空间显示 - 与固定尺寸保持一致
        # 注意：后面会设置固定尺寸160x140，这里的设置会被覆盖
        
    def init_ui(self):
        """Initialize UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)  # 水平布局节省空间后恢复边距
        layout.setSpacing(3)  # 恢复舒适的组件间距
        
        # Title
        title_label = QLabel(self.title)
        title_label.setFont(QFont("Arial", 10, QFont.Bold))  # 1600px窗口下恢复字体大小
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setWordWrap(True)
        title_label.setMaximumHeight(27)  # 水平布局后可以适当增加标题高度
        layout.addWidget(title_label)
        
        # Current value
        self.current_label = QLabel("0" + self.unit)
        self.current_label.setFont(QFont("Arial", 13, QFont.Bold))  # 恢复较大字体，高度160px足够显示
        self.current_label.setAlignment(Qt.AlignCenter)
        self.current_label.setStyleSheet(f"color: {self.color}; padding: 0px;")  # 去除padding节省空间
        layout.addWidget(self.current_label)
        
        # Statistics in horizontal layout - 水平布局节省垂直空间
        stats_widget = QWidget()
        stats_layout = QHBoxLayout(stats_widget)
        stats_layout.setContentsMargins(0, 2, 0, 2)  # 减少左右边距
        stats_layout.setSpacing(1)  # 进一步减少最大和平均信息间距
        
        # Use appropriate fonts for statistics
        font_small = QFont("Arial", 9)
        
        # 最大值信息
        max_container = QWidget()
        max_container.setMinimumWidth(65)  # 设置最小宽度给更多显示空间
        max_layout = QHBoxLayout(max_container)
        max_layout.setContentsMargins(0, 0, 0, 0)
        max_layout.setSpacing(0)  # 减少"最大:"内部间距
        
        max_label_text = QLabel("最大:")
        max_label_text.setFont(font_small)
        max_label_text.setMinimumWidth(22)  # 固定标签宽度
        max_layout.addWidget(max_label_text)
        
        self.max_label = QLabel("0" + self.unit)
        self.max_label.setFont(font_small)
        self.max_label.setStyleSheet("color: #f44336;")
        self.max_label.setMinimumWidth(43)  # 设置数值显示的最小宽度
        max_layout.addWidget(self.max_label)
        
        # 平均值信息
        avg_container = QWidget()
        avg_container.setMinimumWidth(65)  # 设置最小宽度给更多显示空间
        avg_layout = QHBoxLayout(avg_container)
        avg_layout.setContentsMargins(0, 0, 0, 0)
        avg_layout.setSpacing(0)  # 减少"平均:"内部间距
        
        avg_label_text = QLabel("平均:")
        avg_label_text.setFont(font_small)
        avg_label_text.setMinimumWidth(22)  # 固定标签宽度
        avg_layout.addWidget(avg_label_text)
        
        self.avg_label = QLabel("0" + self.unit)
        self.avg_label.setFont(font_small)
        self.avg_label.setStyleSheet("color: #ff9800;")
        self.avg_label.setMinimumWidth(43)  # 设置数值显示的最小宽度
        avg_layout.addWidget(self.avg_label)
        
        # 添加到主统计布局 - 不添加弹性空间让内容更紧凑
        stats_layout.addWidget(max_container)
        stats_layout.addWidget(avg_container)
        
        layout.addWidget(stats_widget)
        
        # Progress bar (optional)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(15)
        layout.addWidget(self.progress_bar)
        
        # Set fixed size for consistent layout with sufficient height for both 最大 and 平均
        self.setFixedSize(160, 160)  # 进一步增加高度以确保统计信息完整显示
        
        # Styling
        self.setStyleSheet("""
            QWidget {
                border: 2px solid #d0d0d0;
                border-radius: 8px;
                background-color: white;
                margin: 1px;
            }
            QLabel {
                border: none;
                background-color: transparent;
            }
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: #f0f0f0;
            }
            QProgressBar::chunk {
                border-radius: 3px;
            }
        """)
        
    def update_value(self, value):
        """Update value with smart refresh control"""
        if value is None:
            return
            
        old_value = self.current_value
        self.current_value = value
        self.sample_count += 1
        
        # Update max value
        if value > self.max_value:
            self.max_value = value
            
        # Update average value
        if self.sample_count == 1:
            self.avg_value = value
        else:
            self.avg_value = (self.avg_value * (self.sample_count - 1) + value) / self.sample_count
        
        # Smart UI update - only update if significant change or sufficient time passed
        should_update = self._should_update_display(old_value, value)
        
        if should_update:
            self._update_display_elements(value)
    
    def _should_update_display(self, old_value, new_value):
        """Determine if display should be updated based on value change"""
        import time
        
        # Initialize last update time if not exists
        if not hasattr(self, '_last_update_time'):
            self._last_update_time = 0
            
        current_time = time.time()
        time_since_update = current_time - self._last_update_time
        
        # Always update if enough time has passed (max 10 seconds)
        if time_since_update > 10:
            self._last_update_time = current_time
            return True
            
        # Don't update too frequently (min 0.5 seconds)
        if time_since_update < 0.5:
            return False
            
        # Update if significant change (>= 5% change or 0.1 absolute change)
        if old_value is not None:
            abs_change = abs(new_value - old_value)
            rel_change = abs_change / max(abs(old_value), 0.1) if old_value != 0 else abs_change
            
            if abs_change >= 0.1 or rel_change >= 0.05:
                self._last_update_time = current_time
                return True
                
        return False
    
    def _update_display_elements(self, value):
        """Update the actual display elements"""
        # Update display
        self.current_label.setText(f"{value:.1f}{self.unit}")
        self.max_label.setText(f"{self.max_value:.1f}{self.unit}")
        self.avg_label.setText(f"{self.avg_value:.1f}{self.unit}")
        
        # Update progress bar (if applicable)
        if self.unit == "%" and self.progress_bar.isVisible():
            self.progress_bar.setValue(int(value))
            
    def set_progress_visible(self, visible):
        """Set progress bar visibility"""
        self.progress_bar.setVisible(visible)

class OptimizedMonitorViewWidget(QWidget):
    """优化的主监控显示界面"""
    def __init__(self):
        super().__init__()
        self.selected_apps = []
        self.monitoring_active = False
        self.data_worker = None
        self.metric_widgets = {}
        self.chart_widgets = {}
        self.chart_manager = None
        
        # 数据存储相关
        self.current_session_id = None
        self.enable_data_storage = DATABASE_AVAILABLE
        
        # 优化的数据管理
        self.data_buffers = {
            'system': CircularBuffer(max_size=240),  # 20分钟数据(每5秒一次)
            'apps': defaultdict(lambda: CircularBuffer(max_size=240))
        }
        
        # GUI更新优化
        self.update_queue = queue.Queue(maxsize=100)
        self.ui_update_timer = QTimer()
        self.ui_update_timer.timeout.connect(self.process_ui_updates)
        self.ui_update_timer.start(100)  # 10 FPS更新频率
        
        # 统计信息更新定时器
        self.stats_update_timer = QTimer()
        self.stats_update_timer.timeout.connect(self.update_statistics)
        self.stats_update_timer.start(1000)  # 每秒更新一次
        
        # 性能监控
        self.update_counts = defaultdict(int)
        self.last_cleanup = time.time()
        
        # 去抖动计数器
        self.update_skip_counter = 0
        self.max_skip_updates = 2  # 每3次更新显示一次
        
        self.init_ui()
    
    def process_ui_updates(self):
        """批量处理UI更新，避免阻塞"""
        updates_processed = 0
        max_updates_per_cycle = 3  # 每次最多处理3个更新
        
        while not self.update_queue.empty() and updates_processed < max_updates_per_cycle:
            try:
                update_data = self.update_queue.get_nowait()
                self._update_ui_components(update_data)
                updates_processed += 1
            except queue.Empty:
                break
            except Exception as e:
                print(f"UI更新错误: {e}")
        
        # 定期清理过期数据
        current_time = time.time()
        if current_time - self.last_cleanup > 60:  # 每分钟清理一次
            self._cleanup_expired_data()
            self.last_cleanup = current_time
    
    def _update_ui_components(self, data):
        """更新UI组件"""
        try:
            # 去抖动处理
            self.update_skip_counter += 1
            if self.update_skip_counter < self.max_skip_updates:
                return
            self.update_skip_counter = 0
            
            timestamp = data['timestamp']
            
            # 更新系统指标
            if data.get('system'):
                self._update_system_metrics(data['system'], timestamp)
            
            # 更新应用指标  
            if data.get('apps'):
                self._update_app_metrics(data['apps'], timestamp)
                
        except Exception as e:
            print(f"UI组件更新失败: {e}")
    
    def _update_system_metrics(self, system_data, timestamp):
        """更新系统指标显示"""
        # 保存最新的系统数据供应用内存百分比计算使用
        self.latest_system_data = system_data
        
        # 存储到环形缓冲区
        self.data_buffers['system'].add_data(timestamp.timestamp(), system_data)
        
        # 更新度量显示组件
        metric_mapping = {
            'cpu_usage': 'system_CPU使用率：Total',
            'cpu_user': 'system_CPU使用率：用户态',
            'memory_usage_percent': 'system_内存使用', 
            'battery_level': 'system_电池电量',
            'network_rx': 'system_网络接收', 
            'network_tx': 'system_网络发送',
            'cpu_temperature': 'system_CPU温度',
            'load_1min': 'system_负载1分',
            'load_5min': 'system_负载5分',
            'load_15min': 'system_负载15分',
            'uptime_days': 'system_运行时间'
        }
        
        for key, display_name in metric_mapping.items():
            if key in system_data and display_name in self.metric_widgets:
                value = system_data[key]
                if value is not None:
                    self.metric_widgets[display_name].update_value(value)
        
        # 更新图表（降低频率）
        if self.update_counts['system_charts'] % 3 == 0:  # 每3次更新图表一次
            self._update_system_charts(system_data, timestamp)
        self.update_counts['system_charts'] += 1
    
    def _update_app_metrics(self, apps_data, timestamp):
        """更新应用指标显示"""
        for app_data in apps_data:
            if 'app_info' not in app_data:
                continue
                
            app_info = app_data['app_info']
            package_name = app_info['package_name']
            
            # 存储到环形缓冲区
            self.data_buffers['apps'][package_name].add_data(
                timestamp.timestamp(), app_data
            )
            
            # 计算内存使用率：内存使用/总内存
            if 'memory_pss' in app_data and app_data['memory_pss'] is not None:
                # 获取系统总内存
                system_total_memory = None
                if hasattr(self, 'latest_system_data') and self.latest_system_data:
                    system_total_memory = self.latest_system_data.get('memory_system_total')
                
                if system_total_memory and system_total_memory > 0:
                    # 计算内存使用率：应用内存(MB) / 系统总内存(MB) * 100
                    memory_percentage = (app_data['memory_pss'] / system_total_memory) * 100
                    app_data['memory_percentage'] = round(memory_percentage, 2)
                else:
                    # 如果无法获取系统总内存，回退到top命令的百分比
                    if 'top_memory_percent' in app_data and app_data['top_memory_percent'] is not None:
                        app_data['memory_percentage'] = round(app_data['top_memory_percent'], 2)
            
            # 更新度量显示组件
            metric_mapping = {
                'cpu_usage': f'{package_name}_CPU',
                'memory_pss': f'{package_name}_内存',
                'memory_percentage': f'{package_name}_内存百分比',
                'fps': f'{package_name}_帧率',
                'power_consumption': f'{package_name}_功耗'
            }
            
            for key, widget_key in metric_mapping.items():
                if key in app_data and widget_key in self.metric_widgets:
                    value = app_data[key]
                    if value is not None:
                        self.metric_widgets[widget_key].update_value(value)
            
            # 更新图表（降低频率）
            if self.update_counts[f'app_charts_{package_name}'] % 2 == 0:
                self._update_app_charts(app_data, timestamp, app_info)
            self.update_counts[f'app_charts_{package_name}'] += 1
    
    def _update_system_charts(self, system_data, timestamp):
        """更新系统图表"""
        ts = timestamp.timestamp()
        
        if 'cpu' in self.chart_widgets and 'cpu_usage' in system_data:
            # 添加总CPU使用率数据点
            cpu_usage = system_data['cpu_usage']
            self.chart_widgets['cpu'].add_data_point('系统 CPU使用率', ts, cpu_usage)
            
            # 如果有用户态CPU数据，也添加用户态CPU使用率数据点
            if 'cpu_user' in system_data:
                cpu_user = system_data['cpu_user']
                self.chart_widgets['cpu'].add_data_point('系统 CPU使用率 (用户态)', ts, cpu_user)
            
        if 'network' in self.chart_widgets:
            if 'network_rx' in system_data:
                self.chart_widgets['network'].add_data_point('系统 网络接收', ts, system_data['network_rx'])
            if 'network_tx' in system_data:
                self.chart_widgets['network'].add_data_point('系统 网络发送', ts, system_data['network_tx'])
    
    def _update_app_charts(self, app_data, timestamp, app_info):
        """更新应用图表"""
        package_name = app_info['package_name']
        # 直接使用包名作为图表标签，便于区分
        chart_label = package_name
        ts = timestamp.timestamp()
        
        if 'cpu' in self.chart_widgets and 'cpu_usage' in app_data:
            self.chart_widgets['cpu'].add_data_point(f"{chart_label} CPU", ts, app_data['cpu_usage'])
            
        if 'memory_mb' in self.chart_widgets and 'memory_pss' in app_data:
            self.chart_widgets['memory_mb'].add_data_point(f"{chart_label} 内存", ts, app_data['memory_pss'])
            
        if 'memory_percent' in self.chart_widgets and 'memory_percentage' in app_data:
            self.chart_widgets['memory_percent'].add_data_point(f"{chart_label} 内存使用率", ts, app_data['memory_percentage'])
            
        if 'fps' in self.chart_widgets and 'fps' in app_data:
            self.chart_widgets['fps'].add_data_point(f"{chart_label} FPS", ts, app_data['fps'])
            
        if 'power' in self.chart_widgets:
            power_value = app_data.get('power_consumption', 0)
            # If no power consumption data, show 0 but with indicator
            if power_value == 0 or power_value is None:
                power_label = f"{chart_label} 功耗 (估算)"
                # Try to get estimated power from adb_collector if available
                if hasattr(self, 'adb_collector'):
                    estimated = self.adb_collector._estimate_power_consumption(app_info['package_name'])
                    if estimated is not None:
                        power_value = estimated
            else:
                power_label = f"{chart_label} 功耗"
            
            self.chart_widgets['power'].add_data_point(power_label, ts, power_value)
    
    def _cleanup_expired_data(self):
        """清理过期数据"""
        try:
            # 清理系统数据缓冲区
            if self.data_buffers['system'].size() > 1000:
                # 保留最近的数据，清理旧数据
                pass  # CircularBuffer会自动处理
                
            # 清理应用数据缓冲区
            for package_name in list(self.data_buffers['apps'].keys()):
                if self.data_buffers['apps'][package_name].size() > 1000:
                    pass  # CircularBuffer会自动处理
                    
            # 清理更新计数器
            if len(self.update_counts) > 100:
                # 保留最近的计数器
                keys_to_keep = list(self.update_counts.keys())[-50:]
                new_counts = {k: self.update_counts[k] for k in keys_to_keep}
                self.update_counts = defaultdict(int, new_counts)
                
        except Exception as e:
            print(f"清理过期数据失败: {e}")
    
    def update_statistics(self):
        """更新统计信息"""
        if not self.monitoring_active:
            return
            
        try:
            # 更新数据点统计
            total_points = 0
            for buffer in [self.data_buffers['system']] + list(self.data_buffers['apps'].values()):
                total_points += buffer.size()
            
            self.total_data_points = total_points
                
        except Exception as e:
            print(f"更新统计信息失败: {e}")
    
    def init_ui(self):
        """初始化用户界面"""
        layout = QVBoxLayout(self)
        
        # 创建状态栏
        status_frame = QFrame()
        status_frame.setFrameStyle(QFrame.Box)
        status_frame.setMaximumHeight(60)
        status_layout = QHBoxLayout(status_frame)
        
        self.status_label = QLabel("监控状态: 未开始")
        self.status_label.setFont(QFont("Arial", 14, QFont.Bold))
        status_layout.addWidget(self.status_label)
        
        # 添加弹性空间
        status_layout.addStretch()
        
        # 右侧统计信息区域
        stats_widget = QWidget()
        stats_layout = QVBoxLayout(stats_widget)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(2)
        
        
        status_layout.addWidget(stats_widget)
        layout.addWidget(status_frame)
        
        # 初始化时间相关变量
        self.monitoring_start_time = None
        self.total_data_points = 0
        
        # 定义高对比度颜色系统
        self.app_colors = [
            "#E91E63",  # 粉红色
            "#9C27B0",  # 紫色  
            "#673AB7",  # 深紫色
            "#3F51B5",  # 靛蓝色
            "#2196F3",  # 蓝色
            "#03A9F4",  # 浅蓝色
            "#00BCD4",  # 青色
            "#009688",  # 茶色
            "#4CAF50",  # 绿色
            "#8BC34A",  # 浅绿色
            "#CDDC39",  # 柠檬绿
            "#FFEB3B",  # 黄色
            "#FFC107",  # 琥珀色
            "#FF9800",  # 橙色
            "#FF5722",  # 深橙色
            "#795548",  # 棕色
        ]
        self.app_color_index = 0
        
        # 创建主要内容区域
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        
        # 创建实际的指标显示区域
        self._create_metrics_display(content_layout)
        
        layout.addWidget(content_widget)
    
    def _create_metrics_display(self, parent_layout):
        """创建指标显示区域"""
        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # 创建主容器
        metrics_container = QWidget()
        main_layout = QVBoxLayout(metrics_container)
        
        # 系统指标组
        system_group = QGroupBox("系统性能指标")
        system_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
            }
        """)
        system_layout = QGridLayout(system_group)
        system_layout.setSpacing(12)  # 增加间距
        system_layout.setContentsMargins(15, 20, 15, 15)  # 增加内边距
        
        # 创建系统指标组件
        system_metrics = [
            ("system_CPU使用率：Total", "%", "#2196F3"),
            ("system_CPU使用率：用户态", "%", "#1976D2"),
            ("system_内存使用", "%", "#4CAF50"),
            ("system_电池电量", "%", "#FF9800"),
            ("system_网络接收", "KB/s", "#9C27B0"),
            ("system_网络发送", "KB/s", "#E91E63"),
            ("system_CPU温度", "°C", "#F44336"),
            ("system_负载1分", "", "#607D8B"),
            ("system_负载5分", "", "#795548"),
            ("system_负载15分", "", "#424242"),
            ("system_运行时间", "天", "#00BCD4"),
        ]
        
        # 设置系统指标布局为6列，2排显示
        row, col = 0, 0
        max_cols = 6
        for metric_name, unit, color in system_metrics:
            widget = MetricDisplayWidget(metric_name.replace("system_", ""), unit, color)
            widget.set_progress_visible(unit == "%")
            self.metric_widgets[metric_name] = widget
            system_layout.addWidget(widget, row, col)
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
        
        main_layout.addWidget(system_group)
        
        # 应用指标Tab组
        self.apps_tab_widget = QTabWidget()
        self.apps_tab_widget.setStyleSheet("""
            QTabWidget {
                border: 2px solid #4CAF50;
                border-radius: 8px;
                background-color: white;
                margin-top: 10px;
            }
            QTabWidget::pane {
                border: 2px solid #4CAF50;
                border-radius: 8px;
                padding: 10px;
                background-color: white;
            }
            QTabBar::tab {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-bottom: none;
                border-radius: 6px 6px 0 0;
                padding: 8px 15px;
                margin-right: 2px;
                min-width: 120px;
            }
            QTabBar::tab:selected {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
            }
            QTabBar::tab:hover {
                background-color: #81C784;
                color: white;
            }
        """)
        # 初始显示Tab组件（即使没有内容）
        main_layout.addWidget(self.apps_tab_widget)
        
        # 添加占位符Tab
        self._add_placeholder_tab()
        
        # 图表区域
        if PYQTGRAPH_AVAILABLE and CHART_WIDGETS_AVAILABLE:
            self._create_charts_area(main_layout)
        
        scroll_area.setWidget(metrics_container)
        parent_layout.addWidget(scroll_area)
    
    def _create_charts_area(self, parent_layout):
        """创建图表区域"""
        charts_group = QGroupBox("性能图表")
        charts_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #FF9800;
                border-radius: 8px;
                margin-top: 8px;
                padding-top: 8px;
                background-color: #fff8f0;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 8px 0 8px;
                color: #FF9800;
            }
        """)
        charts_layout = QVBoxLayout(charts_group)
        charts_layout.setSpacing(8)
        charts_layout.setContentsMargins(10, 15, 10, 10)
        
        # 创建图表管理器
        if not self.chart_manager:
            self.chart_manager = MultiSeriesChartManager()
        
        # 创建各类图表
        chart_configs = [
            ("cpu", "CPU使用率", "%", "#2196F3"),
            ("memory_mb", "应用内存使用量", "MB", "#4CAF50"),
            ("memory_percent", "内存使用率", "%", "#388E3C"),
            ("network", "网络流量", "KB/s", "#9C27B0"),
            ("fps", "帧率", "FPS", "#FF9800"),
            ("power", "功耗", "mW", "#F44336"),
        ]
        
        for chart_id, title, unit, color in chart_configs:
            chart_widget = AdvancedChartWidget(title, unit)
            self.chart_widgets[chart_id] = chart_widget
            charts_layout.addWidget(chart_widget)
        
        parent_layout.addWidget(charts_group)
    
    def _add_placeholder_tab(self):
        """添加占位符Tab页面"""
        placeholder_page = QWidget()
        placeholder_layout = QVBoxLayout(placeholder_page)
        placeholder_layout.setAlignment(Qt.AlignCenter)
        
        # 提示信息
        info_label = QLabel("📱 请选择要监控的应用")
        info_label.setFont(QFont("Arial", 18, QFont.Bold))
        info_label.setStyleSheet("color: #999; margin: 40px;")
        info_label.setAlignment(Qt.AlignCenter)
        placeholder_layout.addWidget(info_label)
        
        description_label = QLabel("选择应用后，每个应用将显示为独立的Tab页面")
        description_label.setFont(QFont("Arial", 14))
        description_label.setStyleSheet("color: #666; margin: 20px;")
        description_label.setAlignment(Qt.AlignCenter)
        placeholder_layout.addWidget(description_label)
        
        self.apps_tab_widget.addTab(placeholder_page, "应用性能指标")
    
    def _create_app_metrics_widgets(self, selected_apps):
        """为选中的应用创建Tab形式的指标显示组件"""
        # 清理现有的Tab页面
        self._clear_app_metrics_widgets()
        
        if not selected_apps:
            # 没有应用时显示占位符
            self._add_placeholder_tab()
            return
        
        for app in selected_apps:
            package_name = app['package_name']
            app_name = app.get('app_name', package_name)
            
            # 创建Tab页面
            tab_page = QWidget()
            tab_layout = QVBoxLayout(tab_page)
            tab_layout.setContentsMargins(20, 20, 20, 20)  # 1600px窗口下恢复舒适边距
            tab_layout.setSpacing(12)  # 适当增加间距
            
            # 添加应用信息标题
            info_label = QLabel(f"📱 {app_name}")
            info_label.setFont(QFont("Arial", 16, QFont.Bold))
            info_label.setStyleSheet("color: #4CAF50; margin-bottom: 10px;")
            tab_layout.addWidget(info_label)
            
            # 添加包名信息
            package_label = QLabel(f"包名: {package_name}")
            package_label.setFont(QFont("Arial", 12))
            package_label.setStyleSheet("color: #666; margin-bottom: 15px;")
            tab_layout.addWidget(package_label)
            
            # 创建指标网格容器
            metrics_container = QWidget()
            metrics_container.setMinimumWidth(800)  # 确保能容纳5个指标(5*160+0间距)
            metrics_layout = QGridLayout(metrics_container)
            metrics_layout.setSpacing(0)  # 去除模块间距，使用框线区别模块
            metrics_layout.setContentsMargins(0, 0, 0, 0)
            # 设置列拉伸比例，确保所有列均匀分布
            for i in range(5):
                metrics_layout.setColumnStretch(i, 1)
            
            # 创建应用指标组件 - 5个指标一排显示，1600px窗口下使用清晰标题
            app_metrics = [
                (f"{package_name}_CPU", "CPU使用率", "%", "#2196F3"),
                (f"{package_name}_内存", "内存使用", "MB", "#4CAF50"),
                (f"{package_name}_内存百分比", "内存占比", "%", "#388E3C"),
                (f"{package_name}_帧率", "帧率", "FPS", "#FF9800"),
                (f"{package_name}_功耗", "功耗", "mW", "#F44336"),
            ]
            
            # 一排5个指标的布局
            for i, (metric_name, display_name, unit, color) in enumerate(app_metrics):
                widget = MetricDisplayWidget(display_name, unit, color)
                if unit == "%":
                    widget.set_progress_visible(True)
                self.metric_widgets[metric_name] = widget
                metrics_layout.addWidget(widget, 0, i)  # 全部放在第0行
            
            # 固定1600x900窗口大小，无需滚动区域，直接添加指标容器
            tab_layout.addWidget(metrics_container)
            
            # 添加弹性空间
            tab_layout.addStretch()
            
            # 将Tab页面添加到Tab组件
            # 使用简化的应用名作为Tab标题
            tab_title = app_name[:15] if len(app_name) <= 15 else app_name[:12] + "..."
            self.apps_tab_widget.addTab(tab_page, tab_title)
    
    def _clear_app_metrics_widgets(self):
        """清理现有的Tab形式应用指标组件"""
        if not hasattr(self, 'apps_tab_widget'):
            return
            
        # 清理所有Tab页面
        while self.apps_tab_widget.count() > 0:
            self.apps_tab_widget.removeTab(0)
        
        # 清理相关的metric_widgets条目
        keys_to_remove = [key for key in self.metric_widgets.keys() 
                         if not key.startswith('system_')]
        for key in keys_to_remove:
            del self.metric_widgets[key]
    
    def start_monitoring(self, adb_collector, config):
        """开始监控"""
        self.adb_collector = adb_collector
        self.config = config
        self.monitoring_active = True
        self.monitoring_start_time = time.time()  # 记录开始时间
        self.total_data_points = 0
        self.status_label.setText("监控状态: 运行中")
        self.status_label.setStyleSheet("color: green;")
        
        # Reset battery stats for fresh power consumption data
        try:
            if hasattr(self.adb_collector, 'reset_battery_stats'):
                self.adb_collector.reset_battery_stats()
                self.status_label.setText("监控状态: 运行中")
        except Exception as e:
            logger.debug(f"Failed to reset battery stats at monitoring start: {e}")
        
        # 启动数据收集线程
        if hasattr(self, 'data_collection_worker'):
            self.data_collection_worker.quit()
            self.data_collection_worker.wait()
        
        try:
            self.data_collection_worker = OptimizedDataCollectionWorker(adb_collector, config)
            self.data_collection_worker.data_collected.connect(self.update_display)
            self.data_collection_worker.error_occurred.connect(self.handle_error)
            self.data_collection_worker.start()
        except Exception as e:
            print(f"启动监控失败: {e}")
    
    def stop_monitoring(self):
        """停止监控"""
        self.monitoring_active = False
        self.monitoring_start_time = None  # 清空开始时间
        self.status_label.setText("监控状态: 已停止")
        self.status_label.setStyleSheet("color: red;")
        
        if hasattr(self, 'data_collection_worker'):
            self.data_collection_worker.running = False
            self.data_collection_worker.quit()
            self.data_collection_worker.wait()
    
    def update_display(self, data):
        """更新显示数据"""
        try:
            # 使用队列缓冲更新，让UI线程处理
            if not self.update_queue.full():
                self.update_queue.put(data)
                
        except Exception as e:
            print(f"更新显示失败: {e}")
    
    def export_to_html(self, filepath):
        """导出数据到HTML页面"""
        try:
            html_content = self._generate_html_report()
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            return True
        except Exception as e:
            print(f"导出HTML失败: {e}")
            return False
    
    def _generate_html_report(self):
        """生成HTML报告内容"""
        # 收集数据
        system_data = self._collect_system_data()
        apps_data = self._collect_apps_data()
        
        # 生成HTML
        html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Android性能监控报告</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }}
        .stat-card {{ background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .stat-title {{ font-size: 16px; color: #666; margin-bottom: 5px; }}
        .stat-value {{ font-size: 26px; font-weight: bold; color: #333; }}
        .chart-container {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .app-section {{ margin: 20px 0; }}
        .app-title {{ background: #4CAF50; color: white; padding: 10px; border-radius: 5px; margin: 10px 0; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f8f9fa; font-weight: bold; }}
        .export-time {{ text-align: right; color: #666; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 Android性能监控报告</h1>
        <p>监控时长: {self._get_monitoring_duration()}</p>
        <p>数据点总数: {self.total_data_points}</p>
    </div>
    
    <div class="stats">
        {self._generate_system_stats_html(system_data)}
    </div>
    
    <div class="chart-container">
        <h2>📊 系统性能趋势</h2>
        <canvas id="systemChart" width="400" height="200"></canvas>
    </div>
    
    <div class="apps-section">
        <h2>📱 应用性能详情</h2>
        {self._generate_apps_html(apps_data)}
    </div>
    
    <div class="export-time">
        导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    </div>
    
    <script>
        {self._generate_chart_js(system_data, apps_data)}
    </script>
</body>
</html>
        """
        return html
    
    def _collect_system_data(self):
        """收集系统数据"""
        system_buffer = self.data_buffers['system']
        timestamps, data_points = system_buffer.get_recent_data(1800)  # 30分钟数据
        return {'timestamps': timestamps, 'data': data_points}
    
    def _collect_apps_data(self):
        """收集应用数据"""
        apps_data = {}
        for package_name, buffer in self.data_buffers['apps'].items():
            timestamps, data_points = buffer.get_recent_data(1800)
            apps_data[package_name] = {'timestamps': timestamps, 'data': data_points}
        return apps_data
    
    def _get_monitoring_duration(self):
        """获取监控时长字符串"""
        if not self.monitoring_start_time:
            return "00:00:00"
        elapsed = time.time() - self.monitoring_start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def _generate_system_stats_html(self, system_data):
        """生成系统统计信息HTML"""
        stats_html = ""
        system_metrics = ['CPU使用率：Total', 'CPU使用率：用户态', '内存使用', '电池电量', 'CPU温度']
        colors = ['#2196F3', '#1976D2', '#4CAF50', '#FF9800', '#F44336']
        
        for i, metric in enumerate(system_metrics):
            value = self._get_latest_metric_value(f'system_{metric}')
            stats_html += f"""
            <div class="stat-card">
                <div class="stat-title">{metric}</div>
                <div class="stat-value" style="color: {colors[i]}">{value}</div>
            </div>
            """
        return stats_html
    
    def _generate_apps_html(self, apps_data):
        """生成应用信息HTML"""
        apps_html = ""
        for package_name, data in apps_data.items():
            app_name = package_name.split('.')[-1]  # 简化包名
            apps_html += f"""
            <div class="app-section">
                <div class="app-title">{app_name} ({package_name})</div>
                <table>
                    <tr><th>指标</th><th>当前值</th><th>最大值</th><th>平均值</th></tr>
                    <tr><td>CPU使用率</td><td>{self._get_latest_metric_value(f'{package_name}_CPU')}%</td><td>-</td><td>-</td></tr>
                    <tr><td>内存使用</td><td>{self._get_latest_metric_value(f'{package_name}_内存')}MB</td><td>-</td><td>-</td></tr>
                    <tr><td>内存使用率</td><td>{self._get_latest_metric_value(f'{package_name}_内存百分比')}%</td><td>-</td><td>-</td></tr>
                    <tr><td>帧率</td><td>{self._get_latest_metric_value(f'{package_name}_帧率')}FPS</td><td>-</td><td>-</td></tr>
                    <tr><td>功耗</td><td>{self._get_latest_metric_value(f'{package_name}_功耗')}mW</td><td>-</td><td>-</td></tr>
                </table>
            </div>
            """
        return apps_html
    
    def _generate_chart_js(self, system_data, apps_data):
        """生成Chart.js代码"""
        return """
        // 创建系统性能图表
        const ctx = document.getElementById('systemChart').getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: ['示例时间点1', '示例时间点2', '示例时间点3'],
                datasets: [{
                    label: 'CPU使用率',
                    data: [30, 45, 60],
                    borderColor: '#2196F3',
                    fill: false
                }, {
                    label: '内存使用',
                    data: [40, 55, 70],
                    borderColor: '#4CAF50', 
                    fill: false
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100
                    }
                }
            }
        });
        """
    
    def _get_latest_metric_value(self, metric_name):
        """获取指标的最新值"""
        if metric_name in self.metric_widgets:
            return self.metric_widgets[metric_name].current_value
        return "0"
    
    def set_selected_apps(self, selected_apps):
        """设置选中的应用"""
        self.selected_apps = selected_apps
        if hasattr(self, 'config'):
            self.config['selected_apps'] = selected_apps
        
        # 创建应用指标显示组件
        self._create_app_metrics_widgets(selected_apps)
    
    def handle_error(self, error_msg):
        """处理错误"""
        print(f"监控错误: {error_msg}")
        self.status_label.setText(f"监控状态: 错误 - {error_msg}")
        self.status_label.setStyleSheet("color: red;")

# 向后兼容性别名
MonitorViewWidget = OptimizedMonitorViewWidget
