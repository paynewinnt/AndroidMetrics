import sys
import os
from datetime import datetime
from collections import defaultdict, deque
import numpy as np

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                           QPushButton, QCheckBox, QSpinBox, QComboBox,
                           QGroupBox, QSlider, QFrame, QSplitter)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor

try:
    import pyqtgraph as pg
    from pyqtgraph import PlotWidget, PlotDataItem
    from pyqtgraph import exporters
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class AdvancedChartWidget(QWidget):
    """高级图表组件，支持实时数据显示和交互"""
    
    def __init__(self, title, y_label="Value", max_points=300):
        super().__init__()
        self.title = title
        self.y_label = y_label
        self.max_points = max_points
        
        # 数据存储
        self.data_series = {}  # {series_name: {'x': deque, 'y': deque, 'color': color}}
        self.plot_items = {}   # {series_name: PlotDataItem}
        
        # 图表配置
        self.auto_scale = True
        self.show_grid = True
        self.show_legend = True
        self.line_width = 2
        
        # 颜色列表
        self.colors = [
            '#2196F3',  # 蓝色
            '#4CAF50',  # 绿色
            '#FF9800',  # 橙色
            '#F44336',  # 红色
            '#9C27B0',  # 紫色
            '#00BCD4',  # 青色
            '#FFEB3B',  # 黄色
            '#795548',  # 棕色
        ]
        self.color_index = 0
        
        self.init_ui()
        
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        
        # 创建控制面板
        self.create_control_panel(layout)
        
        # 创建图表
        self.create_chart(layout)
        
        # 创建统计面板
        self.create_stats_panel(layout)
        
    def create_control_panel(self, layout):
        """创建控制面板"""
        control_frame = QFrame()
        control_frame.setFrameStyle(QFrame.Box)
        control_frame.setMaximumHeight(80)
        control_layout = QVBoxLayout(control_frame)
        
        # 标题
        title_label = QLabel(self.title)
        title_label.setFont(QFont("Arial", 14, QFont.Bold))  # 增大字体2个字号
        title_label.setAlignment(Qt.AlignCenter)
        control_layout.addWidget(title_label)
        
        # 控制按钮行
        controls_layout = QHBoxLayout()
        
        # 自动缩放
        self.auto_scale_check = QCheckBox("自动缩放")
        self.auto_scale_check.setChecked(self.auto_scale)
        self.auto_scale_check.toggled.connect(self.toggle_auto_scale)
        controls_layout.addWidget(self.auto_scale_check)
        
        # 显示网格
        self.grid_check = QCheckBox("显示网格")
        self.grid_check.setChecked(self.show_grid)
        self.grid_check.toggled.connect(self.toggle_grid)
        controls_layout.addWidget(self.grid_check)
        
        # 显示图例
        self.legend_check = QCheckBox("显示图例")
        self.legend_check.setChecked(self.show_legend)
        self.legend_check.toggled.connect(self.toggle_legend)
        controls_layout.addWidget(self.legend_check)
        
        controls_layout.addStretch()
        
        # 时间范围控制
        controls_layout.addWidget(QLabel("显示时长:"))
        self.time_range_combo = QComboBox()
        self.time_range_combo.addItems(["1分钟", "5分钟", "10分钟", "30分钟", "全部"])
        self.time_range_combo.setCurrentText("10分钟")
        self.time_range_combo.currentTextChanged.connect(self.change_time_range)
        controls_layout.addWidget(self.time_range_combo)
        
        # 暂停/继续
        self.pause_btn = QPushButton("暂停")
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.paused = False
        controls_layout.addWidget(self.pause_btn)
        
        # 清空数据
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self.clear_data)
        controls_layout.addWidget(clear_btn)
        
        # 导出数据
        export_btn = QPushButton("导出")
        export_btn.clicked.connect(self.export_chart)
        controls_layout.addWidget(export_btn)
        
        control_layout.addLayout(controls_layout)
        layout.addWidget(control_frame)
        
    def create_chart(self, layout):
        """创建图表"""
        if PYQTGRAPH_AVAILABLE:
            # 使用PyQtGraph创建高性能图表
            self.plot_widget = PlotWidget()
            
            # 设置图表属性
            self.plot_widget.setLabel('left', self.y_label)
            self.plot_widget.setLabel('bottom', '时间')
            self.plot_widget.showGrid(x=self.show_grid, y=self.show_grid)
            
            # 设置时间轴格式化
            axis = self.plot_widget.getAxis('bottom')
            axis.setLabel('时间')
            
            # 创建自定义时间轴格式化函数
            def format_time(values, scale, spacing):
                formatted_times = []
                for value in values:
                    try:
                        # 检查时间戳有效性
                        if value is None or not isinstance(value, (int, float)):
                            formatted_times.append('')
                            continue
                        
                        # 检查时间戳范围（1970年到2100年之间）
                        if value < 0 or value > 4102444800:  # 2100年1月1日的时间戳
                            formatted_times.append('')
                            continue
                            
                        # 格式化时间
                        dt = datetime.fromtimestamp(value)
                        formatted_times.append(dt.strftime('%H:%M:%S'))
                        
                    except (OSError, ValueError, OverflowError) as e:
                        # 处理无效时间戳
                        formatted_times.append('')
                        
                return formatted_times
            
            # 应用自定义格式化
            axis.tickStrings = format_time
            
            # 设置Y轴格式化为2位小数
            y_axis = self.plot_widget.getAxis('left')
            
            def format_y_values(values, scale, spacing):
                formatted_values = []
                for value in values:
                    try:
                        if value is None or not isinstance(value, (int, float)):
                            formatted_values.append('')
                            continue
                        # 格式化为2位小数
                        formatted_values.append(f'{value:.2f}')
                    except (ValueError, TypeError):
                        formatted_values.append('')
                return formatted_values
            
            # 应用Y轴自定义格式化
            y_axis.tickStrings = format_y_values
            
            # 启用交互（禁用滚轮缩放）
            self.plot_widget.setMouseEnabled(x=True, y=True)
            self.plot_widget.enableAutoRange('xy', True)
            
            # 禁用鼠标滚轮缩放
            view_box = self.plot_widget.getViewBox()
            view_box.setMouseEnabled(x=True, y=True)
            
            # 创建自定义的wheelEvent函数来处理可能的参数
            def disabled_wheel_event(event, axis=None):
                # 完全忽略滚轮事件，不做任何处理
                event.ignore()
                return
            
            view_box.wheelEvent = disabled_wheel_event
            
            # 添加十字光标
            self.crosshair_v = pg.InfiniteLine(angle=90, movable=False, pen='g')
            self.crosshair_h = pg.InfiniteLine(angle=0, movable=False, pen='g')
            self.plot_widget.addItem(self.crosshair_v, ignoreBounds=True)
            self.plot_widget.addItem(self.crosshair_h, ignoreBounds=True)
            
            # 鼠标移动事件
            self.plot_widget.scene().sigMouseMoved.connect(self.mouse_moved)
            
            layout.addWidget(self.plot_widget)
            
        else:
            # 降级方案：使用简单的图表显示
            fallback_label = QLabel("PyQtGraph未安装，使用简化图表显示")
            fallback_label.setAlignment(Qt.AlignCenter)
            fallback_label.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ccc; padding: 20px;")
            layout.addWidget(fallback_label)
            self.plot_widget = None
            
    def create_stats_panel(self, layout):
        """创建统计信息面板"""
        stats_frame = QFrame()
        stats_frame.setFrameStyle(QFrame.Box)
        stats_frame.setMaximumHeight(60)
        stats_layout = QHBoxLayout(stats_frame)
        
        # 数据点数量
        self.points_label = QLabel("数据点: 0")
        stats_layout.addWidget(self.points_label)
        
        # 时间范围
        self.time_range_label = QLabel("时间范围: --")
        stats_layout.addWidget(self.time_range_label)
        
        stats_layout.addStretch()
        
        # 当前值显示
        self.current_values_label = QLabel("当前值: --")
        stats_layout.addWidget(self.current_values_label)
        
        layout.addWidget(stats_frame)
        
    def add_series(self, series_name, color=None):
        """添加数据系列"""
        if color is None:
            color = self.colors[self.color_index % len(self.colors)]
            self.color_index += 1
            
        self.data_series[series_name] = {
            'x': deque(maxlen=self.max_points),
            'y': deque(maxlen=self.max_points),
            'color': color,
            'visible': True
        }
        
        if PYQTGRAPH_AVAILABLE and self.plot_widget:
            # 创建绘图项
            pen = pg.mkPen(color=color, width=self.line_width)
            plot_item = self.plot_widget.plot([], [], pen=pen, name=series_name)
            self.plot_items[series_name] = plot_item
            
            # 创建文本标签项
            text_item = pg.TextItem(series_name, color=color, anchor=(0, 0.5))
            text_item.hide()  # 初始隐藏
            self.plot_widget.addItem(text_item)
            if not hasattr(self, 'text_items'):
                self.text_items = {}
            self.text_items[series_name] = text_item
            
    def add_data_point(self, series_name, x_value, y_value):
        """添加数据点"""
        if self.paused:
            return
            
        # 验证数据有效性
        if not self._is_valid_data_point(x_value, y_value):
            return
            
        if series_name not in self.data_series:
            self.add_series(series_name)
            
        # 添加数据点
        self.data_series[series_name]['x'].append(x_value)
        self.data_series[series_name]['y'].append(y_value)
        
        # 更新图表
        if PYQTGRAPH_AVAILABLE and self.plot_widget and series_name in self.plot_items:
            x_data = list(self.data_series[series_name]['x'])
            y_data = list(self.data_series[series_name]['y'])
            
            if len(x_data) > 0 and len(x_data) == len(y_data):
                try:
                    # 再次验证数据有效性
                    valid_x = [x for x in x_data if self._is_valid_timestamp(x)]
                    valid_y = [y for y in y_data if self._is_valid_number(y)]
                    
                    if len(valid_x) == len(x_data) and len(valid_y) == len(y_data):
                        self.plot_items[series_name].setData(x_data, y_data)
                        
                        # 更新文本标签位置到折线最后一个点
                        if hasattr(self, 'text_items') and series_name in self.text_items and len(x_data) > 0:
                            last_x = x_data[-1]
                            last_y = y_data[-1]
                            self.text_items[series_name].setPos(last_x, last_y)
                            self.text_items[series_name].show()
                            
                except Exception as e:
                    print(f"更新图表数据失败: {e}")
                
        # 更新统计信息
        self.update_stats()
    
    def _is_valid_data_point(self, x_value, y_value):
        """验证数据点的有效性"""
        try:
            # 检查x值（时间戳）有效性
            if x_value is None or not isinstance(x_value, (int, float)):
                return False
            
            # 检查时间戳范围（1970年到2100年之间）
            if x_value < 0 or x_value > 4102444800:  # 2100年1月1日的时间戳
                return False
            
            # 检查y值有效性
            if y_value is None or not isinstance(y_value, (int, float)):
                return False
            
            # 检查y值是否为数字（不是NaN或无穷大）
            if not (float('-inf') < y_value < float('inf')):
                return False
                
            return True
            
        except (TypeError, ValueError):
            return False
    
    def _is_valid_timestamp(self, value):
        """验证时间戳有效性"""
        try:
            if value is None or not isinstance(value, (int, float)):
                return False
            return 0 <= value <= 4102444800  # 1970年到2100年之间
        except:
            return False
    
    def _is_valid_number(self, value):
        """验证数值有效性"""
        try:
            if value is None or not isinstance(value, (int, float)):
                return False
            return float('-inf') < value < float('inf')
        except:
            return False
        
    def remove_series(self, series_name):
        """移除数据系列"""
        if series_name in self.data_series:
            del self.data_series[series_name]
            
        if series_name in self.plot_items:
            if PYQTGRAPH_AVAILABLE and self.plot_widget:
                self.plot_widget.removeItem(self.plot_items[series_name])
            del self.plot_items[series_name]
            
        # 移除文本标签
        if hasattr(self, 'text_items') and series_name in self.text_items:
            if PYQTGRAPH_AVAILABLE and self.plot_widget:
                self.plot_widget.removeItem(self.text_items[series_name])
            del self.text_items[series_name]
            
    def toggle_series_visibility(self, series_name, visible):
        """切换数据系列可见性"""
        if series_name in self.data_series:
            self.data_series[series_name]['visible'] = visible
            
        if series_name in self.plot_items:
            if PYQTGRAPH_AVAILABLE:
                self.plot_items[series_name].setVisible(visible)
                
    def toggle_auto_scale(self, enabled):
        """切换自动缩放"""
        self.auto_scale = enabled
        if PYQTGRAPH_AVAILABLE and self.plot_widget:
            if enabled:
                self.plot_widget.enableAutoRange('xy', True)
            else:
                self.plot_widget.disableAutoRange()
                
    def toggle_grid(self, enabled):
        """切换网格显示"""
        self.show_grid = enabled
        if PYQTGRAPH_AVAILABLE and self.plot_widget:
            self.plot_widget.showGrid(x=enabled, y=enabled)
            
    def toggle_legend(self, enabled):
        """切换图例显示"""
        self.show_legend = enabled
        if PYQTGRAPH_AVAILABLE and self.plot_widget:
            if enabled:
                self.plot_widget.addLegend()
            else:
                # PyQtGraph doesn't have removeLegend, so we recreate the plot
                pass
                
    def change_time_range(self, range_text):
        """改变时间范围"""
        range_minutes = {
            "1分钟": 1,
            "5分钟": 5,
            "10分钟": 10,
            "30分钟": 30,
            "全部": 0
        }
        
        minutes = range_minutes.get(range_text, 10)
        if minutes > 0:
            # 实现时间范围过滤
            self.filter_by_time_range(minutes)
            
    def filter_by_time_range(self, minutes):
        """按时间范围过滤数据"""
        if not PYQTGRAPH_AVAILABLE or not self.plot_widget:
            return
            
        current_time = datetime.now().timestamp()
        cutoff_time = current_time - (minutes * 60)
        
        for series_name in self.data_series:
            if series_name in self.plot_items:
                x_data = list(self.data_series[series_name]['x'])
                y_data = list(self.data_series[series_name]['y'])
                
                # 过滤时间范围内的数据
                filtered_x = []
                filtered_y = []
                
                for i, x_val in enumerate(x_data):
                    if isinstance(x_val, datetime):
                        timestamp = x_val.timestamp()
                    else:
                        timestamp = x_val
                        
                    if timestamp >= cutoff_time:
                        filtered_x.append(x_val)
                        filtered_y.append(y_data[i])
                        
                self.plot_items[series_name].setData(filtered_x, filtered_y)
                
    def toggle_pause(self):
        """切换暂停状态"""
        self.paused = not self.paused
        self.pause_btn.setText("继续" if self.paused else "暂停")
        
    def clear_data(self):
        """清空所有数据"""
        for series_name in self.data_series:
            self.data_series[series_name]['x'].clear()
            self.data_series[series_name]['y'].clear()
            
            if series_name in self.plot_items:
                self.plot_items[series_name].setData([], [])
                
        self.update_stats()
        
    def export_chart(self):
        """导出图表"""
        if PYQTGRAPH_AVAILABLE and self.plot_widget:
            try:
                # 导出为PNG
                exporter = exporters.ImageExporter(self.plot_widget.plotItem)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"chart_{self.title}_{timestamp}.png"
                exporter.export(filename)
                print(f"图表已导出为: {filename}")
            except Exception as e:
                print(f"导出失败: {e}")
        else:
            print("PyQtGraph未安装，无法导出图表")
            
    def mouse_moved(self, evt):
        """鼠标移动事件处理"""
        if not PYQTGRAPH_AVAILABLE or not self.plot_widget:
            return
            
        pos = evt
        if self.plot_widget.sceneBoundingRect().contains(pos):
            mouse_point = self.plot_widget.plotItem.vb.mapSceneToView(pos)
            
            # 更新十字光标
            self.crosshair_v.setPos(mouse_point.x())
            self.crosshair_h.setPos(mouse_point.y())
            
            # 显示当前位置的值
            x_val = mouse_point.x()
            y_val = mouse_point.y()
            
            # 更新状态显示
            self.update_cursor_info(x_val, y_val)
            
    def update_cursor_info(self, x_val, y_val):
        """更新光标信息显示"""
        # 这里可以显示光标位置的详细信息
        pass
        
    def update_stats(self):
        """更新统计信息"""
        total_points = sum(len(series['x']) for series in self.data_series.values())
        self.points_label.setText(f"数据点: {total_points}")
        
        # 更新时间范围
        if self.data_series:
            all_times = []
            for series in self.data_series.values():
                if series['x']:
                    all_times.extend(series['x'])
                    
            if all_times:
                min_time = min(all_times)
                max_time = max(all_times)
                
                # 将timestamp转换为时分秒格式
                if isinstance(min_time, datetime):
                    time_range = f"{min_time.strftime('%H:%M:%S')} - {max_time.strftime('%H:%M:%S')}"
                else:
                    # 假设是timestamp格式，转换为时分秒
                    min_dt = datetime.fromtimestamp(min_time)
                    max_dt = datetime.fromtimestamp(max_time)
                    time_range = f"{min_dt.strftime('%H:%M:%S')} - {max_dt.strftime('%H:%M:%S')}"
                    
                self.time_range_label.setText(f"时间范围: {time_range}")
                
        # 更新当前值
        current_values = []
        for series_name, series_data in self.data_series.items():
            if series_data['y'] and series_data['visible']:
                latest_value = series_data['y'][-1]
                current_values.append(f"{series_name}: {latest_value:.2f}")
                
        if current_values:
            self.current_values_label.setText("当前值: " + " | ".join(current_values))
        else:
            self.current_values_label.setText("当前值: --")
            
    def get_series_stats(self, series_name):
        """获取数据系列统计信息"""
        if series_name not in self.data_series:
            return None
            
        y_data = list(self.data_series[series_name]['y'])
        if not y_data:
            return None
            
        return {
            'count': len(y_data),
            'min': min(y_data),
            'max': max(y_data),
            'avg': sum(y_data) / len(y_data),
            'current': y_data[-1] if y_data else 0
        }

class MultiSeriesChartManager(QWidget):
    """多系列图表管理器"""
    
    def __init__(self):
        super().__init__()
        self.charts = {}
        self.init_ui()
        
    def init_ui(self):
        """初始化UI"""
        self.layout = QVBoxLayout(self)
        
    def add_chart(self, chart_id, title, y_label="Value"):
        """添加图表"""
        chart = AdvancedChartWidget(title, y_label)
        self.charts[chart_id] = chart
        self.layout.addWidget(chart)
        return chart
        
    def remove_chart(self, chart_id):
        """移除图表"""
        if chart_id in self.charts:
            chart = self.charts[chart_id]
            self.layout.removeWidget(chart)
            chart.setParent(None)
            del self.charts[chart_id]
            
    def get_chart(self, chart_id):
        """获取图表"""
        return self.charts.get(chart_id)
        
    def clear_all_charts(self):
        """清空所有图表"""
        for chart in self.charts.values():
            chart.clear_data()
            
    def export_all_charts(self):
        """导出所有图表"""
        for chart_id, chart in self.charts.items():
            chart.export_chart()