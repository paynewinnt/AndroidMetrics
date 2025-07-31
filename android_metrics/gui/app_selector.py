# -*- coding: utf-8 -*-
import sys
import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, 
                           QListWidgetItem, QPushButton, QLabel, QLineEdit,
                           QGroupBox, QCheckBox, QSpinBox, QComboBox,
                           QMessageBox, QProgressDialog, QFrame)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, pyqtSlot
from PyQt5.QtGui import QFont

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class AppSelectorWidget(QWidget):
    # 信号定义
    apps_selected = pyqtSignal(list)  # 应用选择信号
    monitoring_started = pyqtSignal(dict)  # 监控开始信号
    monitoring_stopped = pyqtSignal()  # 监控停止信号
    
    def __init__(self):
        super().__init__()
        self.apps_list = []
        self.selected_apps = []
        self.monitoring_active = False
        
        self.init_ui()
        
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        
        # 创建标题
        self.create_header(layout)
        
        # 创建主内容区域
        main_layout = QHBoxLayout()
        layout.addLayout(main_layout)
        
        # 应用列表区域
        self.create_app_list_section(main_layout)
        
        # 监控配置区域
        self.create_config_section(main_layout)
        
        # 创建按钮区域
        self.create_button_section(layout)
        
        # 应用样式
        self.apply_styles()
        
    def create_header(self, layout):
        """创建标题区域"""
        header_frame = QFrame()
        header_frame.setFrameStyle(QFrame.Box)
        header_layout = QVBoxLayout(header_frame)
        
        title_label = QLabel("应用性能监控")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))  # 增大字体2个字号
        title_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title_label)
        
        desc_label = QLabel(
            "选择要监控的Android应用，配置监控参数，开始性能分析"
        )
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setStyleSheet("color: #666666; margin: 5px;")
        header_layout.addWidget(desc_label)
        
        layout.addWidget(header_frame)
        
    def create_app_list_section(self, layout):
        """创建应用列表区域"""
        app_group = QGroupBox("应用列表")
        app_layout = QVBoxLayout(app_group)
        
        # 搜索和过滤框
        filter_layout = QVBoxLayout()
        
        # 搜索框
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入应用名或包名...")
        self.search_input.textChanged.connect(self.filter_apps)
        
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        filter_layout.addLayout(search_layout)
        
        # 应用类型过滤
        type_layout = QHBoxLayout()
        type_label = QLabel("类型:")
        self.app_type_combo = QComboBox()
        self.app_type_combo.addItems(["所有应用", "仅第三方应用", "仅系统应用"])
        self.app_type_combo.currentTextChanged.connect(self.filter_apps)
        
        type_layout.addWidget(type_label)
        type_layout.addWidget(self.app_type_combo)
        type_layout.addStretch()
        filter_layout.addLayout(type_layout)
        
        app_layout.addLayout(filter_layout)
        
        # 应用列表
        self.app_list = QListWidget()
        self.app_list.setSelectionMode(QListWidget.MultiSelection)
        self.app_list.itemSelectionChanged.connect(self.on_selection_changed)
        app_layout.addWidget(self.app_list)
        
        # 选择状态
        self.selection_label = QLabel("已选择: 0 / 6")
        self.selection_label.setAlignment(Qt.AlignCenter)
        self.selection_label.setStyleSheet("font-weight: bold; color: #2196F3;")
        app_layout.addWidget(self.selection_label)
        
        layout.addWidget(app_group, 2)  # 占2/3宽度
        
    def create_config_section(self, layout):
        """创建监控配置区域"""
        config_group = QGroupBox("监控配置")
        config_layout = QVBoxLayout(config_group)
        
        # 采样配置
        sampling_group = QGroupBox("采样设置")
        sampling_layout = QVBoxLayout(sampling_group)
        
        # 采样间隔
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("采样间隔:"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 60)
        self.interval_spin.setValue(5)
        self.interval_spin.setSuffix(" 秒")
        interval_layout.addWidget(self.interval_spin)
        interval_layout.addStretch()
        sampling_layout.addLayout(interval_layout)
        
        # 监控时长
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("监控时长:"))
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 1440)
        self.duration_spin.setValue(20)
        self.duration_spin.setSuffix(" 分钟")
        duration_layout.addWidget(self.duration_spin)
        duration_layout.addStretch()
        sampling_layout.addLayout(duration_layout)
        
        # 连续监控模式
        self.continuous_check = QCheckBox("连续监控模式（不限时间）")
        sampling_layout.addWidget(self.continuous_check)
        
        config_layout.addWidget(sampling_group)
        
        # 监控指标
        metrics_group = QGroupBox("监控指标")
        metrics_layout = QVBoxLayout(metrics_group)
        
        self.cpu_check = QCheckBox("CPU使用率")
        self.cpu_check.setChecked(True)
        metrics_layout.addWidget(self.cpu_check)
        
        self.memory_check = QCheckBox("内存使用")
        self.memory_check.setChecked(True)
        metrics_layout.addWidget(self.memory_check)
        
        self.network_check = QCheckBox("网络流量")
        self.network_check.setChecked(True)
        metrics_layout.addWidget(self.network_check)
        
        self.power_check = QCheckBox("功耗状态")
        self.power_check.setChecked(True)
        metrics_layout.addWidget(self.power_check)
        
        self.fps_check = QCheckBox("FPS帧率")
        self.fps_check.setChecked(True)
        metrics_layout.addWidget(self.fps_check)
        
        self.system_check = QCheckBox("系统整体性能")
        self.system_check.setChecked(True)
        metrics_layout.addWidget(self.system_check)
        
        config_layout.addWidget(metrics_group)
        
        # 预设配置
        preset_group = QGroupBox("预设配置")
        preset_layout = QVBoxLayout(preset_group)
        
        preset_select_layout = QHBoxLayout()
        preset_select_layout.addWidget(QLabel("选择预设:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["标准监控", "性能测试", "长期监控", "自定义"])
        self.preset_combo.currentTextChanged.connect(self.on_preset_changed)
        preset_select_layout.addWidget(self.preset_combo)
        preset_layout.addLayout(preset_select_layout)
        
        preset_buttons_layout = QHBoxLayout()
        self.save_preset_btn = QPushButton("保存配置")
        self.save_preset_btn.clicked.connect(self.save_preset)
        self.load_preset_btn = QPushButton("加载配置")
        self.load_preset_btn.clicked.connect(self.load_preset)
        preset_buttons_layout.addWidget(self.save_preset_btn)
        preset_buttons_layout.addWidget(self.load_preset_btn)
        preset_layout.addLayout(preset_buttons_layout)
        
        config_layout.addWidget(preset_group)
        
        config_layout.addStretch()
        
        layout.addWidget(config_group, 1)  # 占1/3宽度
        
    def create_button_section(self, layout):
        """创建按钮区域"""
        button_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("刷新应用列表")
        self.refresh_btn.clicked.connect(self.refresh_apps)
        button_layout.addWidget(self.refresh_btn)
        
        button_layout.addStretch()
        
        self.start_btn = QPushButton("开始监控")
        self.start_btn.clicked.connect(self.start_monitoring)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px 20px;
                font-size: 16px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        button_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("停止监控")
        self.stop_btn.clicked.connect(self.stop_monitoring)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 10px 20px;
                font-size: 16px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        button_layout.addWidget(self.stop_btn)
        
        layout.addLayout(button_layout)
        
    def apply_styles(self):
        """应用样式"""
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 8px;
                margin: 10px 0px;
                padding-top: 10px;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #2196F3;
            }
            
            QListWidget {
                border: 1px solid #cccccc;
                border-radius: 4px;
                background-color: white;
                selection-background-color: #e3f2fd;
            }
            
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #f0f0f0;
            }
            
            QListWidget::item:selected {
                background-color: #2196F3;
                color: white;
            }
            
            QLineEdit {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 6px;
                background-color: white;
            }
            
            QLineEdit:focus {
                border-color: #2196F3;
            }
            
            QSpinBox, QComboBox {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 4px;
                background-color: white;
            }
            
            QCheckBox {
                padding: 4px;
            }
            
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            
            QCheckBox::indicator:checked {
                background-color: #2196F3;
                border: 1px solid #2196F3;
            }
            
            QPushButton {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 6px 12px;
                background-color: #f8f8f8;
            }
            
            QPushButton:hover {
                background-color: #e8e8e8;
            }
            
            QPushButton:pressed {
                background-color: #d8d8d8;
            }
        """)
        
    def set_apps(self, apps):
        """设置应用列表"""
        self.apps_list = apps
        self.update_app_list()
        
    def update_app_list(self):
        """更新应用列表显示"""
        self.app_list.clear()
        
        search_text = self.search_input.text().lower()
        app_type_filter = self.app_type_combo.currentText()
        
        for app in self.apps_list:
            app_name = app.get('app_name', app['package_name'])
            package_name = app['package_name']
            is_system = app.get('is_system', False)
            
            # 搜索过滤
            if search_text and search_text not in app_name.lower() and search_text not in package_name.lower():
                continue
                
            # 应用类型过滤
            if app_type_filter == "仅第三方应用" and is_system:
                continue
            elif app_type_filter == "仅系统应用" and not is_system:
                continue
                
            # 添加列表项
            if is_system:
                item_text = f"{app_name} [系统]\n{package_name}"
            else:
                item_text = f"{app_name}\n{package_name}"
                
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, app)
            
            # 系统应用使用不同的样式
            if is_system:
                item.setForeground(Qt.gray)
            
            self.app_list.addItem(item)
            
    def filter_apps(self):
        """过滤应用列表"""
        self.update_app_list()
        
    def on_selection_changed(self):
        """选择变化处理"""
        selected_items = self.app_list.selectedItems()
        self.selected_apps = [item.data(Qt.UserRole) for item in selected_items]
        
        # 限制选择数量
        if len(self.selected_apps) > 6:
            # 取消最后一个选择
            selected_items[-1].setSelected(False)
            self.selected_apps = self.selected_apps[:6]
            QMessageBox.warning(self, "选择限制", "最多只能选择6个应用进行监控")
            
        # 更新选择状态
        self.selection_label.setText(f"已选择: {len(self.selected_apps)} / 6")
        
        # 更新开始按钮状态
        self.start_btn.setEnabled(len(self.selected_apps) > 0 and not self.monitoring_active)
        
        # 发送选择信号
        self.apps_selected.emit(self.selected_apps)
        
    def get_monitoring_config(self):
        """获取监控配置"""
        return {
            'selected_apps': self.selected_apps,
            'sample_interval': self.interval_spin.value(),
            'duration_minutes': self.duration_spin.value() if not self.continuous_check.isChecked() else 0,
            'continuous': self.continuous_check.isChecked(),
            'metrics': {
                'cpu': self.cpu_check.isChecked(),
                'memory': self.memory_check.isChecked(),
                'network': self.network_check.isChecked(),
                'power': self.power_check.isChecked(),
                'fps': self.fps_check.isChecked(),
                'system': self.system_check.isChecked()
            }
        }
        
    def start_monitoring(self):
        """开始监控"""
        if len(self.selected_apps) == 0:
            QMessageBox.warning(self, "提示", "请先选择至少一个应用进行监控")
            return
            
        # 获取配置
        config = self.get_monitoring_config()
        
        # 确认对话框
        app_names = [app.get('app_name', app['package_name']) for app in self.selected_apps]
        message = f"将开始监控以下应用:\n\n" + "\n".join(f"• {name}" for name in app_names)
        message += f"\n\n采样间隔: {config['sample_interval']}秒"
        
        if config['continuous']:
            message += "\n监控时长: 连续监控"
        else:
            message += f"\n监控时长: {config['duration_minutes']}分钟"
            
        reply = QMessageBox.question(
            self, '确认开始监控', message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.Yes:
            self.monitoring_active = True
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.monitoring_started.emit(config)
            
    def stop_monitoring(self):
        """停止监控"""
        reply = QMessageBox.question(
            self, '确认停止监控', '确定要停止当前监控任务吗？',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.monitoring_active = False
            self.start_btn.setEnabled(len(self.selected_apps) > 0)
            self.stop_btn.setEnabled(False)
            self.monitoring_stopped.emit()
            
    def refresh_apps(self):
        """刷新应用列表"""
        try:
            # 创建进度对话框
            progress = QProgressDialog("正在刷新应用列表...", "取消", 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setAutoClose(True)
            progress.setAutoReset(True)
            progress.show()
            
            # 获取父窗口的ADB收集器
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'adb_collector'):
                main_window = main_window.parent()
                
            if main_window and hasattr(main_window, 'adb_collector') and main_window.adb_collector:
                # 重新获取应用列表
                apps = main_window.adb_collector.get_installed_apps()
                
                # 更新应用列表
                self.set_apps(apps)
                
                progress.close()
                QMessageBox.information(self, "刷新完成", f"成功刷新应用列表，共找到 {len(apps)} 个应用")
            else:
                progress.close()
                QMessageBox.warning(self, "刷新失败", "无法连接到ADB，请检查设备连接")
                
        except Exception as e:
            if 'progress' in locals():
                progress.close()
            QMessageBox.critical(self, "刷新错误", f"刷新应用列表时发生错误：\n{str(e)}")
        
    def on_preset_changed(self, preset_name):
        """预设配置变化"""
        if preset_name == "性能测试":
            self.interval_spin.setValue(1)
            self.duration_spin.setValue(30)
            self.continuous_check.setChecked(False)
        elif preset_name == "长期监控":
            self.interval_spin.setValue(5)
            self.duration_spin.setValue(240)
            self.continuous_check.setChecked(False)
        elif preset_name == "标准监控":
            self.interval_spin.setValue(2)
            self.duration_spin.setValue(60)
            self.continuous_check.setChecked(False)
            
    def save_preset(self):
        """保存预设配置"""
        QMessageBox.information(self, "保存配置", "配置保存功能待实现")
        
    def load_preset(self):
        """加载预设配置"""
        QMessageBox.information(self, "加载配置", "配置加载功能待实现")