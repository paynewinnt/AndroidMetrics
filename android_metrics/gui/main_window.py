# -*- coding: utf-8 -*-
import sys
import os
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                           QTabWidget, QLabel, QStatusBar, QMenuBar, QAction,
                           QMessageBox, QProgressBar, QSplitter)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QIcon

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .app_selector import AppSelectorWidget
from .monitor_view import MonitorViewWidget
from .chart_config import ChartConfigDialog, ChartThemeManager
# 导入核心组件
try:
    from core.adb_collector import ADBCollector
    ADB_COLLECTOR_AVAILABLE = True
except ImportError as e:
    print(f"Warning: ADB Collector not available: {e}")
    ADBCollector = None
    ADB_COLLECTOR_AVAILABLE = False

# 尝试导入优化配置管理器，如果失败则使用基础版本
try:
    from core.optimized_config import optimized_config as config_manager_instance
    OPTIMIZED_CONFIG_AVAILABLE = True
except ImportError:
    config_manager_instance = None
    OPTIMIZED_CONFIG_AVAILABLE = False

# 尝试导入基础配置管理器
try:
    from core.config_manager import ConfigManager
    CONFIG_MANAGER_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Config Manager not available: {e}")
    ConfigManager = None
    CONFIG_MANAGER_AVAILABLE = False

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # 初始标题，稍后会根据优化模式更新
        self.setWindowTitle("ADB Performance Monitor")
        self.setGeometry(100, 100, 1600, 900)
        self.setFixedSize(1600, 900)  # 设置固定窗口大小，不允许调整
        
        # Initialize core components
        self.adb_collector = None
        
        # 使用优化配置管理器（如果可用）
        if OPTIMIZED_CONFIG_AVAILABLE and config_manager_instance:
            self.config_manager = config_manager_instance
            self.optimized_mode = True
        elif CONFIG_MANAGER_AVAILABLE and ConfigManager:
            self.config_manager = ConfigManager("config")
            self.optimized_mode = False
        else:
            # 创建一个基本的配置管理器作为后备
            self.config_manager = self._create_fallback_config_manager()
            self.optimized_mode = False
            
        # 初始化图表主题管理器（有错误处理）
        try:
            self.chart_theme_manager = ChartThemeManager()
        except Exception as e:
            print(f"Warning: Chart Theme Manager initialization failed: {e}")
            self.chart_theme_manager = None
            
        self.is_monitoring = False
        
        # Set font
        font = QFont("Arial", 11)  # 增大字体2个字号
        self.setFont(font)
        
        # Initialize UI
        self.init_ui()
        
        # Update window title based on optimization mode
        self.update_window_title()
        
        # Initialize ADB connection
        self.init_adb_connection()
    
    def _create_fallback_config_manager(self):
        """创建一个后备配置管理器"""
        class FallbackConfigManager:
            def __init__(self):
                self.config = {
                    'sample_interval': 3,
                    'max_samples': 1000,
                    'auto_save': True
                }
            
            def get_config(self, key=None, default=None):
                if key is None:
                    return self.config
                return self.config.get(key, default)
            
            def set_config(self, key, value):
                self.config[key] = value
            
            def save_config(self):
                pass  # 后备版本不保存配置
        
        return FallbackConfigManager()
        
    def init_ui(self):
        """Initialize user interface"""
        # Create menu bar
        self.create_menu_bar()
        
        # Create status bar
        self.create_status_bar()
        
        # Create main window widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create main layout
        main_layout = QVBoxLayout(central_widget)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # Create app selection and monitoring tabs
        self.create_tabs()
        
        # Apply styles
        self.apply_styles()
    
    def update_window_title(self):
        """更新窗口标题以反映优化模式"""
        base_title = "ADB Performance Monitor"
        if self.optimized_mode:
            self.setWindowTitle(f"{base_title} - v2.0")
        else:
            self.setWindowTitle(base_title)
        
    def create_menu_bar(self):
        """Create menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        
        # Export data
        export_action = QAction('Export Data', self)
        export_action.setShortcut('Ctrl+E')
        export_action.triggered.connect(self.export_data)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        # Exit
        exit_action = QAction('Exit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Settings menu
        settings_menu = menubar.addMenu('Settings')
        
        # Chart configuration
        chart_config_action = QAction('Chart Settings', self)
        chart_config_action.triggered.connect(self.configure_charts)
        settings_menu.addAction(chart_config_action)
        
        # ADB configuration
        adb_config_action = QAction('ADB Settings', self)
        adb_config_action.triggered.connect(self.configure_adb)
        settings_menu.addAction(adb_config_action)
        
        # Database configuration
        db_config_action = QAction('Database Settings', self)
        db_config_action.triggered.connect(self.configure_database)
        settings_menu.addAction(db_config_action)
        
        # Help menu
        help_menu = menubar.addMenu('Help')
        
        # About
        about_action = QAction('About', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
    def create_status_bar(self):
        """Create status bar"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # ADB connection status
        self.adb_status_label = QLabel("ADB: Not Connected")
        self.status_bar.addWidget(self.adb_status_label)
        
        # Monitoring status
        self.monitor_status_label = QLabel("Monitor: Not Started")
        self.status_bar.addWidget(self.monitor_status_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)
        
    def create_tabs(self):
        """Create tab pages"""
        # App selection tab
        self.app_selector = AppSelectorWidget()
        self.tab_widget.addTab(self.app_selector, "App Selection")
        
        # Monitoring display tab
        self.monitor_view = MonitorViewWidget()
        self.tab_widget.addTab(self.monitor_view, "Performance Monitor")
        
        # Connect signals
        self.app_selector.apps_selected.connect(self.on_apps_selected)
        self.app_selector.monitoring_started.connect(self.start_monitoring)
        self.app_selector.monitoring_stopped.connect(self.stop_monitoring)
        
    def apply_styles(self):
        """Apply styles"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            
            QTabWidget::pane {
                border: 1px solid #c0c0c0;
                background-color: white;
            }
            
            QTabWidget::tab-bar {
                left: 5px;
            }
            
            QTabBar::tab {
                background-color: #e0e0e0;
                padding: 8px 16px;
                margin-right: 2px;
                border: 1px solid #c0c0c0;
                border-bottom: none;
            }
            
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: 1px solid white;
            }
            
            QTabBar::tab:hover {
                background-color: #f0f0f0;
            }
            
            QStatusBar {
                background-color: #e0e0e0;
                border-top: 1px solid #c0c0c0;
            }
            
            QLabel {
                color: #333333;
            }
            
            QProgressBar {
                border: 1px solid #c0c0c0;
                border-radius: 3px;
                text-align: center;
            }
            
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 2px;
            }
        """)
        
    def init_adb_connection(self):
        """Initialize ADB connection"""
        try:
            if ADB_COLLECTOR_AVAILABLE and ADBCollector:
                self.adb_collector = ADBCollector()
                if self.adb_collector.check_adb_connection():
                    self.adb_status_label.setText(f"ADB: Connected ({self.adb_collector.device_id})")
                    self.adb_status_label.setStyleSheet("color: green;")
                    
                    # Get app list
                    apps = self.adb_collector.get_installed_apps()
                    if hasattr(self, 'app_selector') and self.app_selector:
                        self.app_selector.set_apps(apps)
                else:
                    if hasattr(self, 'adb_status_label'):
                        self.adb_status_label.setText("ADB: Connection Failed")
                        self.adb_status_label.setStyleSheet("color: red;")
                    self.show_adb_error()
            else:
                # ADB Collector not available
                if hasattr(self, 'adb_status_label'):
                    self.adb_status_label.setText("ADB: Not Available")
                    self.adb_status_label.setStyleSheet("color: orange;")
                print("Warning: ADB Collector is not available")
                
        except Exception as e:
            if hasattr(self, 'adb_status_label'):
                self.adb_status_label.setText("ADB: Error")
                self.adb_status_label.setStyleSheet("color: red;")
            print(f"ADB Connection Error: {e}")
            # Only show message box if it's a critical error and GUI is ready
            if hasattr(self, 'isVisible') and self.isVisible():
                QMessageBox.critical(self, "ADB Connection Error", f"Unable to connect to ADB:\n{str(e)}")
            
    def show_adb_error(self):
        """Show ADB connection error information"""
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("ADB Connection Failed")
        msg.setText("Unable to connect to Android device")
        msg.setInformativeText(
            "Please check the following:\n"
            "1. Device is connected via USB with USB debugging enabled\n"
            "2. ADB drivers are correctly installed\n"
            "3. Device has authorized this computer for debugging\n"
            "4. ADB is in system PATH"
        )
        msg.setDetailedText(
            "Solutions:\n"
            "• Go to Settings > Developer Options > USB Debugging on device\n"
            "• Reconnect USB cable\n"
            "• Run 'adb devices' command to check device status\n"
            "• Try 'adb kill-server && adb start-server'"
        )
        msg.exec_()
        
    def on_apps_selected(self, selected_apps):
        """App selection completed"""
        self.monitor_view.set_selected_apps(selected_apps)
        
    def start_monitoring(self, config):
        """Start monitoring"""
        if not self.adb_collector:
            QMessageBox.warning(self, "Warning", "ADB not connected, cannot start monitoring")
            return
            
        self.is_monitoring = True
        self.monitor_status_label.setText("Monitor: Running")
        self.monitor_status_label.setStyleSheet("color: green;")
        
        # Switch to monitoring tab
        self.tab_widget.setCurrentIndex(1)
        
        # Start monitoring
        self.monitor_view.start_monitoring(self.adb_collector, config)
        
    def stop_monitoring(self):
        """Stop monitoring"""
        self.is_monitoring = False
        self.monitor_status_label.setText("Monitor: Stopped")
        self.monitor_status_label.setStyleSheet("color: red;")
        
        # Stop monitoring
        self.monitor_view.stop_monitoring()
        
    def export_data(self):
        """Export data"""
        if hasattr(self.monitor_view, 'export_data'):
            self.monitor_view.export_data()
        else:
            QMessageBox.information(self, "Information", "No data to export")
            
    def configure_charts(self):
        """Configure chart settings"""
        dialog = ChartConfigDialog(self)
        dialog.config_changed.connect(self.on_chart_config_changed)
        dialog.exec_()
        
    def on_chart_config_changed(self, config):
        """Handle chart configuration changes"""
        # Apply configuration to monitoring view
        if hasattr(self.monitor_view, 'apply_chart_config'):
            self.monitor_view.apply_chart_config(config)
            
    def configure_adb(self):
        """Configure ADB settings"""
        QMessageBox.information(self, "ADB Settings", "ADB configuration feature to be implemented")
        
    def configure_database(self):
        """Configure database settings"""
        QMessageBox.information(self, "Database Settings", "Database configuration feature to be implemented")
        
    def show_about(self):
        """Show about dialog"""
        about_text = """
        <h3>AndroidMetrics</h3>
        <p>ADB-based Android device performance monitoring tool</p>
        <p><b>Version:</b> 1.0.0</p>
        <p><b>Features:</b></p>
        <ul>
        <li>Real-time monitoring of CPU, memory, network, power</li>
        <li>Multiple app simultaneous monitoring</li>
        <li>Visualization with interactive charts</li>
        <li>Data export and historical analysis</li>
        </ul>
        <p><b>System Requirements:</b></p>
        <ul>
        <li>Android device with USB debugging enabled</li>
        <li>ADB tools correctly installed</li>
        <li>Python 3.7+ environment</li>
        </ul>
        """
        QMessageBox.about(self, "About AndroidMetrics", about_text)
        
    def closeEvent(self, event):
        """Window close event"""
        if self.is_monitoring:
            reply = QMessageBox.question(
                self, 
                'Confirm Exit', 
                'Monitoring is in progress, are you sure you want to exit?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.stop_monitoring()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()