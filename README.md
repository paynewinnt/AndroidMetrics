# AndroidMetrics - 高性能Android设备监控工具

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/)
[![PyQt5](https://img.shields.io/badge/GUI-PyQt5-green.svg)](https://pypi.org/project/PyQt5/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

AndroidMetrics 是一个基于ADB的专业Android设备性能监控工具，采用现代化GUI界面，提供实时性能数据采集、智能分析和数据可视化功能。

## ✨ 核心特性

### 🚀 实时监控
- **多维度指标**: CPU使用率、内存占用、网络流量、电池状态
- **应用级分析**: 支持选择特定应用的深度性能监控
- **高频数据采集**: 可配置采样间隔(1-5秒)，支持长期监控(最长4小时)
- **智能缓存**: 多级缓存系统，提升数据获取效率

### 📊 数据可视化
- **实时图表**: 基于PyQtGraph的高性能实时图表
- **多种图表类型**: 线图、柱状图、饼图等多种展示方式
- **主题定制**: 支持多种图表主题和配色方案
- **数据导出**: Excel、CSV格式数据导出功能

### 🗄️ 数据管理
- **双数据库支持**: 默认SQLite，可选MySQL数据库
- **数据持久化**: 完整的监控会话数据存储
- **数据维护**: 自动数据清理和数据库优化
- **异常处理**: 完善的数据库异常恢复机制

### 🎯 用户体验
- **现代化界面**: 基于PyQt5的专业GUI设计
- **配置预设**: 内置多种监控场景预设配置
- **错误提示**: 智能的依赖检查和错误诊断
- **启动画面**: 专业的应用启动体验

## 📋 系统要求

- **Python**: 3.7或更高版本
- **操作系统**: Windows / Linux / macOS
- **Android设备**: 已开启USB调试模式
- **ADB工具**: 已安装Android SDK Platform Tools

## 🔧 安装部署

### 1. 克隆项目
```bash
git clone https://github.com/paynewinnt/AndroidMetrics.git
cd AndroidMetrics
```

### 2. 安装依赖
```bash
# 使用requirements.txt安装
pip install -r requirements.txt

# 或手动安装核心依赖
pip install PyQt5==5.15.9 pyqtgraph==0.13.3 SQLAlchemy==2.0.19 PyMySQL==1.1.0 pandas==2.0.3 matplotlib==3.7.2
```

### 3. 环境检查
```bash
# 检查运行环境和依赖
python check_env.py
```

### 4. 设备准备
- 启用Android设备的开发者选项
- 开启USB调试模式
- 通过USB连接设备到电脑
- 确认ADB连接: `adb devices`

## 🚀 使用指南

### 启动应用
```bash
# 启动主程序
python main.py
```

### 基本使用流程

1. **设备连接检测**
   - 应用启动后自动检测ADB连接的设备
   - 如无设备连接，会显示相应提示

2. **选择监控应用**
   - 在应用选择器中选择要监控的目标应用
   - 支持同时监控多个应用(最多6个)

3. **配置监控参数**
   - 设置采样间隔(1-5秒)
   - 选择监控时长(5分钟-4小时)
   - 配置性能阈值和告警

4. **开始监控**
   - 点击开始按钮启动实时监控
   - 观察实时性能图表和数据统计

5. **数据分析与导出**
   - 查看历史监控数据
   - 导出数据为Excel或CSV格式

## 📁 项目架构

```
AndroidMetrics/
├── README.md                   # 项目说明文档
├── PERFORMANCE_OPTIMIZATION.md # 性能优化指南
├── main.py                    # 应用程序入口
├── requirements.txt           # Python依赖包
├── check_env.py              # 环境检查工具
│
├── core/                     # 核心功能模块
│   ├── adb_collector.py      # ADB数据采集器(支持缓存优化)
│   ├── config_manager.py     # 配置管理器
│   ├── data_manager.py       # 数据管理器
│   ├── performance_monitor.py # 性能监控核心
│   └── optimized_config.py    # 性能优化配置
│
├── database/                 # 数据库模块
│   ├── connection.py         # 数据库连接管理
│   ├── models.py             # SQLAlchemy数据模型
│   ├── data_storage.py       # 数据存储服务
│   ├── operations.py         # 数据库操作接口
│   ├── maintenance.py        # 数据库维护工具
│   └── exceptions.py         # 数据库异常处理
│
├── gui/                      # 图形用户界面
│   ├── main_window.py        # 主窗口界面
│   ├── app_selector.py       # 应用选择器
│   ├── monitor_view.py       # 监控视图组件
│   ├── chart_widgets.py      # 图表组件
│   └── chart_config.py       # 图表配置和主题
│
├── utils/                    # 工具模块
│   ├── export.py             # 数据导出工具
│   └── validators.py         # 数据验证工具
│
├── config/                   # 配置文件
│   ├── database.json         # 数据库配置
│   ├── monitoring.json       # 监控参数配置
│   ├── performance.json      # 性能优化配置
│   ├── gui.json             # 界面配置
│   └── alerts.json          # 告警配置
│
└── logs/                     # 日志文件目录
    └── android_metrics.log
```

## ⚙️ 配置说明

### 监控配置 (monitoring.json)
```json
{
  "monitoring": {
    "sample_interval": 2,        // 采样间隔(秒)
    "duration_minutes": 20,      // 监控时长(分钟)
    "max_apps": 6,              // 最大监控应用数
    "auto_start": false         // 是否自动开始监控
  },
  "thresholds": {
    "cpu_max": 90,              // CPU使用率告警阈值
    "memory_max": 80,           // 内存使用率告警阈值
    "network_max": 1000,        // 网络流量告警阈值(KB/s)
    "fps_min": 30               // 最低FPS告警阈值
  }
}
```

### 数据库配置 (database.json)
```json
{
  "type": "sqlite",             // 数据库类型: sqlite/mysql
  "host": "localhost",          // MySQL主机(仅MySQL)
  "port": 3306,                // MySQL端口(仅MySQL)
  "username": "user",           // MySQL用户名(仅MySQL)
  "password": "password",       // MySQL密码(仅MySQL)
  "database": "android_metrics" // 数据库名称
}
```

## 🔍 监控指标详解

### CPU监控
- **CPU使用率**: 应用和系统整体CPU占用百分比
- **CPU频率**: 当前CPU运行频率
- **进程数**: 活跃进程数量统计

### 内存监控  
- **RSS内存**: 物理内存占用(Resident Set Size)
- **VSS内存**: 虚拟内存占用(Virtual Set Size)
- **PSS内存**: 按比例分配的内存占用(Proportional Set Size)
- **内存泄漏检测**: 内存使用趋势分析

### 网络监控
- **上传流量**: 实时上传数据量统计
- **下载流量**: 实时下载数据量统计
- **网络延迟**: 网络响应时间监控

### 电池监控
- **电池电量**: 实时电池剩余电量
- **充电状态**: 充电/放电状态检测
- **温度监控**: 设备温度实时监控

## 🚨 故障排除

### 常见问题解决

#### 1. ADB连接问题
```bash
# 检查ADB连接
adb devices

# 重启ADB服务
adb kill-server
adb start-server

# 检查USB调试是否开启
adb shell getprop ro.debuggable
```

#### 2. 依赖包问题
```bash
# 检查Python版本
python --version

# 重新安装依赖
pip install -r requirements.txt --force-reinstall

# 检查PyQt5安装
python -c "import PyQt5; print(PyQt5.__version__)"
```

#### 3. 数据库连接问题
- 检查 `config/database.json` 配置
- 确认MySQL服务运行状态(如使用MySQL)
- 查看日志文件 `logs/android_metrics.log`

#### 4. 性能问题
- 降低采样频率(增加采样间隔)
- 减少同时监控的应用数量
- 关闭不必要的图表显示
- 参考 `PERFORMANCE_OPTIMIZATION.md` 优化指南

### 日志分析
应用运行日志保存在 `logs/android_metrics.log`，包含：
- 应用启动和初始化信息
- ADB命令执行状态
- 数据库操作记录
- 错误和异常信息

## 🔄 更新日志

### v1.0.0 (当前版本)
- ✅ 完整的ADB性能监控功能
- ✅ 现代化PyQt5 GUI界面
- ✅ 多级缓存优化系统
- ✅ SQLite/MySQL双数据库支持
- ✅ 数据导出和可视化功能
- ✅ 完善的错误处理和日志系统

## 🤝 贡献指南

欢迎参与AndroidMetrics项目的改进！

### 贡献方式
1. Fork本项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建Pull Request

### 开发环境设置
```bash
# 克隆开发版本
git clone https://github.com/paynewinnt/AndroidMetrics.git
cd AndroidMetrics

# 安装开发依赖
pip install -r requirements.txt

# 运行环境检查
python check_env.py

# 启动开发版本
python main.py
```

## 📄 许可证

本项目采用 [MIT许可证](LICENSE) - 详见LICENSE文件

## 🙏 致谢

- [PyQt5](https://pypi.org/project/PyQt5/) - 现代化GUI框架
- [PyQtGraph](https://pyqtgraph.readthedocs.io/) - 高性能图表库
- [SQLAlchemy](https://sqlalchemy.org/) - Python SQL工具包
- [Android Debug Bridge](https://developer.android.com/studio/command-line/adb) - Android调试桥

## 📞 支持与反馈

- **Issues**: [GitHub Issues](https://github.com/paynewinnt/AndroidMetrics/issues)
- **Discussions**: [GitHub Discussions](https://github.com/paynewinnt/AndroidMetrics/discussions)
- **Wiki**: [项目Wiki](https://github.com/paynewinnt/AndroidMetrics/wiki)

---

> 💡 **提示**: 如遇到问题，请先查看[故障排除](#-故障排除)部分，或查看日志文件获取详细错误信息。