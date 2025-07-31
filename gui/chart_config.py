# -*- coding: utf-8 -*-
"""
图表配置管理器
处理图表的高级配置和设置
"""

import json
import os
from datetime import datetime
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                           QPushButton, QTabWidget, QWidget, QFormLayout,
                           QCheckBox, QSpinBox, QComboBox, QColorDialog,
                           QSlider, QGroupBox, QListWidget, QListWidgetItem,
                           QMessageBox, QLineEdit)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont

class ChartConfigDialog(QDialog):
    """图表配置对话框"""
    
    config_changed = pyqtSignal(dict)  # 配置改变信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chart Configuration")
        self.setModal(True)
        self.resize(600, 500)
        
        # 默认配置
        self.config = {
            'global': {
                'auto_scale': True,
                'show_grid': True,
                'show_legend': True,
                'line_width': 2,
                'update_interval': 1000,
                'max_points': 300,
                'time_range': 600  # seconds
            },
            'series': {},
            'colors': [
                '#2196F3', '#4CAF50', '#FF9800', '#F44336',
                '#9C27B0', '#00BCD4', '#FFEB3B', '#795548'
            ]
        }
        
        self.init_ui()
        
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        
        # 创建标签页
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # 全局设置标签页
        self.create_global_tab()
        
        # 数据系列标签页
        self.create_series_tab()
        
        # 颜色设置标签页
        self.create_color_tab()
        
        # 导出设置标签页
        self.create_export_tab()
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.reset_btn = QPushButton("Reset to Default")
        self.reset_btn.clicked.connect(self.reset_to_default)
        button_layout.addWidget(self.reset_btn)
        
        button_layout.addStretch()
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self.apply_config)
        button_layout.addWidget(self.apply_btn)
        
        self.ok_btn = QPushButton("OK")
        self.ok_btn.clicked.connect(self.accept_config)
        button_layout.addWidget(self.ok_btn)
        
        layout.addLayout(button_layout)
        
    def create_global_tab(self):
        """创建全局设置标签页"""
        global_widget = QWidget()
        layout = QVBoxLayout(global_widget)
        
        # 显示设置组
        display_group = QGroupBox("Display Settings")
        display_layout = QFormLayout(display_group)
        
        self.auto_scale_check = QCheckBox()
        self.auto_scale_check.setChecked(self.config['global']['auto_scale'])
        display_layout.addRow("Auto Scale:", self.auto_scale_check)
        
        self.show_grid_check = QCheckBox()
        self.show_grid_check.setChecked(self.config['global']['show_grid'])
        display_layout.addRow("Show Grid:", self.show_grid_check)
        
        self.show_legend_check = QCheckBox()
        self.show_legend_check.setChecked(self.config['global']['show_legend'])
        display_layout.addRow("Show Legend:", self.show_legend_check)
        
        self.line_width_spin = QSpinBox()
        self.line_width_spin.setRange(1, 10)
        self.line_width_spin.setValue(self.config['global']['line_width'])
        display_layout.addRow("Line Width:", self.line_width_spin)
        
        layout.addWidget(display_group)
        
        # 性能设置组
        performance_group = QGroupBox("Performance Settings")
        performance_layout = QFormLayout(performance_group)
        
        self.update_interval_spin = QSpinBox()
        self.update_interval_spin.setRange(100, 5000)
        self.update_interval_spin.setSuffix(" ms")
        self.update_interval_spin.setValue(self.config['global']['update_interval'])
        performance_layout.addRow("Update Interval:", self.update_interval_spin)
        
        self.max_points_spin = QSpinBox()
        self.max_points_spin.setRange(50, 1000)
        self.max_points_spin.setValue(self.config['global']['max_points'])
        performance_layout.addRow("Max Data Points:", self.max_points_spin)
        
        self.time_range_spin = QSpinBox()
        self.time_range_spin.setRange(60, 3600)
        self.time_range_spin.setSuffix(" seconds")
        self.time_range_spin.setValue(self.config['global']['time_range'])
        performance_layout.addRow("Time Range:", self.time_range_spin)
        
        layout.addWidget(performance_group)
        
        layout.addStretch()
        self.tab_widget.addTab(global_widget, "Global")
        
    def create_series_tab(self):
        """创建数据系列标签页"""
        series_widget = QWidget()
        layout = QHBoxLayout(series_widget)
        
        # 左侧：系列列表
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Data Series:"))
        
        self.series_list = QListWidget()
        self.series_list.currentItemChanged.connect(self.on_series_selected)
        left_layout.addWidget(self.series_list)
        
        layout.addLayout(left_layout, 1)
        
        # 右侧：系列设置
        right_layout = QVBoxLayout()
        
        self.series_settings_group = QGroupBox("Series Settings")
        self.series_settings_layout = QFormLayout(self.series_settings_group)
        
        self.series_name_edit = QLineEdit()
        self.series_settings_layout.addRow("Name:", self.series_name_edit)
        
        self.series_visible_check = QCheckBox()
        self.series_settings_layout.addRow("Visible:", self.series_visible_check)
        
        self.series_color_btn = QPushButton("Choose Color")
        self.series_color_btn.clicked.connect(self.choose_series_color)
        self.series_settings_layout.addRow("Color:", self.series_color_btn)
        
        self.series_line_style_combo = QComboBox()
        self.series_line_style_combo.addItems(["Solid", "Dashed", "Dotted", "DashDot"])
        self.series_settings_layout.addRow("Line Style:", self.series_line_style_combo)
        
        self.series_marker_combo = QComboBox()
        self.series_marker_combo.addItems(["None", "Circle", "Square", "Triangle", "Diamond"])
        self.series_settings_layout.addRow("Marker:", self.series_marker_combo)
        
        right_layout.addWidget(self.series_settings_group)
        right_layout.addStretch()
        
        layout.addLayout(right_layout, 1)
        
        self.tab_widget.addTab(series_widget, "Series")
        
    def create_color_tab(self):
        """创建颜色设置标签页"""
        color_widget = QWidget()
        layout = QVBoxLayout(color_widget)
        
        # 颜色主题选择
        theme_group = QGroupBox("Color Theme")
        theme_layout = QVBoxLayout(theme_group)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Default", "Dark", "Light", "Custom"])
        self.theme_combo.currentTextChanged.connect(self.on_theme_changed)
        theme_layout.addWidget(self.theme_combo)
        
        layout.addWidget(theme_group)
        
        # 自定义颜色
        custom_group = QGroupBox("Custom Colors")
        self.custom_layout = QVBoxLayout(custom_group)
        
        self.color_buttons = []
        self.update_color_buttons()
        
        layout.addWidget(custom_group)
        
        layout.addStretch()
        self.tab_widget.addTab(color_widget, "Colors")
        
    def create_export_tab(self):
        """创建导出设置标签页"""
        export_widget = QWidget()
        layout = QVBoxLayout(export_widget)
        
        # 导出格式设置
        format_group = QGroupBox("Export Format")
        format_layout = QFormLayout(format_group)
        
        self.export_format_combo = QComboBox()
        self.export_format_combo.addItems(["PNG", "SVG", "PDF", "JPG"])
        format_layout.addRow("Format:", self.export_format_combo)
        
        self.export_width_spin = QSpinBox()
        self.export_width_spin.setRange(400, 4000)
        self.export_width_spin.setValue(1200)
        format_layout.addRow("Width:", self.export_width_spin)
        
        self.export_height_spin = QSpinBox()
        self.export_height_spin.setRange(300, 3000)
        self.export_height_spin.setValue(800)
        format_layout.addRow("Height:", self.export_height_spin)
        
        self.export_dpi_spin = QSpinBox()
        self.export_dpi_spin.setRange(72, 300)
        self.export_dpi_spin.setValue(150)
        format_layout.addRow("DPI:", self.export_dpi_spin)
        
        layout.addWidget(format_group)
        
        # 导出选项
        options_group = QGroupBox("Export Options")
        options_layout = QVBoxLayout(options_group)
        
        self.export_background_check = QCheckBox("Include Background")
        self.export_background_check.setChecked(True)
        options_layout.addWidget(self.export_background_check)
        
        self.export_legend_check = QCheckBox("Include Legend")
        self.export_legend_check.setChecked(True)
        options_layout.addWidget(self.export_legend_check)
        
        self.export_timestamp_check = QCheckBox("Add Timestamp")
        self.export_timestamp_check.setChecked(True)
        options_layout.addWidget(self.export_timestamp_check)
        
        layout.addWidget(options_group)
        
        layout.addStretch()
        self.tab_widget.addTab(export_widget, "Export")
        
    def update_color_buttons(self):
        """更新颜色按钮"""
        # 清除现有按钮
        for button in self.color_buttons:
            button.setParent(None)
        self.color_buttons.clear()
        
        # 创建新按钮
        colors_layout = QHBoxLayout()
        
        for i, color in enumerate(self.config['colors']):
            btn = QPushButton()
            btn.setFixedSize(40, 30)
            btn.setStyleSheet(f"background-color: {color}; border: 1px solid #ccc;")
            btn.clicked.connect(lambda checked, idx=i: self.choose_color(idx))
            
            self.color_buttons.append(btn)
            colors_layout.addWidget(btn)
            
        # 添加颜色按钮
        add_btn = QPushButton("+")
        add_btn.setFixedSize(40, 30)
        add_btn.clicked.connect(self.add_color)
        colors_layout.addWidget(add_btn)
        
        colors_layout.addStretch()
        self.custom_layout.addLayout(colors_layout)
        
    def on_theme_changed(self, theme_name):
        """主题改变"""
        if theme_name == "Dark":
            self.config['colors'] = ['#1E88E5', '#43A047', '#FB8C00', '#E53935', 
                                   '#8E24AA', '#00ACC1', '#FDD835', '#6D4C41']
        elif theme_name == "Light":
            self.config['colors'] = ['#42A5F5', '#66BB6A', '#FFA726', '#EF5350', 
                                   '#AB47BC', '#26C6DA', '#FFEE58', '#8D6E63']
        elif theme_name == "Default":
            self.config['colors'] = ['#2196F3', '#4CAF50', '#FF9800', '#F44336',
                                   '#9C27B0', '#00BCD4', '#FFEB3B', '#795548']
        
        if theme_name != "Custom":
            self.update_color_buttons()
            
    def choose_color(self, index):
        """选择颜色"""
        current_color = QColor(self.config['colors'][index])
        color = QColorDialog.getColor(current_color, self)
        
        if color.isValid():
            self.config['colors'][index] = color.name()
            self.color_buttons[index].setStyleSheet(
                f"background-color: {color.name()}; border: 1px solid #ccc;"
            )
            
    def add_color(self):
        """添加颜色"""
        color = QColorDialog.getColor(QColor("#000000"), self)
        if color.isValid():
            self.config['colors'].append(color.name())
            self.update_color_buttons()
            
    def choose_series_color(self):
        """选择系列颜色"""
        color = QColorDialog.getColor(QColor("#2196F3"), self)
        if color.isValid():
            self.series_color_btn.setStyleSheet(
                f"background-color: {color.name()}; border: 1px solid #ccc;"
            )
            
    def on_series_selected(self, current, previous):
        """系列选择改变"""
        if current:
            series_name = current.text()
            # 更新系列设置界面
            self.series_name_edit.setText(series_name)
            
    def reset_to_default(self):
        """重置为默认设置"""
        reply = QMessageBox.question(
            self, 'Reset Configuration', 
            'Are you sure you want to reset all settings to default?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 重置配置
            self.config = {
                'global': {
                    'auto_scale': True,
                    'show_grid': True,
                    'show_legend': True,
                    'line_width': 2,
                    'update_interval': 1000,
                    'max_points': 300,
                    'time_range': 600
                },
                'series': {},
                'colors': [
                    '#2196F3', '#4CAF50', '#FF9800', '#F44336',
                    '#9C27B0', '#00BCD4', '#FFEB3B', '#795548'
                ]
            }
            
            # 更新UI
            self.update_ui_from_config()
            
    def update_ui_from_config(self):
        """根据配置更新UI"""
        # 更新全局设置
        self.auto_scale_check.setChecked(self.config['global']['auto_scale'])
        self.show_grid_check.setChecked(self.config['global']['show_grid'])
        self.show_legend_check.setChecked(self.config['global']['show_legend'])
        self.line_width_spin.setValue(self.config['global']['line_width'])
        self.update_interval_spin.setValue(self.config['global']['update_interval'])
        self.max_points_spin.setValue(self.config['global']['max_points'])
        self.time_range_spin.setValue(self.config['global']['time_range'])
        
        # 更新颜色按钮
        self.update_color_buttons()
        
    def get_config(self):
        """获取当前配置"""
        # 更新全局配置
        self.config['global']['auto_scale'] = self.auto_scale_check.isChecked()
        self.config['global']['show_grid'] = self.show_grid_check.isChecked()
        self.config['global']['show_legend'] = self.show_legend_check.isChecked()
        self.config['global']['line_width'] = self.line_width_spin.value()
        self.config['global']['update_interval'] = self.update_interval_spin.value()
        self.config['global']['max_points'] = self.max_points_spin.value()
        self.config['global']['time_range'] = self.time_range_spin.value()
        
        return self.config.copy()
        
    def set_config(self, config):
        """设置配置"""
        self.config = config.copy()
        self.update_ui_from_config()
        
    def apply_config(self):
        """应用配置"""
        config = self.get_config()
        self.config_changed.emit(config)
        
    def accept_config(self):
        """接受配置并关闭"""
        self.apply_config()
        self.accept()

class ChartThemeManager:
    """图表主题管理器"""
    
    def __init__(self):
        self.themes = {
            'default': {
                'background': '#ffffff',
                'grid': '#e0e0e0',
                'text': '#000000',
                'colors': ['#2196F3', '#4CAF50', '#FF9800', '#F44336', '#9C27B0', '#00BCD4']
            },
            'dark': {
                'background': '#2e2e2e',
                'grid': '#555555',
                'text': '#ffffff',
                'colors': ['#1E88E5', '#43A047', '#FB8C00', '#E53935', '#8E24AA', '#00ACC1']
            },
            'light': {
                'background': '#fafafa',
                'grid': '#f0f0f0',
                'text': '#333333',
                'colors': ['#42A5F5', '#66BB6A', '#FFA726', '#EF5350', '#AB47BC', '#26C6DA']
            }
        }
        
    def get_theme(self, theme_name):
        """获取主题"""
        return self.themes.get(theme_name, self.themes['default'])
        
    def apply_theme_to_chart(self, chart_widget, theme_name):
        """将主题应用到图表"""
        theme = self.get_theme(theme_name)
        
        if hasattr(chart_widget, 'plot_widget') and chart_widget.plot_widget:
            # 应用PyQtGraph主题
            chart_widget.plot_widget.setBackground(theme['background'])
            
    def save_theme(self, theme_name, theme_config):
        """保存主题"""
        self.themes[theme_name] = theme_config
        
    def load_themes_from_file(self, filepath):
        """从文件加载主题"""
        try:
            with open(filepath, 'r') as f:
                themes = json.load(f)
                self.themes.update(themes)
        except Exception as e:
            print(f"Failed to load themes: {e}")
            
    def save_themes_to_file(self, filepath):
        """保存主题到文件"""
        try:
            with open(filepath, 'w') as f:
                json.dump(self.themes, f, indent=2)
        except Exception as e:
            print(f"Failed to save themes: {e}")