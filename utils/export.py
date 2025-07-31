# -*- coding: utf-8 -*-
"""
数据导出工具
支持导出到多种格式：CSV、Excel、JSON
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

# 配置日志
logger = logging.getLogger(__name__)

class DataExporter:
    """数据导出器"""
    
    def __init__(self):
        self.supported_formats = ['csv', 'excel', 'json', 'xlsx']
        
    def export_session_data(self, session_data: Dict[str, Any], 
                          export_format: str, 
                          output_path: str = None) -> Optional[str]:
        """导出会话数据到指定格式"""
        try:
            export_format = export_format.lower()
            if export_format not in self.supported_formats:
                raise ValueError(f"不支持的导出格式: {export_format}")
                
            # 生成输出文件路径
            if not output_path:
                session_name = session_data.get('session_info', {}).get('session_name', 'unknown')
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"metrics_export_{session_name}_{timestamp}"
                output_path = os.path.join(os.getcwd(), 'exports', f"{filename}.{export_format}")
                
            # 确保输出目录存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # 根据格式调用相应的导出方法
            if export_format == 'json':
                return self._export_to_json(session_data, output_path)
            else:
                logger.warning(f"格式 {export_format} 需要额外依赖，当前只支持JSON")
                return None
                
        except Exception as e:
            logger.error(f"数据导出失败: {e}")
            return None
            
    def _export_to_json(self, session_data: Dict[str, Any], output_path: str) -> str:
        """导出到JSON格式"""
        try:
            if not output_path.endswith('.json'):
                output_path += '.json'
                
            # 处理时间戳序列化
            def json_serializer(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
                
            # 添加导出元数据
            export_data = {
                'export_info': {
                    'export_time': datetime.now().isoformat(),
                    'format_version': '1.0',
                    'exporter': 'AndroidMetrics Data Exporter'
                },
                'data': session_data
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False, 
                         default=json_serializer)
                         
            logger.info(f"JSON导出完成: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"JSON导出失败: {e}")
            raise
            
    def create_export_report(self, session_data: Dict[str, Any], output_path: str = None) -> str:
        """创建导出报告"""
        try:
            if not output_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = os.path.join(os.getcwd(), 'exports', f'report_{timestamp}.html')
                
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            session_info = session_data.get('session_info', {})
            
            html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AndroidMetrics 性能监控报告</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
        .section {{ margin: 20px 0; }}
        .stats {{ display: flex; gap: 20px; }}
        .stat-box {{ background-color: #f9f9f9; padding: 15px; border-radius: 5px; flex: 1; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .summary {{ background-color: #e7f3ff; padding: 15px; border-radius: 5px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>AndroidMetrics 性能监控报告</h1>
        <p><strong>会话名称:</strong> {session_info.get('session_name', 'N/A')}</p>
        <p><strong>设备ID:</strong> {session_info.get('device_id', 'N/A')}</p>
        <p><strong>开始时间:</strong> {session_info.get('start_time', 'N/A')}</p>
        <p><strong>结束时间:</strong> {session_info.get('end_time', 'N/A')}</p>
        <p><strong>报告生成时间:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
    <div class="section">
        <h2>数据统计</h2>
        <div class="stats">
            <div class="stat-box">
                <h3>系统性能数据</h3>
                <p>{len(session_data.get('system_performance', []))} 个数据点</p>
            </div>
            <div class="stat-box">
                <h3>应用性能数据</h3>
                <p>{len(session_data.get('app_performance', {}))} 个应用</p>
            </div>
            <div class="stat-box">
                <h3>网络统计数据</h3>
                <p>{len(session_data.get('network_stats', {}))} 个应用</p>
            </div>
            <div class="stat-box">
                <h3>FPS数据</h3>
                <p>{len(session_data.get('fps_data', {}))} 个应用</p>
            </div>
        </div>
    </div>
</body>
</html>"""
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
            logger.info(f"HTML报告生成完成: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"生成HTML报告失败: {e}")
            raise


# 全局数据导出器实例
data_exporter = DataExporter()