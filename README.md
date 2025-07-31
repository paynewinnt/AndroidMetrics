# AndroidMetrics - ADB Performance Monitor Tool

AndroidMetrics 是一个基于 ADB 的 Android 设备性能监控工具，提供实时性能数据采集、可视化分析和数据导出功能。

## 功能特性

### 🚀 核心功能
- **实时性能监控**: CPU使用率、内存占用、网络流量等关键指标
- **应用级监控**: 支持选择特定应用进行深度性能分析
- **数据可视化**: 基于 PyQt5 和 pyqtgraph 的实时图表展示
- **数据存储**: SQLAlchemy + MySQL 数据库存储历史数据
- **数据导出**: 支持导出为 Excel、CSV 等格式

### 📊 监控指标
- CPU 使用率和频率
- 内存使用情况（RSS、VSS、PSS）
- 网络流量（上传/下载）
- 应用启动时间
- 系统负载
- 温度监控

### 🎯 界面特性
- 现代化 GUI 界面
- 实时图表更新
- 配置管理
- 监控会话管理
- 数据维护工具

## 系统要求

- **Python**: 3.7 或更高版本
- **操作系统**: Windows / Linux / macOS
- **Android 设备**: 已开启 USB 调试
- **ADB 工具**: 已安装并添加到 PATH 环境变量

## 安装部署

### 1. 安装依赖包
```bash
/usr/bin/python -m pip install -r requirements.txt
```

或者手动安装：
```bash
/usr/bin/python -m pip install PyQt5 pyqtgraph matplotlib SQLAlchemy PyMySQL pandas numpy openpyxl psutil cryptography configparser
```

### 2. 配置数据库
编辑 `config/database.json` 文件配置数据库连接信息（可选，默认使用 SQLite）。

### 3. 配置监控参数
编辑 `config/monitoring.json` 文件自定义监控参数和采集间隔。

## 使用方法

### 启动应用
```bash
# 启动完整 GUI 界面
/usr/bin/python main.py

# 使用多功能启动器
/usr/bin/python run.py

# 运行演示模式
/usr/bin/python start_demo.py
```

### 基本使用步骤
1. **连接设备**: 通过 USB 连接 Android 设备并开启 USB 调试
2. **选择应用**: 在界面中选择要监控的目标应用
3. **开始监控**: 点击开始按钮启动实时监控
4. **查看数据**: 实时查看性能图表和数据统计
5. **导出数据**: 将监控数据导出为 Excel 或 CSV 格式

## 项目结构

```
android_metrics/
├── main.py                    # 主程序入口
├── run.py                     # 多功能启动器
├── start_demo.py              # 演示模式
├── check_env.py               # 环境检查工具
├── compile_and_test.py        # 编译测试工具
├── requirements.txt           # 依赖包列表
├── config/                    # 配置文件目录
│   ├── database.json         # 数据库配置
│   └── monitoring.json       # 监控配置
├── core/                      # 核心功能模块
│   ├── adb_collector.py      # ADB数据采集器
│   ├── config_manager.py     # 配置管理器
│   └── data_manager.py       # 数据管理器
├── database/                  # 数据库模块
│   ├── connection.py         # 数据库连接管理
│   ├── models.py             # 数据库模型
│   ├── data_storage.py       # 数据存储服务
│   ├── operations.py         # 数据库操作
│   ├── maintenance.py        # 数据库维护
│   └── exceptions.py         # 异常处理
├── gui/                      # 图形界面模块
│   ├── main_window.py        # 主窗口
│   ├── app_selector.py       # 应用选择器
│   ├── monitor_view.py       # 监控视图
│   ├── chart_widgets.py      # 图表组件
│   └── chart_config.py       # 图表配置
└── utils/                    # 工具模块
    ├── export.py             # 数据导出
    └── validators.py         # 数据验证
```

## 开发调试

### 环境检查
```bash
# 检查运行环境和依赖
/usr/bin/python check_env.py
```

### 编译测试
```bash
# 运行完整的编译和测试
/usr/bin/python compile_and_test.py
```

## 数据库配置

### SQLite（默认）
默认使用 SQLite 数据库，无需额外配置。

### MySQL（可选）
编辑 `config/database.json`：
```json
{
    "type": "mysql",
    "host": "localhost",
    "port": 3306,
    "username": "your_username",
    "password": "your_password",
    "database": "android_metrics"
}
```

## 故障排除

### 常见问题
1. **ADB 连接失败**: 确保设备已开启 USB 调试，ADB 工具已正确安装
2. **依赖包缺失**: 运行 `check_env.py` 检查环境，根据提示安装缺失包
3. **数据库连接失败**: 检查数据库配置文件和连接参数
4. **GUI 启动失败**: 确保已安装 PyQt5，检查显示环境

### 日志文件
应用运行时会在 `logs/` 目录下生成日志文件，用于问题诊断。

## 许可证

本项目采用 MIT 许可证，详见 LICENSE 文件。

## 贡献

欢迎提交 Issue 和 Pull Request 来改进这个项目。

## 更新日志

### v1.0.0
- 初始版本发布
- 基础性能监控功能
- GUI 界面和数据可视化
- 数据库存储和导出功能