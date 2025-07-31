#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
ADB Performance Monitor Tool
Main Program Entry
"""

import sys
import os
import logging
from PyQt5.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QFont

# Add a project path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from gui.main_window import MainWindow

def setup_logging():
    """Setup logging configuration"""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(log_dir, 'android_metrics.log')),
            logging.StreamHandler(sys.stdout)
        ]
    )

def check_dependencies():
    """Check dependencies"""
    missing_deps = []
    
    # Check critical dependencies
    try:
        import PyQt5
    except ImportError:
        missing_deps.append("PyQt5")
        
    try:
        import pyqtgraph
    except ImportError:
        print("Warning: pyqtgraph not found, will use basic charts")
        
    try:
        import sqlalchemy
    except ImportError:
        missing_deps.append("SQLAlchemy")
        
    try:
        import pymysql
    except ImportError:
        missing_deps.append("PyMySQL")
        
    if missing_deps:
        return False, missing_deps
    return True, []

def show_splash_screen(app):
    """Show splash screen"""
    # Create simple splash screen
    splash_pix = QPixmap(400, 300)
    splash_pix.fill(Qt.white)
    
    splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
    splash.setMask(splash_pix.mask())
    
    # Add text
    splash.showMessage(
        "AndroidMetrics\nStarting...\n\n"
        "ADB Performance Monitor\nVersion 1.0.0",
        Qt.AlignCenter,
        Qt.black
    )
    
    splash.show()
    app.processEvents()
    
    return splash

def main():
    """Main function"""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("AndroidMetrics starting...")
    
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("AndroidMetrics")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("AndroidMetrics Team")
    
    # Set application icon and style
    app.setStyle('Fusion')  # Use Fusion style
    
    # Set global font
    font = QFont("Arial", 11)  # 增大字体2个字号
    app.setFont(font)
    
    # Check dependencies
    deps_ok, missing = check_dependencies()
    if not deps_ok:
        QMessageBox.critical(
            None, 
            "Missing Dependencies", 
            f"Missing required dependencies:\n\n" + "\n".join(f"• {dep}" for dep in missing) +
            f"\n\nPlease run:\n/usr/bin/python -m pip install " + " ".join(missing)
        )
        sys.exit(1)
    
    # Show splash screen
    splash = show_splash_screen(app)
    
    try:
        # Create the main window
        QTimer.singleShot(1500, splash.close)  # Close splash after 1.5s
        
        main_window = MainWindow()
        
        # Delay shows main window
        def show_main_window():
            splash.finish(main_window)
            main_window.show()
            
        QTimer.singleShot(1500, show_main_window)
        
        logger.info("AndroidMetrics started successfully")
        
        # Run application
        sys.exit(app.exec_())
        
    except Exception as e:
        logger.error(f"Failed to start AndroidMetrics: {e}")
        QMessageBox.critical(
            None,
            "Startup Failed",
            f"AndroidMetrics startup failed:\n\n{str(e)}\n\n"
            f"Please check log files for more information."
        )
        sys.exit(1)

if __name__ == "__main__":
    main()