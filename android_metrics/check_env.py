#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
环境检查脚本
检查虚拟环境是否正确配置，所有依赖是否已安装
"""

import sys
import os
import importlib
from typing import List, Tuple

def check_python_version() -> Tuple[bool, str]:
    """检查Python版本"""
    version = sys.version_info
    if version.major == 3 and version.minor >= 7:
        return True, f"✅ Python版本: {version.major}.{version.minor}.{version.micro}"
    else:
        return False, f"❌ Python版本过低: {version.major}.{version.minor}.{version.micro} (需要3.7+)"

def check_required_packages() -> List[Tuple[str, bool, str]]:
    """检查必需的包"""
    required_packages = [
        ('PyQt5', 'PyQt5'),
        ('pyqtgraph', 'pyqtgraph'),
        ('matplotlib', 'matplotlib'),
        ('sqlalchemy', 'SQLAlchemy'),
        ('pymysql', 'PyMySQL'),
        ('pandas', 'pandas'),
        ('numpy', 'numpy'),
        ('openpyxl', 'openpyxl'),
        ('psutil', 'psutil'),
        ('cryptography', 'cryptography'),
        ('configparser', 'configparser')
    ]
    
    results = []
    for module_name, package_name in required_packages:
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, '__version__', 'unknown')
            results.append((package_name, True, f"✅ {package_name}: {version}"))
        except ImportError:
            results.append((package_name, False, f"❌ {package_name}: 未安装"))
    
    return results

def check_database_modules() -> List[Tuple[str, bool, str]]:
    """检查数据库模块"""
    database_modules = [
        ('database.connection', '数据库连接管理'),
        ('database.models', '数据库模型'),
        ('database.data_storage', '数据存储服务'),
        ('database.operations', '数据库操作'),
        ('database.maintenance', '数据库维护'),
        ('database.exceptions', '异常处理')
    ]
    
    results = []
    # 添加当前目录到Python路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    for module_name, description in database_modules:
        try:
            importlib.import_module(module_name)
            results.append((description, True, f"✅ {description}: 可用"))
        except ImportError as e:
            results.append((description, False, f"❌ {description}: {str(e)}"))
    
    return results

def check_python_environment() -> Tuple[bool, str]:
    """检查Python环境"""
    return True, f"✅ 系统Python环境: {sys.prefix}"

def main():
    """主检查函数"""
    print("=" * 60)
    print("🔍 AndroidMetrics 环境检查")
    print("=" * 60)
    
    # 检查Python版本
    python_ok, python_msg = check_python_version()
    print(f"\n📋 Python环境:")
    print(f"  {python_msg}")
    
    # 检查Python环境
    python_env_ok, python_env_msg = check_python_environment()
    print(f"\n🏠 Python环境:")
    print(f"  {python_env_msg}")
    
    # 检查必需包
    print(f"\n📦 依赖包检查:")
    package_results = check_required_packages()
    all_packages_ok = True
    
    for package_name, ok, msg in package_results:
        print(f"  {msg}")
        if not ok:
            all_packages_ok = False
    
    # 检查数据库模块
    print(f"\n🗄️  数据库模块检查:")
    db_results = check_database_modules()
    all_db_ok = True
    
    for module_name, ok, msg in db_results:
        print(f"  {msg}")
        if not ok:
            all_db_ok = False
    
    # 总结
    print(f"\n" + "=" * 60)
    print("📊 检查结果总结:")
    
    if python_ok and python_env_ok and all_packages_ok and all_db_ok:
        print("🎉 所有检查通过！环境配置正确。")
        print("\n🚀 可以运行以下命令启动程序:")
        print("   /usr/bin/python main.py")
        return 0
    else:
        print("⚠️  发现问题，请修复后重新检查。")
        
        if not python_ok:
            print("   - 请升级Python到3.7或更高版本")
        
        if not all_packages_ok:
            print("   - 请安装缺失的依赖包: /usr/bin/python -m pip install -r requirements.txt")
        
        if not all_db_ok:
            print("   - 检查数据库模块导入错误")
        
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)