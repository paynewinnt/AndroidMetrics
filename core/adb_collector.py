import subprocess
import re
import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import threading
import queue
from collections import deque, defaultdict
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class EnhancedCache:
    """多级缓存系统"""
    def __init__(self):
        self.l1_cache = {}  # 热数据缓存 (TTL: 30s)
        self.l2_cache = {}  # 温数据缓存 (TTL: 60s)  
        self.cache_stats = defaultdict(int)
        self.max_l1_size = 100
        self.max_l2_size = 500
        
    def get(self, key: str, fetch_func=None, ttl: int = 30):
        current_time = time.time()
        
        # L1缓存检查
        if key in self.l1_cache:
            if current_time - self.l1_cache[key]['time'] < ttl:
                self.cache_stats['l1_hit'] += 1
                return self.l1_cache[key]['data']
            else:
                del self.l1_cache[key]
                
        # L2缓存检查
        if key in self.l2_cache:
            if current_time - self.l2_cache[key]['time'] < ttl * 2:
                # 提升到L1
                self.l1_cache[key] = self.l2_cache[key]
                del self.l2_cache[key]
                self.cache_stats['l2_hit'] += 1
                return self.l1_cache[key]['data']
            else:
                del self.l2_cache[key]
        
        # 缓存未命中
        if fetch_func:
            data = fetch_func()
            self.put(key, data, current_time)
            self.cache_stats['miss'] += 1
            return data
            
        self.cache_stats['miss'] += 1
        return None
        
    def put(self, key: str, data, timestamp: float = None):
        if timestamp is None:
            timestamp = time.time()
            
        # L1缓存管理
        if len(self.l1_cache) >= self.max_l1_size:
            # 移除最老的条目到L2
            oldest_key = min(self.l1_cache.keys(), 
                           key=lambda k: self.l1_cache[k]['time'])
            self.l2_cache[oldest_key] = self.l1_cache[oldest_key]
            del self.l1_cache[oldest_key]
            
        self.l1_cache[key] = {'data': data, 'time': timestamp}
        
        # L2缓存大小管理
        if len(self.l2_cache) >= self.max_l2_size:
            oldest_key = min(self.l2_cache.keys(),
                           key=lambda k: self.l2_cache[k]['time'])
            del self.l2_cache[oldest_key]
    
    def get_stats(self):
        total_requests = sum(self.cache_stats.values())
        if total_requests == 0:
            return {"hit_rate": 0, "l1_hit_rate": 0, "l2_hit_rate": 0}
            
        hit_rate = (self.cache_stats['l1_hit'] + self.cache_stats['l2_hit']) / total_requests
        return {
            "hit_rate": hit_rate,
            "l1_hit_rate": self.cache_stats['l1_hit'] / total_requests,
            "l2_hit_rate": self.cache_stats['l2_hit'] / total_requests,
            "total_requests": total_requests
        }

class BatchADBExecutor:
    """批量ADB命令执行器"""
    def __init__(self, device_id: str = None, max_workers: int = 6):
        self.device_id = device_id
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.command_queue = queue.Queue()
        self.batch_results = {}
        
    def execute_batch(self, commands: List[Tuple[str, str]], timeout: int = 10) -> Dict[str, str]:
        """
        批量执行ADB命令
        commands: [(command_id, command), ...]
        返回: {command_id: result, ...}
        """
        futures = {}
        
        for cmd_id, command in commands:
            future = self.executor.submit(self._execute_single_command, command, timeout)
            futures[cmd_id] = future
            
        results = {}
        for cmd_id, future in futures.items():
            try:
                results[cmd_id] = future.result(timeout=timeout + 2)
            except Exception as e:
                logger.debug(f"Command {cmd_id} failed: {e}")
                results[cmd_id] = None
                
        return results
        
    def _execute_single_command(self, command: str, timeout: int) -> Optional[str]:
        """执行单个ADB命令"""
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(command.split())
        
        try:
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=timeout,
                check=True
            )
            return result.stdout.strip()
        except Exception:
            return None

class ADBCollector:
    def __init__(self, timeout: int = 5, retry_count: int = 1):
        # Optimized timeout settings for better performance vs reliability balance
        self.timeout = timeout
        self.retry_count = retry_count
        self.device_id = None
        self._last_network_stats = {}
        
        # Enhanced multi-level cache system
        self.enhanced_cache = EnhancedCache()
        self._uid_cache = {}  # UID缓存，较长TTL
        self._compiled_patterns = {}  # 预编译正则表达式
        
        # Basic cache system for ADB commands
        self._cache = {}  # 基础命令缓存
        self._cache_timeout = 30.0  # 缓存超时时间（秒）
        
        # Performance tracking and optimization
        self._command_times = {}
        self._slow_commands = set()
        self._performance_stats = defaultdict(float)
        
        # Batch executor for parallel ADB commands
        self.batch_executor = BatchADBExecutor(self.device_id, max_workers=8)
        
        # Initialize compiled regex patterns
        self._init_regex_patterns()
        
        # Optimize data collection intervals based on data type
        self._collection_intervals = {
            'system_performance': 3.0,  # 系统性能每3秒采集
            'app_basic': 2.0,           # 应用基础信息每2秒
            'app_detailed': 5.0,        # 应用详细信息每5秒
            'network_stats': 4.0,       # 网络统计每4秒
            'device_info': 60.0         # 设备信息每分钟
        }
        self._last_collection_time = defaultdict(float)
        
    def _init_regex_patterns(self):
        """Initialize compiled regex patterns for better performance"""
        self._compiled_patterns = {
            'memory_pss': [
                re.compile(r'TOTAL\s+(\d+)', re.IGNORECASE),
                re.compile(r'TOTAL PSS:\s+(\d+)', re.IGNORECASE),
                re.compile(r'Total\s+PSS:\s+(\d+)', re.IGNORECASE),
                re.compile(r'PSS\s+Total:\s+(\d+)', re.IGNORECASE)
            ],
            'power_consumption': [
                # Original patterns
                re.compile(r'Estimated power use.*?(\d+(?:\.\d+)?)\s*mAh', re.IGNORECASE),
                re.compile(r'Power use \(mAh\):\s*(\d+(?:\.\d+)?)', re.IGNORECASE),
                re.compile(r'Total.*?(\d+(?:\.\d+)?)\s*mAh', re.IGNORECASE),
                re.compile(r'Consumption:\s*(\d+(?:\.\d+)?)\s*mAh', re.IGNORECASE),
                # Additional patterns for different Android versions
                re.compile(r'Power:\s*(\d+(?:\.\d+)?)\s*mAh', re.IGNORECASE),
                re.compile(r'Battery drain:\s*(\d+(?:\.\d+)?)\s*mAh', re.IGNORECASE),
                re.compile(r'mAh:\s*(\d+(?:\.\d+)?)', re.IGNORECASE),
                re.compile(r'(\d+(?:\.\d+)?)\s*mAh', re.IGNORECASE),
                # Pattern for newer Android versions
                re.compile(r'Estimated power.*?(\d+(?:\.\d+)?)mAh', re.IGNORECASE),
                re.compile(r'App battery usage.*?(\d+(?:\.\d+)?)', re.IGNORECASE),
                # Pattern without "mAh" unit for percentage-based power
                re.compile(r'Power usage:\s*(\d+(?:\.\d+)?)%', re.IGNORECASE),
                re.compile(r'Battery:\s*(\d+(?:\.\d+)?)%', re.IGNORECASE)
            ],
            'fps_alternative': [
                re.compile(r'RefreshRate[:\s]+(\d+(?:\.\d+)?)', re.IGNORECASE),
                re.compile(r'FPS[:\s]+(\d+(?:\.\d+)?)', re.IGNORECASE),
                re.compile(r'Frame rate[:\s]+(\d+(?:\.\d+)?)', re.IGNORECASE)
            ],
            'uid_lookup': re.compile(r'userId=(\d+)', re.IGNORECASE)
        }
        
    def check_adb_connection(self) -> bool:
        try:
            result = self._run_adb_command("devices")
            if result and "device" in result:
                devices = self._parse_devices(result)
                if devices:
                    self.device_id = devices[0]
                    logger.info(f"ADB connected to device: {self.device_id}")
                    return True
            logger.warning("No ADB devices found")
            return False
        except Exception as e:
            logger.error(f"ADB connection check failed: {e}")
            return False
            
    def get_installed_apps(self) -> List[Dict[str, str]]:
        try:
            # Get all packages and third-party packages in parallel for speed
            commands = [
                "shell pm list packages",
                "shell pm list packages -3"
            ]
            results = self._run_adb_commands_parallel(commands, log_errors=False)
            
            all_packages_result = None
            third_party_result = None
            
            for cmd_key, result in results.items():
                if "cmd_1" in cmd_key:  # Second command is "shell pm list packages -3"
                    third_party_result = result
                elif "cmd_0" in cmd_key:  # First command is "shell pm list packages"
                    all_packages_result = result
            
            if not all_packages_result:
                return []
                
            # Create set of third-party packages for fast lookup
            third_party_packages = set()
            if third_party_result:
                for line in third_party_result.strip().split('\n'):
                    if line.startswith('package:'):
                        package_name = line.replace('package:', '').strip()
                        third_party_packages.add(package_name)
                
            apps = []
            package_lines = all_packages_result.strip().split('\n')
            
            # 系统应用黑名单（过滤掉一些不需要监控的系统应用）
            system_blacklist = {
                'com.android.providers', 'com.android.server', 'com.android.systemui',
                'com.android.shell', 'com.android.bluetooth', 'com.android.nfc',
                'com.android.carrierconfig', 'com.android.cts', 'com.android.inputmethod',
                'com.android.keychain', 'com.android.location', 'com.android.externalstorage',
                'com.android.documentsui', 'com.android.onetimeinitializer', 'com.android.proxyhandler',
                'com.android.defcontainer', 'com.android.backupconfirm', 'com.android.sharedstoragebackup'
            }
            
            for line in package_lines:
                if line.startswith('package:'):
                    package_name = line.replace('package:', '').strip()
                    if package_name:
                        # 过滤掉黑名单中的系统应用
                        should_skip = False
                        for blacklist_pattern in system_blacklist:
                            if package_name.startswith(blacklist_pattern):
                                should_skip = True
                                break
                        
                        if should_skip:
                            continue
                            
                        # Use package name as display name for speed (avoid expensive pm dump calls)
                        # Try to make it more readable
                        display_name = self._make_readable_app_name(package_name)
                        
                        # 只添加有意义的应用（排除一些明显的系统内部组件）
                        if not package_name.endswith('.test') and not package_name.startswith('android.'):
                            apps.append({
                                'package_name': package_name,
                                'app_name': display_name,
                                'is_system': package_name not in third_party_packages
                            })
                        
            # 按应用名排序
            apps.sort(key=lambda x: x['app_name'].lower())
            logger.info(f"Found {len(apps)} installed apps")
            return apps
            
        except Exception as e:
            logger.error(f"Failed to get installed apps: {e}")
            return []
    
    def _make_readable_app_name(self, package_name: str) -> str:
        """Convert package name to more readable format without expensive ADB calls"""
        # Remove common prefixes
        if package_name.startswith('com.'):
            parts = package_name.split('.')
            if len(parts) > 2:
                # Use the last part as app name, with some cleanup
                app_name = parts[-1]
                # Handle cases like com.company.appname
                if len(parts) > 3:
                    app_name = parts[-1]
                else:
                    app_name = parts[1]  # company name
                
                # Capitalize and clean up
                app_name = app_name.replace('_', ' ').title()
                return app_name
        
        # For other packages, just use the package name
        return package_name
    
    def _is_third_party_app(self, package_name: str) -> bool:
        """判断是否是第三方应用"""
        try:
            result = self._run_adb_command(f"shell pm list packages -3 {package_name}")
            return result and package_name in result
        except:
            return False
            
    def get_system_performance(self) -> Dict[str, float]:
        """优化的系统性能数据获取 - 使用批量ADB命令和智能缓存"""
        current_time = time.time()
        
        # 检查缓存
        if (current_time - self._last_collection_time['system_performance'] < 
            self._collection_intervals['system_performance']):
            cached_data = self.enhanced_cache.get('system_performance')
            if cached_data:
                return cached_data
        
        # 使用批量数据获取方法
        try:
            batch_data = self._get_system_batch_data()
            if batch_data:
                # 缓存结果
                self.enhanced_cache.put('system_performance', batch_data, current_time)
                self._last_collection_time['system_performance'] = current_time
                return batch_data
        except Exception as e:
            logger.debug(f"Batch system performance failed, using fallback: {e}")
            
        # 回退到原有方法
        return self._get_system_performance_fallback()
        
    def _get_system_performance_fallback(self) -> Dict[str, float]:
        """系统性能数据获取回退方案"""
        current_time = time.time()
        data = {}
        
        try:
            # 获取基础系统数据
            cpu_usage = self._get_system_cpu_usage()
            if cpu_usage is not None:
                data['cpu_usage'] = cpu_usage
                
            memory_data = self._get_system_memory()
            data.update(memory_data)
            
            battery_level = self._get_battery_level()
            if battery_level is not None:
                data['battery_level'] = battery_level
                
            # 缓存结果
            self.enhanced_cache.put('system_performance', data, current_time)
            self._last_collection_time['system_performance'] = current_time
            
        except Exception as e:
            logger.debug(f"Fallback system performance collection failed: {e}")
            
        return data
        
    def get_device_info(self) -> Dict[str, str]:
        """获取设备信息"""
        device_info = {}
        
        try:
            # 获取设备属性
            props = [
                ('ro.product.model', 'model'),
                ('ro.product.brand', 'brand'), 
                ('ro.product.manufacturer', 'manufacturer'),
                ('ro.build.version.release', 'android_version'),
                ('ro.build.version.sdk', 'api_level'),
                ('ro.product.cpu.abi', 'cpu_abi'),
                ('ro.build.id', 'build_id')
            ]
            
            for prop, key in props:
                result = self._run_adb_command(f"shell getprop {prop}")
                if result:
                    device_info[key] = result.strip()
                    
            # 获取屏幕信息
            screen_info = self._run_adb_command("shell wm size")
            if screen_info and "Physical size:" in screen_info:
                screen_size = screen_info.split("Physical size:")[-1].strip()
                device_info['screen_size'] = screen_size
                
            # 获取密度信息  
            density_info = self._run_adb_command("shell wm density")
            if density_info and "Physical density:" in density_info:
                density = density_info.split("Physical density:")[-1].strip()
                device_info['screen_density'] = density
                
            logger.info(f"Device info collected: {device_info.get('model', 'Unknown')}")
            return device_info
            
        except Exception as e:
            logger.error(f"Failed to get device info: {e}")
            return {'error': str(e)}
        
    def get_app_performance(self, package_name: str) -> Dict[str, float]:
        """优化的应用性能数据获取"""
        data = {'app_package': package_name}
        current_time = time.time()
        
        # 检查缓存
        cache_key = f"app_performance_{package_name}"
        if (current_time - self._last_collection_time.get(cache_key, 0) < 
            self._collection_intervals['app_basic']):
            cached_data = self.enhanced_cache.get(cache_key)
            if cached_data:
                return cached_data
        
        # 批量执行应用性能命令
        batch_commands = [
            ("cpuinfo", "shell dumpsys cpuinfo"),
            ("meminfo", f"shell dumpsys meminfo {package_name}"),
            ("gfxinfo", f"shell dumpsys gfxinfo {package_name} framestats"),
            ("batterystats", f"shell dumpsys batterystats {package_name}"),
            ("top_app", f"shell top -n 1 -b | grep {package_name}")
        ]
        
        start_time = time.time()
        results = self.batch_executor.execute_batch(batch_commands, timeout=10)
        execution_time = time.time() - start_time
        
        # 记录性能统计
        self._performance_stats[f'app_collection_time_{package_name}'] = execution_time
        
        data.update(self._parse_app_performance_batch(results, package_name))
        
        # 缓存结果
        self.enhanced_cache.put(cache_key, data, current_time)
        self._last_collection_time[cache_key] = current_time
        
        return data
    
    def get_multiple_app_performance(self, package_names: List[str]) -> Dict[str, Dict[str, float]]:
        """批量获取多个应用的性能数据 - 新增优化方法"""
        if not package_names:
            return {}
            
        current_time = time.time()
        results = {}
        
        # 检查哪些应用需要更新数据
        apps_to_update = []
        for package_name in package_names:
            cache_key = f"app_performance_{package_name}"
            if (current_time - self._last_collection_time.get(cache_key, 0) >= 
                self._collection_intervals['app_basic']):
                apps_to_update.append(package_name)
            else:
                # 从缓存获取
                cached_data = self.enhanced_cache.get(cache_key)
                if cached_data:
                    results[package_name] = cached_data
        
        if not apps_to_update:
            return results
            
        # 第一步：获取所有应用的基础信息
        batch_commands_phase1 = [
            ("cpuinfo_all", "shell dumpsys cpuinfo"),
            ("top_all", "shell top -n 1 -b")
        ]
        
        phase1_results = self.batch_executor.execute_batch(batch_commands_phase1, timeout=10)
        all_cpu_info = phase1_results.get('cpuinfo_all', '')
        all_top_info = phase1_results.get('top_all', '')
        
        # 第二步：基于top输出获取实际进程名，然后构建第二批命令
        batch_commands_phase2 = []
        actual_process_names = {}
        
        for package_name in apps_to_update:
            # 从top输出中找到实际的进程名
            actual_process_name = self._get_actual_process_name_from_top(all_top_info, package_name)
            actual_process_names[package_name] = actual_process_name or package_name
            
            # 使用实际进程名构建命令
            batch_commands_phase2.extend([
                (f"meminfo_{package_name}", f"shell dumpsys meminfo {actual_process_names[package_name]}"),
                (f"gfxinfo_{package_name}", f"shell dumpsys gfxinfo {package_name} framestats"),
                (f"batterystats_{package_name}", f"shell dumpsys batterystats {package_name}")
            ])
        
        # 批量执行第二阶段命令
        start_time = time.time()
        batch_results = self.batch_executor.execute_batch(batch_commands_phase2, timeout=15)
        execution_time = time.time() - start_time
        
        # 记录性能统计
        self._performance_stats['multi_app_collection_time'] = execution_time
        
        # 解析结果
        for package_name in apps_to_update:
            app_data = {'app_package': package_name}
            
            # 解析各项数据
            if all_cpu_info:
                cpu_usage = self._parse_app_cpu_usage(all_cpu_info, package_name)
                if cpu_usage is not None:
                    app_data['cpu_usage'] = cpu_usage
            
            meminfo_result = batch_results.get(f"meminfo_{package_name}")
            if meminfo_result:
                memory_info = self._parse_app_memory_info(meminfo_result)
                app_data.update(memory_info)
            
            gfxinfo_result = batch_results.get(f"gfxinfo_{package_name}")
            if gfxinfo_result:
                fps = self._parse_app_fps(gfxinfo_result)
                if fps is not None:
                    app_data['fps'] = fps
            
            batterystats_result = batch_results.get(f"batterystats_{package_name}")
            if batterystats_result:
                power_info = self._parse_app_power_info(batterystats_result)
                app_data.update(power_info)
            
            # 解析top命令结果（使用第一阶段的结果）
            if all_top_info:
                top_data = self._parse_top_app(all_top_info, package_name)
                if top_data:
                    app_data.update(top_data)
            
            # 缓存结果
            cache_key = f"app_performance_{package_name}"
            self.enhanced_cache.put(cache_key, app_data, current_time)
            self._last_collection_time[cache_key] = current_time
            
            results[package_name] = app_data
        
        return results
    
    def _parse_app_performance_batch(self, results: Dict[str, str], package_name: str) -> Dict[str, float]:
        """批量解析应用性能数据"""
        data = {}
        
        try:
            # CPU使用率
            if results.get('cpuinfo'):
                cpu_usage = self._parse_app_cpu_usage(results['cpuinfo'], package_name)
                if cpu_usage is not None:
                    data['cpu_usage'] = cpu_usage
            
            # TOP命令解析（应用级别）
            if results.get('top_app'):
                top_data = self._parse_top_app(results['top_app'], package_name)
                if top_data:
                    data.update(top_data)
                    
            # 内存信息
            if results.get('meminfo'):
                memory_info = self._parse_app_memory_info(results['meminfo'])
                data.update(memory_info)
                
            # FPS信息
            if results.get('gfxinfo'):
                fps = self._parse_app_fps(results['gfxinfo'])
                if fps is not None:
                    data['fps'] = fps
                    
            # 功耗信息 - 使用增强的解析方法
            if results.get('batterystats'):
                power_info = self._parse_app_power_info_enhanced(results['batterystats'], package_name)
                data.update(power_info)
            else:
                # 如果没有batterystats结果，尝试估算功耗
                estimated_power = self._estimate_power_consumption(package_name)
                if estimated_power is not None:
                    data['power_consumption'] = estimated_power
                
        except Exception as e:
            logger.error(f"解析应用性能数据失败 {package_name}: {e}")
            
        return data
        
        # Process results based on command index
        app_cmd_index_map = {
            0: 'cpuinfo',        # "shell dumpsys cpuinfo"
            1: 'meminfo',        # "shell dumpsys meminfo {package_name}"
            2: 'gfxinfo',        # "shell dumpsys gfxinfo {package_name} framestats"
            3: 'batterystats'    # "shell dumpsys batterystats {package_name}"
        }
        
        for cmd_key, result in results.items():
            if result:
                try:
                    cmd_index = int(cmd_key.split('_')[1])
                    cmd_type = app_cmd_index_map.get(cmd_index)
                    
                    if cmd_type == 'cpuinfo':
                        cpu_usage = self._parse_app_cpu_usage(result, package_name)
                        if cpu_usage is not None:
                            data['cpu_usage'] = cpu_usage
                            
                    elif cmd_type == 'meminfo':
                        memory_info = self._parse_app_memory_info(result)
                        data.update(memory_info)
                        
                    elif cmd_type == 'gfxinfo':
                        fps = self._parse_app_fps(result)
                        if fps is not None:
                            data['fps'] = fps
                            
                    elif cmd_type == 'batterystats':
                        power_info = self._parse_app_power_info(result)
                        data.update(power_info)
                        
                except (IndexError, ValueError):
                    continue  # Skip malformed command keys
        
        # Network stats now handled asynchronously for better performance
        try:
            network_stats = self._get_app_network_stats(package_name)
            data.update(network_stats)
        except Exception as e:
            logger.debug(f"Network stats collection failed for {package_name}: {e}")
            # Don't fail the entire collection if network stats fail
        
        return data
        
    def _run_adb_command(self, command: str, shell: bool = False, log_errors: bool = True, use_cache: bool = False) -> Optional[str]:
        # Check cache first if enabled
        if use_cache:
            cache_key = f"{command}_{self.device_id}"
            cached_result = self._get_cached_result(cache_key)
            if cached_result is not None:
                return cached_result
        
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(command.split())
        
        for attempt in range(self.retry_count):
            try:
                result = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True, 
                    timeout=self.timeout,
                    check=True
                )
                output = result.stdout.strip()
                
                # Cache the result if caching is enabled
                if use_cache and output:
                    self._cache_result(cache_key, output)
                    
                return output
                
            except subprocess.TimeoutExpired:
                if log_errors and attempt == self.retry_count - 1:  # Only log on final attempt
                    logger.warning(f"ADB command timeout: {command}")
            except subprocess.CalledProcessError as e:
                if log_errors and attempt == self.retry_count - 1:  # Only log on final attempt
                    logger.debug(f"ADB command failed: {command}, Error: {e}")
            except Exception as e:
                if log_errors and attempt == self.retry_count - 1:  # Only log on final attempt
                    logger.debug(f"Unexpected error running ADB command: {e}")
                
            # Shorter sleep between retries for faster recovery
            if attempt < self.retry_count - 1:
                time.sleep(0.1)
                
        return None
    
    def _get_cached_result(self, cache_key: str) -> Optional[str]:
        """Get cached result if still valid"""
        if cache_key in self._cache:
            cached_data = self._cache[cache_key]
            if time.time() - cached_data['timestamp'] < self._cache_timeout:
                return cached_data['result']
            else:
                # Remove expired cache entry
                del self._cache[cache_key]
        return None
    
    def _cache_result(self, cache_key: str, result: str):
        """Cache a result with timestamp"""
        self._cache[cache_key] = {
            'result': result,
            'timestamp': time.time()
        }
    
    def _run_adb_commands_parallel(self, commands: List[str], log_errors: bool = True) -> Dict[str, Optional[str]]:
        """Run multiple ADB commands in parallel using threading with performance tracking"""
        results = {}
        threads = []
        result_queue = queue.Queue()
        start_time = time.time()
        
        def run_command(cmd, cmd_key):
            cmd_start = time.time()
            result = self._run_adb_command(cmd, log_errors=log_errors)
            cmd_time = time.time() - cmd_start
            
            # Track command performance
            self._command_times[cmd_key] = cmd_time
            if cmd_time > self.timeout * 2:  # Mark as slow if takes >2x expected time
                self._slow_commands.add(cmd.split()[0])
                logger.debug(f"Slow command detected: {cmd} took {cmd_time:.1f}s")
            
            result_queue.put((cmd_key, result, cmd_time))
        
        # Start threads for each command
        for i, command in enumerate(commands):
            cmd_key = f"cmd_{i}_{command.split()[0]}"  # Create unique key
            thread = threading.Thread(target=run_command, args=(command, cmd_key))
            thread.daemon = True
            threads.append(thread)
            thread.start()
        
        # Collect results with improved timeout handling
        completed_threads = 0
        for thread in threads:
            # Use a reasonable timeout per thread
            timeout_per_thread = min(self.timeout + 2, 8)  # Max 8 seconds per thread
            thread.join(timeout=timeout_per_thread)
            if thread.is_alive():
                logger.warning(f"Thread still running after {timeout_per_thread}s timeout")
            else:
                completed_threads += 1
        
        # Get all results from queue with timeout
        collected_results = 0
        queue_timeout = time.time() + 2  # 2 seconds to collect results
        while not result_queue.empty() and time.time() < queue_timeout:
            try:
                cmd_key, result, cmd_time = result_queue.get(timeout=0.1)
                results[cmd_key] = result
                collected_results += 1
            except queue.Empty:
                break
        
        total_time = time.time() - start_time
        logger.debug(f"Parallel execution: {completed_threads}/{len(threads)} threads completed, "
                    f"{collected_results} results collected in {total_time:.1f}s")
        
        return results
        
    def _parse_devices(self, devices_output: str) -> List[str]:
        devices = []
        lines = devices_output.strip().split('\n')[1:]  # Skip header
        for line in lines:
            if '\tdevice' in line:
                device_id = line.split('\t')[0]
                devices.append(device_id)
        return devices
        
    def _get_app_name(self, package_name: str) -> Optional[str]:
        try:
            result = self._run_adb_command(f"shell pm dump {package_name}")
            if result:
                # Look for application label
                match = re.search(r'applicationLabel=(.+)', result)
                if match:
                    return match.group(1).strip()
        except Exception:
            pass
        return None
        
    def _get_system_batch_data(self) -> Dict[str, Any]:
        """批量获取系统数据 - 性能优化，包含网络流量"""
        try:
            # 分别获取各项数据（避免复杂批量命令问题）
            cpu_data = {}
            memory_data = {}
            battery_data = {}
            network_data = {}
            
            # 获取CPU数据（包含详细分解）
            cpu_breakdown = self.get_cpu_usage_with_breakdown()
            if cpu_breakdown:
                # 保持向后兼容性，同时添加详细信息
                cpu_data = {'cpu_usage': cpu_breakdown.get('total', 0)}
                if 'user' in cpu_breakdown:
                    cpu_data['cpu_user'] = cpu_breakdown['user']
                    cpu_data['cpu_breakdown'] = cpu_breakdown
            
            # 获取内存数据
            memory_result = self._run_adb_command("shell cat /proc/meminfo", use_cache=False)
            if memory_result:
                memory_data = self._parse_memory_data(memory_result)
            
            # 获取电池数据
            battery_result = self._run_adb_command("shell dumpsys battery", use_cache=True)
            if battery_result:
                battery_data = self._parse_battery_data(battery_result)
            
            # 获取网络数据，使用多种方法尝试
            network_data = self._get_network_data_with_fallback()
            
            # 获取CPU温度
            cpu_temp = self._get_cpu_temperature()
            temp_data = {}
            if cpu_temp is not None:
                temp_data['cpu_temperature'] = cpu_temp
            
            # 获取系统负载
            load_result = self._run_adb_command("shell cat /proc/loadavg", use_cache=True)
            load_data = {}
            if load_result:
                load_data = self._parse_load_data(load_result)
            
            # 合并所有数据
            system_data = {}
            system_data.update(cpu_data)
            system_data.update(memory_data)
            system_data.update(battery_data)
            system_data.update(network_data)
            system_data.update(temp_data)
            system_data.update(load_data)
            
            return system_data if system_data else self._get_system_data_fallback()
            
        except Exception as e:
            logger.debug(f"Batch system data collection failed: {e}")
            return self._get_system_data_fallback()
    
    def _parse_cpu_data(self, cpu_output: str) -> Dict[str, float]:
        """解析CPU数据"""
        try:
            lines = cpu_output.strip().split('\n')
            cpu_line = lines[0]  # First line is total CPU
            values = cpu_line.split()[1:]
            values = [int(v) for v in values]
            
            total = sum(values)
            idle = values[3]  # idle time
            usage = ((total - idle) / total) * 100
            return {'cpu_usage': round(usage, 2)}
        except Exception:
            return {}
    
    def _parse_memory_data(self, memory_output: str) -> Dict[str, float]:
        """解析内存数据"""
        try:
            memory_info = {}
            total_kb = None
            available_kb = None
            
            for line in memory_output.strip().split('\n'):
                if 'MemTotal:' in line:
                    total_kb = int(re.findall(r'\d+', line)[0])
                    memory_info['memory_system_total'] = round(total_kb / 1024, 2)
                elif 'MemAvailable:' in line:
                    available_kb = int(re.findall(r'\d+', line)[0])
                    memory_info['memory_system_available'] = round(available_kb / 1024, 2)
            
            # 计算内存使用百分比
            if total_kb is not None and available_kb is not None:
                used_kb = total_kb - available_kb
                usage_percent = (used_kb / total_kb) * 100
                memory_info['memory_usage_percent'] = round(usage_percent, 2)
                memory_info['memory_percent'] = round(usage_percent, 2)  # 保持兼容性
                memory_info['memory_system_used'] = round(used_kb / 1024, 2)
                
            return memory_info
        except Exception:
            return {}
    
    def _parse_battery_data(self, battery_output: str) -> Dict[str, float]:
        """解析电池数据"""
        try:
            for line in battery_output.strip().split('\n'):
                if 'level:' in line.lower():
                    level = float(re.findall(r'\d+', line)[0])
                    return {'battery_level': level}
        except Exception:
            pass
        return {}
    
    def _get_default_network_data(self) -> Dict[str, float]:
        """Return default network data when parsing fails"""
        return {
            'network_rx_total': 0.0,
            'network_tx_total': 0.0,
            'network': 0.0,
            'network_rx': 0.0,
            'network_tx': 0.0
        }
    
    def _get_network_data_with_fallback(self) -> Dict[str, float]:
        """Get network data with multiple fallback methods"""
        # Method 1: Try /proc/net/dev (preferred)
        try:
            network_result = self._run_adb_command("shell cat /proc/net/dev", use_cache=True)
            if network_result and network_result.strip():
                network_data = self._parse_network_data(network_result)
                if network_data and any(v > 0 for k, v in network_data.items() if 'total' in k):
                    logger.debug("Network data successfully obtained from /proc/net/dev")
                    return network_data
        except Exception as e:
            logger.debug(f"Failed to get network data from /proc/net/dev: {e}")
        
        # Method 2: Try alternative network statistics
        try:
            netstats_result = self._run_adb_command("shell dumpsys netstats", use_cache=True)
            if netstats_result:
                network_data = self._parse_netstats_data(netstats_result)
                if network_data:
                    logger.debug("Network data obtained from dumpsys netstats")
                    return network_data
        except Exception as e:
            logger.debug(f"Failed to get network data from dumpsys netstats: {e}")
        
        # Method 3: Try /proc/net/netstat
        try:
            netstat_result = self._run_adb_command("shell cat /proc/net/netstat", use_cache=True)
            if netstat_result:
                # This method doesn't provide total bytes but can indicate network activity
                logger.debug("Network activity detected from /proc/net/netstat")
        except Exception as e:
            logger.debug(f"Failed to get network data from /proc/net/netstat: {e}")
        
        logger.debug("All network data collection methods failed, returning default data")
        return self._get_default_network_data()
    
    def _parse_netstats_data(self, netstats_output: str) -> Dict[str, float]:
        """Parse network data from dumpsys netstats"""
        try:
            # Simple parsing of netstats - look for total bytes
            import re
            rx_matches = re.findall(r'rx.*?(\d+)\s*bytes', netstats_output, re.IGNORECASE)
            tx_matches = re.findall(r'tx.*?(\d+)\s*bytes', netstats_output, re.IGNORECASE)
            
            if rx_matches or tx_matches:
                total_rx = sum(int(x) for x in rx_matches)
                total_tx = sum(int(x) for x in tx_matches)
                
                current_time = time.time()
                rx_kb = total_rx / 1024
                tx_kb = total_tx / 1024
                
                network_data = {
                    'network_rx_total': round(rx_kb, 2),
                    'network_tx_total': round(tx_kb, 2)
                }
                
                # Calculate speeds
                if hasattr(self, '_last_system_network'):
                    time_diff = current_time - self._last_system_network['time']
                    if time_diff > 0:
                        rx_speed = (rx_kb - self._last_system_network['rx']) / time_diff
                        tx_speed = (tx_kb - self._last_system_network['tx']) / time_diff
                        network_data['network_rx'] = round(max(0, rx_speed), 2)
                        network_data['network_tx'] = round(max(0, tx_speed), 2)
                        network_data['network'] = round(max(0, rx_speed + tx_speed), 2)
                else:
                    network_data['network'] = 0.0
                    network_data['network_rx'] = 0.0
                    network_data['network_tx'] = 0.0
                
                # Store for next calculation
                self._last_system_network = {
                    'time': current_time,
                    'rx': rx_kb,
                    'tx': tx_kb
                }
                
                return network_data
        except Exception as e:
            logger.debug(f"Failed to parse netstats data: {e}")
        return {}
    
    def _parse_network_data(self, network_output: str) -> Dict[str, float]:
        """解析网络数据"""
        try:
            if not network_output or not network_output.strip():
                logger.debug("Empty network output")
                return self._get_default_network_data()
                
            lines = network_output.strip().split('\n')
            logger.debug(f"Network output lines: {len(lines)}")
            
            if len(lines) < 3:  # Need header + at least one interface
                logger.debug("Insufficient network data lines")
                return self._get_default_network_data()
                
            # Skip first 2 lines (headers)
            data_lines = lines[2:]
            total_rx = total_tx = 0
            interface_count = 0
            
            for line in data_lines:
                if ':' in line and line.strip():
                    try:
                        # Split by ':' to separate interface name and stats
                        parts = line.split(':')
                        if len(parts) < 2:
                            continue
                        
                        interface_name = parts[0].strip()
                        # Skip loopback interface
                        if interface_name == 'lo':
                            continue
                            
                        # Parse stats (columns: rx_bytes, rx_packets, ..., tx_bytes, tx_packets, ...)
                        stats = parts[1].split()
                        if len(stats) >= 9:
                            rx_bytes = int(stats[0])
                            tx_bytes = int(stats[8])
                            total_rx += rx_bytes
                            total_tx += tx_bytes
                            interface_count += 1
                            logger.debug(f"Interface {interface_name}: rx={rx_bytes}, tx={tx_bytes}")
                    except (ValueError, IndexError) as e:
                        logger.debug(f"Failed to parse network line: {line}, error: {e}")
                        continue
            
            logger.debug(f"Total interfaces processed: {interface_count}, total_rx: {total_rx}, total_tx: {total_tx}")
            
            # Convert to KB and calculate rates
            current_time = time.time()
            rx_kb = total_rx / 1024
            tx_kb = total_tx / 1024
            
            network_data = {
                'network_rx_total': round(rx_kb, 2),
                'network_tx_total': round(tx_kb, 2)
            }
            
            # Calculate network speed if we have previous data
            if hasattr(self, '_last_system_network'):
                time_diff = current_time - self._last_system_network['time']
                if time_diff > 0:
                    rx_speed = (rx_kb - self._last_system_network['rx']) / time_diff
                    tx_speed = (tx_kb - self._last_system_network['tx']) / time_diff
                    # Calculate individual speeds
                    network_data['network_rx'] = round(max(0, rx_speed), 2)
                    network_data['network_tx'] = round(max(0, tx_speed), 2)
                    # Use total network speed (rx + tx) for main display
                    total_speed = max(0, rx_speed + tx_speed)
                    network_data['network'] = round(total_speed, 2)
            else:
                # First time - provide default values
                network_data['network'] = 0.0
                network_data['network_rx'] = 0.0
                network_data['network_tx'] = 0.0
            
            # Store for next calculation
            self._last_system_network = {
                'time': current_time,
                'rx': rx_kb,
                'tx': tx_kb
            }
            
            return network_data
            
        except Exception as e:
            logger.debug(f"Failed to parse network data: {e}")
            return self._get_default_network_data()
    
    def _parse_load_data(self, load_output: str) -> Dict[str, float]:
        """解析系统负载数据"""
        try:
            parts = load_output.strip().split()
            if len(parts) >= 3:
                return {
                    'load_1min': round(float(parts[0]), 2),
                    'load_5min': round(float(parts[1]), 2),
                    'load_15min': round(float(parts[2]), 2)
                }
        except (ValueError, IndexError) as e:
            logger.debug(f"Failed to parse load data: {e}")
            pass
        return {}
    
    def _get_system_data_fallback(self) -> Dict[str, Any]:
        """系统数据获取回退方案"""
        data = {}
        
        # 分别获取各项数据（原有方式）
        cpu_usage = self._get_system_cpu_usage()
        if cpu_usage is not None:
            data['cpu_usage'] = cpu_usage
            
        memory_data = self._get_system_memory()
        data.update(memory_data)
        
        battery_level = self._get_battery_level()
        if battery_level is not None:
            data['battery_level'] = battery_level
            
        # 获取网络数据
        network_data = self._get_system_network_stats()
        data.update(network_data)
        
        # 获取CPU温度
        cpu_temp = self._get_cpu_temperature()
        if cpu_temp is not None:
            data['cpu_temperature'] = cpu_temp
        
        # 获取系统负载
        load_result = self._run_adb_command("shell cat /proc/loadavg")
        if load_result:
            load_data = self._parse_load_data(load_result)
            data.update(load_data)
            
        return data

    def _get_system_cpu_usage(self) -> Optional[float]:
        try:
            # First try to get detailed CPU info from dumpsys cpuinfo
            result = self._run_adb_command("shell dumpsys cpuinfo")
            if result:
                total_cpu = self._parse_dumpsys_cpuinfo_total(result)
                if total_cpu is not None:
                    return total_cpu
            
            # Fallback to /proc/stat
            result = self._run_adb_command("shell cat /proc/stat")
            if result:
                lines = result.split('\n')
                cpu_line = lines[0]  # First line is total CPU
                values = cpu_line.split()[1:]
                values = [int(v) for v in values]
                
                total = sum(values)
                idle = values[3]  # idle time
                usage = ((total - idle) / total) * 100
                return round(usage, 2)
        except Exception as e:
            logger.debug(f"Failed to get system CPU usage: {e}")
        return None
    
    def _parse_dumpsys_cpuinfo_total(self, cpuinfo_output: str) -> Optional[float]:
        """Parse total CPU usage from dumpsys cpuinfo output
        Example: 87% TOTAL: 54% user + 29% kernel + 0% iowait + 3.1% irq + 0.8% softirq
        """
        try:
            lines = cpuinfo_output.split('\n')
            for line in lines:
                if 'TOTAL:' in line and '%' in line:
                    # Extract the total percentage before 'TOTAL:'
                    parts = line.split('TOTAL:')
                    if len(parts) >= 1:
                        total_part = parts[0].strip()
                        # Look for percentage pattern
                        import re
                        match = re.search(r'(\d+(?:\.\d+)?)%', total_part)
                        if match:
                            return float(match.group(1))
        except Exception as e:
            logger.debug(f"Failed to parse dumpsys cpuinfo: {e}")
        return None
    
    def get_cpu_usage_with_breakdown(self) -> Dict[str, float]:
        """Get CPU usage with detailed breakdown from dumpsys cpuinfo
        Returns: {'total': 87.0, 'user': 54.0, 'kernel': 29.0, 'iowait': 0.0, 'irq': 3.1, 'softirq': 0.8}
        """
        try:
            result = self._run_adb_command("shell dumpsys cpuinfo")
            if result:
                lines = result.split('\n')
                for line in lines:
                    if 'TOTAL:' in line and '%' in line:
                        # Parse line like: 87% TOTAL: 54% user + 29% kernel + 0% iowait + 3.1% irq + 0.8% softirq
                        import re
                        
                        # Extract total
                        total_match = re.search(r'(\d+(?:\.\d+)?)%\s*TOTAL:', line)
                        if not total_match:
                            continue
                            
                        total = float(total_match.group(1))
                        
                        # Extract breakdown components
                        breakdown = {'total': total}
                        
                        # Find user, kernel, iowait, irq, softirq values
                        components = ['user', 'kernel', 'iowait', 'irq', 'softirq']
                        for component in components:
                            pattern = rf'(\d+(?:\.\d+)?)%\s*{component}'
                            match = re.search(pattern, line)
                            if match:
                                breakdown[component] = float(match.group(1))
                        
                        return breakdown
        except Exception as e:
            logger.debug(f"Failed to get CPU breakdown: {e}")
        
        # Fallback to basic CPU usage
        cpu_usage = self._get_system_cpu_usage()
        if cpu_usage is not None:
            return {'total': cpu_usage}
        return {}
        
    def _get_system_memory(self) -> Dict[str, float]:
        try:
            result = self._run_adb_command("shell cat /proc/meminfo")
            if result:
                memory_info = {}
                for line in result.split('\n'):
                    if 'MemTotal:' in line:
                        total_kb = int(re.findall(r'\d+', line)[0])
                        memory_info['memory_system_total'] = round(total_kb / 1024, 2)
                    elif 'MemAvailable:' in line:
                        available_kb = int(re.findall(r'\d+', line)[0])
                        memory_info['memory_system_available'] = round(available_kb / 1024, 2)
                return memory_info
        except Exception as e:
            logger.debug(f"Failed to get system memory: {e}")
        return {}
        
    def _get_battery_level(self) -> Optional[float]:
        try:
            result = self._run_adb_command("shell dumpsys battery")
            if result:
                match = re.search(r'level: (\d+)', result)
                if match:
                    return float(match.group(1))
        except Exception as e:
            logger.debug(f"Failed to get battery level: {e}")
        return None
        
    def _get_system_network_stats(self) -> Dict[str, float]:
        try:
            result = self._run_adb_command("shell cat /proc/net/dev")
            if result:
                lines = result.split('\n')[2:]  # Skip headers
                total_rx = total_tx = 0
                
                for line in lines:
                    if ':' in line:
                        parts = line.split(':')[1].split()
                        rx_bytes = int(parts[0])
                        tx_bytes = int(parts[8])
                        total_rx += rx_bytes
                        total_tx += tx_bytes
                
                # Convert to KB
                current_time = time.time()
                rx_kb = total_rx / 1024
                tx_kb = total_tx / 1024
                
                # Calculate speed if we have previous data
                network_data = {
                    'network_rx_total': round(rx_kb, 2),
                    'network_tx_total': round(tx_kb, 2)
                }
                
                if hasattr(self, '_last_system_network'):
                    time_diff = current_time - self._last_system_network['time']
                    if time_diff > 0:
                        rx_speed = (rx_kb - self._last_system_network['rx']) / time_diff
                        tx_speed = (tx_kb - self._last_system_network['tx']) / time_diff
                        network_data['network_rx'] = round(max(0, rx_speed), 2)
                        network_data['network_tx'] = round(max(0, tx_speed), 2)
                
                self._last_system_network = {
                    'time': current_time,
                    'rx': rx_kb,
                    'tx': tx_kb
                }
                
                return network_data
        except Exception as e:
            logger.debug(f"Failed to get system network stats: {e}")
        return {}
        
    def _get_app_cpu_usage(self, package_name: str) -> Optional[float]:
        try:
            # First get full cpuinfo, then search for package
            result = self._run_adb_command("shell dumpsys cpuinfo")
            if result and package_name in result:
                # Find lines containing the package name
                lines = result.split('\n')
                for line in lines:
                    if package_name in line and '%' in line:
                        # Parse CPU usage from the line
                        match = re.search(r'(\d+(?:\.\d+)?)%', line)
                        if match:
                            return float(match.group(1))
        except Exception as e:
            logger.debug(f"Failed to get app CPU usage for {package_name}: {e}")
        return None
        
    def _get_app_memory(self, package_name: str) -> Dict[str, float]:
        try:
            result = self._run_adb_command(f"shell dumpsys meminfo {package_name}")
            if result:
                memory_info = {}
                
                # Parse PSS memory
                pss_match = re.search(r'TOTAL\s+(\d+)', result)
                if pss_match:
                    memory_info['memory_pss'] = round(int(pss_match.group(1)) / 1024, 2)
                
                # Parse Java heap
                java_match = re.search(r'Java Heap:\s+(\d+)', result)
                if java_match:
                    memory_info['memory_java'] = round(int(java_match.group(1)) / 1024, 2)
                
                # Parse Native heap
                native_match = re.search(r'Native Heap:\s+(\d+)', result)
                if native_match:
                    memory_info['memory_native'] = round(int(native_match.group(1)) / 1024, 2)
                
                return memory_info
        except Exception as e:
            logger.debug(f"Failed to get app memory for {package_name}: {e}")
        return {}
        
    def _get_app_network_stats(self, package_name: str) -> Dict[str, float]:
        """Get app network statistics with caching and optimized fallback methods"""
        # Check cache first
        cache_key = f"network_{package_name}"
        cached_result = self._get_cached_result(cache_key)
        if cached_result is not None:
            try:
                return eval(cached_result)  # Convert string back to dict
            except:
                pass
        
        network_data = {}
        
        # Get UID first with caching (most expensive operation)
        uid = self._get_cached_uid(package_name)
        if uid is None:
            logger.debug(f"Could not get UID for {package_name}")
            return {}
        
        # Try methods in order of efficiency
        methods = [
            ('traffic_stats', self._get_network_via_traffic_stats_optimized),
            ('netstats', self._get_network_via_netstats_optimized),
            ('qtaguid', self._get_network_via_qtaguid_optimized)
        ]
        
        for method_name, method_func in methods:
            if method_name in self._slow_commands:
                continue  # Skip known slow methods
                
            try:
                network_data = method_func(package_name, uid)
                if network_data:
                    # Cache successful result
                    self._cache_result(cache_key, str(network_data))
                    logger.debug(f"Network stats via {method_name} for {package_name}")
                    return network_data
            except Exception as e:
                logger.debug(f"Network method {method_name} failed for {package_name}: {e}")
                continue
        
        logger.debug(f"All network stat methods failed for {package_name}")
        return {}
    
    def _get_cached_uid(self, package_name: str) -> Optional[str]:
        """Get UID for package with caching"""
        if package_name in self._uid_cache:
            cached_data = self._uid_cache[package_name]
            if time.time() - cached_data['timestamp'] < 30:  # Cache UIDs for 30 seconds
                return cached_data['uid']
        
        try:
            # Use faster pm command instead of full dumpsys
            result = self._run_adb_command(f"shell pm list packages -U {package_name}")
            if result:
                # Format: package:com.example.app uid:10123
                uid_match = re.search(r'uid:(\d+)', result)
                if uid_match:
                    uid = uid_match.group(1)
                    self._uid_cache[package_name] = {
                        'uid': uid,
                        'timestamp': time.time()
                    }
                    return uid
            
            # Fallback to compiled pattern
            result = self._run_adb_command(f"shell dumpsys package {package_name}")
            if result:
                uid_match = self._compiled_patterns['uid_lookup'].search(result)
                if uid_match:
                    uid = uid_match.group(1)
                    self._uid_cache[package_name] = {
                        'uid': uid,
                        'timestamp': time.time()
                    }
                    return uid
                    
        except Exception as e:
            logger.debug(f"Failed to get UID for {package_name}: {e}")
        
        return None
    
    def _get_network_via_traffic_stats_optimized(self, package_name: str, uid: str) -> Dict[str, float]:
        """Optimized traffic stats collection"""
        try:
            # Use targeted netstats query
            result = self._run_adb_command(f"shell dumpsys netstats detail uid {uid}")
            if not result:
                return {}
            
            # Parse with compiled patterns for better performance
            pattern = rf'uid={uid}.*?rb=(\d+).*?tb=(\d+)'
            matches = re.findall(pattern, result, re.DOTALL)
            
            if matches:
                total_rx = total_tx = 0
                for match in matches:
                    total_rx += int(match[0])
                    total_tx += int(match[1])
                
                current_time = time.time()
                rx_kb = total_rx / 1024
                tx_kb = total_tx / 1024
                
                # Calculate rates if we have previous data
                if package_name in self._last_network_stats:
                    last_data = self._last_network_stats[package_name]
                    time_diff = current_time - last_data['timestamp']
                    
                    if time_diff > 0:
                        rx_rate = max(0, (rx_kb - last_data['rx_kb']) / time_diff)
                        tx_rate = max(0, (tx_kb - last_data['tx_kb']) / time_diff)
                    else:
                        rx_rate = tx_rate = 0
                else:
                    rx_rate = tx_rate = 0
                
                # Store current stats for next calculation
                self._last_network_stats[package_name] = {
                    'rx_kb': rx_kb,
                    'tx_kb': tx_kb,
                    'timestamp': current_time
                }
                
                return {
                    'network_rx_kb': rx_kb,
                    'network_tx_kb': tx_kb,
                    'network_rx_rate': round(rx_rate, 2),
                    'network_tx_rate': round(tx_rate, 2)
                }
                
        except Exception as e:
            logger.debug(f"Traffic stats method failed for {package_name}: {e}")
        
        return {}
    
    def _get_network_via_netstats_optimized(self, package_name: str, uid: str) -> Dict[str, float]:
        """Optimized netstats collection"""
        try:
            # Use more targeted command
            result = self._run_adb_command(f"shell cat /proc/net/xt_qtaguid/stats | grep {uid}")
            if not result:
                return {}
            
            lines = result.strip().split('\n')
            total_rx = total_tx = 0
            
            for line in lines:
                parts = line.split()
                if len(parts) >= 8 and parts[3] == uid:
                    total_rx += int(parts[5])
                    total_tx += int(parts[7])
            
            if total_rx > 0 or total_tx > 0:
                return {
                    'network_rx_kb': round(total_rx / 1024, 2),
                    'network_tx_kb': round(total_tx / 1024, 2),
                    'network_rx_rate': 0,  # Rate calculation would need history
                    'network_tx_rate': 0
                }
                
        except Exception as e:
            logger.debug(f"Netstats method failed for {package_name}: {e}")
        
        return {}
    
    def _get_network_via_qtaguid_optimized(self, package_name: str, uid: str) -> Dict[str, float]:
        """Optimized qtaguid collection"""
        # This method is often slow and requires root, so make it very simple
        return {}
        
    def _get_network_via_traffic_stats(self, package_name: str) -> Dict[str, float]:
        try:
            # Get app UID first
            uid_result = self._run_adb_command(f"shell dumpsys package {package_name}")
            if not uid_result:
                return {}
                
            uid_match = re.search(r'userId=(\d+)', uid_result)
            if not uid_match:
                return {}
                
            uid = uid_match.group(1)
            
            # Use dumpsys netstats
            result = self._run_adb_command(f"shell dumpsys netstats detail")
            if result and uid in result:
                # Parse network usage from netstats
                pattern = rf'uid={uid}.*?rb=(\d+).*?tb=(\d+)'
                matches = re.findall(pattern, result, re.DOTALL)
                
                if matches:
                    total_rx = total_tx = 0
                    for match in matches:
                        total_rx += int(match[0])
                        total_tx += int(match[1])
                    
                    current_time = time.time()
                    rx_kb = total_rx / 1024
                    tx_kb = total_tx / 1024
                    
                    network_data = {
                        'network_rx_total': round(rx_kb, 2),
                        'network_tx_total': round(tx_kb, 2)
                    }
                    
                    # Calculate speed
                    key = f"{package_name}_traffic"
                    if key in self._last_network_stats:
                        time_diff = current_time - self._last_network_stats[key]['time']
                        if time_diff > 0:
                            rx_speed = (rx_kb - self._last_network_stats[key]['rx']) / time_diff
                            tx_speed = (tx_kb - self._last_network_stats[key]['tx']) / time_diff
                            network_data['network_rx'] = round(max(0, rx_speed), 2)
                            network_data['network_tx'] = round(max(0, tx_speed), 2)
                    
                    self._last_network_stats[key] = {
                        'time': current_time,
                        'rx': rx_kb,
                        'tx': tx_kb
                    }
                    
                    return network_data
                    
        except Exception as e:
            logger.debug(f"Traffic stats method failed for {package_name}: {e}")
        return {}
        
    def _get_network_via_netstats(self, package_name: str) -> Dict[str, float]:
        try:
            # Try using package manager to get network usage
            result = self._run_adb_command(f"shell dumpsys package {package_name}")
            if result:
                # Look for network usage in package dump
                rx_match = re.search(r'networkLocationRequests.*?(\d+)', result)
                tx_match = re.search(r'dataActivity.*?(\d+)', result)
                
                if rx_match or tx_match:
                    rx_bytes = int(rx_match.group(1)) if rx_match else 0
                    tx_bytes = int(tx_match.group(1)) if tx_match else 0
                    
                    return {
                        'network_rx_total': round(rx_bytes / 1024, 2),
                        'network_tx_total': round(tx_bytes / 1024, 2)
                    }
                    
        except Exception as e:
            logger.debug(f"Netstats method failed for {package_name}: {e}")
        return {}
        
    def _get_network_via_qtaguid(self, package_name: str) -> Dict[str, float]:
        try:
            # Get app UID first
            uid_result = self._run_adb_command(f"shell dumpsys package {package_name}")
            if not uid_result:
                return {}
                
            uid_match = re.search(r'userId=(\d+)', uid_result)
            if not uid_match:
                return {}
                
            uid = uid_match.group(1)
            
            # Try to read xt_qtaguid stats (may not exist on newer Android versions)
            result = self._run_adb_command("shell cat /proc/net/xt_qtaguid/stats", log_errors=False)
            if result and uid in result:
                total_rx = total_tx = 0
                for line in result.split('\n'):
                    if line.strip() and uid in line:
                        parts = line.split()
                        if len(parts) >= 8:
                            try:
                                rx_bytes = int(parts[5])
                                tx_bytes = int(parts[7])
                                total_rx += rx_bytes
                                total_tx += tx_bytes
                            except (ValueError, IndexError):
                                continue
                
                current_time = time.time()
                rx_kb = total_rx / 1024
                tx_kb = total_tx / 1024
                
                network_data = {
                    'network_rx_total': round(rx_kb, 2),
                    'network_tx_total': round(tx_kb, 2)
                }
                
                # Calculate speed
                key = f"{package_name}_qtaguid"
                if key in self._last_network_stats:
                    time_diff = current_time - self._last_network_stats[key]['time']
                    if time_diff > 0:
                        rx_speed = (rx_kb - self._last_network_stats[key]['rx']) / time_diff
                        tx_speed = (tx_kb - self._last_network_stats[key]['tx']) / time_diff
                        network_data['network_rx'] = round(max(0, rx_speed), 2)
                        network_data['network_tx'] = round(max(0, tx_speed), 2)
                
                self._last_network_stats[key] = {
                    'time': current_time,
                    'rx': rx_kb,
                    'tx': tx_kb
                }
                
                return network_data
                
        except Exception as e:
            logger.debug(f"QTagUID method failed for {package_name}: {e}")
        
        # xt_qtaguid is not available on newer Android versions or requires root
        logger.debug(f"xt_qtaguid stats not available for {package_name} (normal on Android 7+ or non-root devices)")
        return {}
        
    def _get_app_fps(self, package_name: str) -> Optional[float]:
        # Try multiple methods for FPS detection
        
        # Method 1: Try gfxinfo (most accurate for app FPS)
        fps = self._get_fps_via_gfxinfo(package_name)
        if fps is not None:
            return fps
            
        # Method 2: Try SurfaceFlinger latency
        fps = self._get_fps_via_surfaceflinger(package_name)
        if fps is not None:
            return fps
            
        # Method 3: Try dumpsys window
        fps = self._get_fps_via_window_dump(package_name)
        if fps is not None:
            return fps
            
        logger.debug(f"All FPS detection methods failed for {package_name}")
        return None
        
    def _get_fps_via_gfxinfo(self, package_name: str) -> Optional[float]:
        try:
            # Use gfxinfo to get frame statistics
            result = self._run_adb_command(f"shell dumpsys gfxinfo {package_name} framestats")
            if result:
                lines = result.split('\n')
                frame_times = []
                
                for line in lines:
                    if line.strip() and not line.startswith('---'):
                        parts = line.split(',')
                        if len(parts) >= 2:
                            try:
                                # Parse frame time (usually in column 1 or 2)
                                frame_start = int(parts[1])
                                frame_end = int(parts[2]) if len(parts) > 2 else frame_start
                                frame_duration = frame_end - frame_start
                                
                                if frame_duration > 0:
                                    frame_times.append(frame_duration)
                            except (ValueError, IndexError):
                                continue
                
                if len(frame_times) > 10:  # Need enough samples
                    # Calculate average frame time
                    avg_frame_time = sum(frame_times) / len(frame_times)
                    # Convert nanoseconds to FPS
                    fps = 1000000000 / avg_frame_time
                    return round(min(fps, 120), 2)  # Cap at 120 FPS
                    
        except Exception as e:
            logger.debug(f"GFXInfo FPS method failed for {package_name}: {e}")
        return None
        
    def _get_fps_via_surfaceflinger(self, package_name: str) -> Optional[float]:
        try:
            # Check if app is in foreground first
            window_result = self._run_adb_command("shell dumpsys window windows")
            if not (window_result and package_name in window_result):
                return None
                
            # Get current focused window surface
            surface_match = re.search(rf'{re.escape(package_name)}.*?Surface\(name=([^)]+)\)', window_result)
            if not surface_match:
                return None
                
            surface_name = surface_match.group(1)
            
            # Get FPS using surfaceflinger latency for this surface
            fps_result = self._run_adb_command(f"shell dumpsys SurfaceFlinger --latency '{surface_name}'")
            if fps_result:
                lines = fps_result.split('\n')[1:]  # Skip header
                valid_frames = []
                
                for line in lines:
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 3:
                            try:
                                frame_ready = int(parts[1])
                                frame_displayed = int(parts[2])
                                if frame_ready > 0 and frame_displayed > 0:
                                    valid_frames.append((frame_ready, frame_displayed))
                            except ValueError:
                                continue
                
                if len(valid_frames) > 5:
                    # Calculate frame intervals
                    intervals = []
                    for i in range(1, len(valid_frames)):
                        interval = valid_frames[i][0] - valid_frames[i-1][0]
                        if interval > 0:
                            intervals.append(interval)
                    
                    if intervals:
                        avg_interval = sum(intervals) / len(intervals)
                        fps = 1000000000 / avg_interval  # Convert from nanoseconds
                        return round(min(fps, 120), 2)
                        
        except Exception as e:
            logger.debug(f"SurfaceFlinger FPS method failed for {package_name}: {e}")
        return None
        
    def _get_fps_via_window_dump(self, package_name: str) -> Optional[float]:
        try:
            # Use window manager to check app activity
            result = self._run_adb_command("shell dumpsys window windows")
            if result and package_name in result:
                # Look for refresh rate information
                refresh_match = re.search(r'refreshRate=([0-9.]+)', result)
                if refresh_match:
                    refresh_rate = float(refresh_match.group(1))
                    
                    # Check if app is actively drawing
                    if 'mHasSurface=true' in result and 'mIsWallpaper=false' in result:
                        # Assume app is running at system refresh rate if actively drawing
                        return round(min(refresh_rate, 120), 2)
                        
        except Exception as e:
            logger.debug(f"Window dump FPS method failed for {package_name}: {e}")
        return None
        
    def _is_app_in_foreground(self, package_name: str) -> bool:
        """Check if the app is currently in the foreground"""
        try:
            # Method 1: Check current activity
            result = self._run_adb_command("shell dumpsys activity activities")
            if result and f'* Hist #{0}:' in result and package_name in result:
                return True
                
            # Method 2: Check window focus
            window_result = self._run_adb_command("shell dumpsys window windows")
            if window_result:
                focus_match = re.search(r'mCurrentFocus=.*?{.*?' + re.escape(package_name), window_result)
                if focus_match:
                    return True
                    
        except Exception as e:
            logger.debug(f"Failed to check foreground status for {package_name}: {e}")
        return False
        
    def _get_app_power_stats(self, package_name: str) -> Dict[str, float]:
        power_info = {}
        
        # Method 1: Try batterystats detailed analysis
        power_data = self._get_power_via_batterystats(package_name)
        power_info.update(power_data)
        
        # Method 2: Try procstats for additional metrics
        proc_data = self._get_power_via_procstats(package_name)
        power_info.update(proc_data)
        
        # Method 3: Estimate power from CPU and other metrics
        estimated_power = self._estimate_power_consumption(package_name)
        if estimated_power is not None and 'power_consumption' not in power_info:
            power_info['power_consumption'] = estimated_power
            
        return power_info
        
    def _get_power_via_batterystats(self, package_name: str) -> Dict[str, float]:
        try:
            result = self._run_adb_command(f"shell dumpsys batterystats {package_name}")
            if result:
                power_info = {}
                
                # Parse various power-related metrics
                # Estimated power consumption
                power_patterns = [
                    r'Estimated power use.*?(\d+(?:\.\d+)?)mAh',
                    r'Power use \(mAh\):\s*(\d+(?:\.\d+)?)',
                    r'Total.*?(\d+(?:\.\d+)?)mAh'
                ]
                
                for pattern in power_patterns:
                    power_match = re.search(pattern, result, re.IGNORECASE)
                    if power_match:
                        power_info['power_consumption'] = float(power_match.group(1))
                        break
                
                # Wake locks
                wakelock_patterns = [
                    r'Wake lock.*?count=(\d+)',
                    r'Wakelock.*?(\d+)\s+times',
                    r'partial.*?count:\s*(\d+)'
                ]
                
                total_wakelocks = 0
                for pattern in wakelock_patterns:
                    matches = re.findall(pattern, result, re.IGNORECASE)
                    if matches:
                        total_wakelocks += sum(int(count) for count in matches)
                
                if total_wakelocks > 0:
                    power_info['wakelock_count'] = total_wakelocks
                
                # Alarms
                alarm_patterns = [
                    r'Alarm.*?count=(\d+)',
                    r'alarms:\s*(\d+)',
                    r'wakeups:\s*(\d+)'
                ]
                
                total_alarms = 0
                for pattern in alarm_patterns:
                    matches = re.findall(pattern, result, re.IGNORECASE)
                    if matches:
                        total_alarms += sum(int(count) for count in matches)
                
                if total_alarms > 0:
                    power_info['alarm_count'] = total_alarms
                
                # CPU time (can be used for power estimation)
                cpu_time_match = re.search(r'CPU:\s*(\d+)ms', result)
                if cpu_time_match:
                    cpu_time_ms = int(cpu_time_match.group(1))
                    power_info['cpu_time_ms'] = cpu_time_ms
                
                # Network activity
                network_patterns = [
                    r'Network:\s*(\d+(?:\.\d+)?)\s*KB received.*?(\d+(?:\.\d+)?)\s*KB sent',
                    r'Wifi.*?(\d+)\s*KB.*?(\d+)\s*KB',
                    r'Mobile.*?(\d+)\s*KB.*?(\d+)\s*KB'
                ]
                
                for pattern in network_patterns:
                    net_match = re.search(pattern, result, re.IGNORECASE)
                    if net_match:
                        rx_kb = float(net_match.group(1))
                        tx_kb = float(net_match.group(2))
                        power_info['network_rx_kb'] = rx_kb
                        power_info['network_tx_kb'] = tx_kb
                        break
                
                return power_info
                
        except Exception as e:
            logger.debug(f"Batterystats power method failed for {package_name}: {e}")
        return {}
        
    def _get_power_via_procstats(self, package_name: str) -> Dict[str, float]:
        try:
            # Get additional process statistics
            result = self._run_adb_command(f"shell dumpsys procstats {package_name}")
            if result:
                power_info = {}
                
                # Parse process runtime statistics
                runtime_match = re.search(r'TOTAL:\s*(\d+)ms', result)
                if runtime_match:
                    total_runtime = int(runtime_match.group(1))
                    power_info['total_runtime_ms'] = total_runtime
                
                # Memory usage over time (affects power)
                mem_matches = re.findall(r'(\d+)K/(\d+)K/(\d+)K', result)
                if mem_matches:
                    avg_memory = sum(int(match[1]) for match in mem_matches) / len(mem_matches)
                    power_info['avg_memory_kb'] = round(avg_memory, 2)
                
                return power_info
                
        except Exception as e:
            logger.debug(f"Procstats power method failed for {package_name}: {e}")
        return {}
        
    def _estimate_power_consumption(self, package_name: str) -> Optional[float]:
        """Enhanced power consumption estimation based on multiple metrics"""
        try:
            logger.debug(f"Estimating power consumption for {package_name}")
            
            # Get current performance metrics
            cpu_usage = self._get_app_cpu_usage(package_name)
            memory_info = self._get_app_memory(package_name)
            
            # Initialize power components
            total_power = 0.0
            components_found = 0
            
            # Base power for active app (varies by type)
            base_power = 5.0  # Reduced base power
            total_power += base_power
            components_found += 1
            
            # CPU-based power estimation
            if cpu_usage is not None and cpu_usage > 0:
                # More realistic CPU power model: exponential relationship
                cpu_power = min(cpu_usage * 0.8, 50)  # Cap at 50mAh for very high CPU
                total_power += cpu_power
                components_found += 1
                logger.debug(f"CPU power component: {cpu_power:.2f} mAh (CPU: {cpu_usage}%)")
            
            # Memory-based power estimation
            if memory_info and 'memory_pss' in memory_info:
                memory_mb = memory_info['memory_pss'] / 1024  # Convert to MB
                # Memory power scales with size but has diminishing returns
                memory_power = min(memory_mb * 0.02, 20)  # Cap at 20mAh
                total_power += memory_power
                components_found += 1
                logger.debug(f"Memory power component: {memory_power:.2f} mAh (Memory: {memory_mb:.1f} MB)")
            
            # Check app state for power multiplier
            foreground_multiplier = 1.0
            try:
                if self._is_app_in_foreground(package_name):
                    foreground_multiplier = 1.8  # Higher multiplier for active apps
                    logger.debug(f"App is in foreground, applying multiplier: {foreground_multiplier}")
                else:
                    foreground_multiplier = 0.4  # Background apps use less power
                    logger.debug(f"App is in background, applying multiplier: {foreground_multiplier}")
            except:
                foreground_multiplier = 1.0  # Default if detection fails
            
            # Apply activity-based adjustments
            try:
                # Check for network activity (higher power consumption)
                network_result = self._run_adb_command(f"shell dumpsys netstats detail uid | grep -i {package_name}")
                if network_result and any(keyword in network_result.lower() for keyword in ['rx', 'tx', 'bytes']):
                    network_bonus = 8.0
                    total_power += network_bonus
                    logger.debug(f"Network activity detected, adding {network_bonus} mAh")
                    components_found += 1
            except:
                pass
            
            # Apply foreground multiplier
            estimated_power = total_power * foreground_multiplier
            
            # Ensure reasonable bounds
            estimated_power = max(0.1, min(estimated_power, 150))  # Between 0.1 and 150 mAh
            
            if components_found > 1:  # Only return estimate if we have meaningful data
                logger.debug(f"Estimated power for {package_name}: {estimated_power:.2f} mAh (components: {components_found})")
                return round(estimated_power, 2)
            else:
                logger.debug(f"Insufficient data for power estimation of {package_name}")
                return None
            
        except Exception as e:
            logger.debug(f"Power estimation failed for {package_name}: {e}")
        return None
        
    def _get_cpu_temperature(self) -> Optional[float]:
        """Get CPU temperature if available"""
        try:
            # Try different temperature sources
            temp_sources = [
                'shell cat /sys/class/thermal/thermal_zone0/temp',
                'shell cat /sys/class/thermal/thermal_zone1/temp',
                'shell cat /sys/devices/system/cpu/cpu0/cpufreq/cpu_temp',
                'shell cat /proc/stat | grep cpu_temp'
            ]
            
            for source in temp_sources:
                result = self._run_adb_command(source)
                if result and result.strip().isdigit():
                    temp = int(result.strip())
                    # Convert from millidegrees to degrees if needed
                    if temp > 1000:
                        temp = temp / 1000.0
                    if 0 < temp < 150:  # Reasonable temperature range
                        return round(temp, 1)
                        
        except Exception as e:
            logger.debug(f"Failed to get CPU temperature: {e}")
        return None
        
    def _get_storage_info(self) -> Dict[str, float]:
        """Get storage usage information"""
        try:
            result = self._run_adb_command('shell df /data')
            if result:
                lines = result.strip().split('\n')
                for line in lines[1:]:  # Skip header
                    if '/data' in line:
                        parts = line.split()
                        if len(parts) >= 4:
                            total_kb = int(parts[1])
                            used_kb = int(parts[2])
                            available_kb = int(parts[3])
                            
                            return {
                                'storage_total_mb': round(total_kb / 1024, 2),
                                'storage_used_mb': round(used_kb / 1024, 2),
                                'storage_available_mb': round(available_kb / 1024, 2),
                                'storage_usage_percent': round((used_kb / total_kb) * 100, 2)
                            }
        except Exception as e:
            logger.debug(f"Failed to get storage info: {e}")
        return {}
        
    def _get_battery_info(self) -> Dict[str, float]:
        """Get comprehensive battery information"""
        try:
            result = self._run_adb_command('shell dumpsys battery')
            if result:
                battery_info = {}
                
                # Battery level
                level_match = re.search(r'level: (\d+)', result)
                if level_match:
                    battery_info['battery_level'] = float(level_match.group(1))
                
                # Battery temperature
                temp_match = re.search(r'temperature: (\d+)', result)
                if temp_match:
                    temp_celsius = int(temp_match.group(1)) / 10.0  # Usually in tenths of degrees
                    battery_info['battery_temperature'] = round(temp_celsius, 1)
                
                # Battery voltage
                voltage_match = re.search(r'voltage: (\d+)', result)
                if voltage_match:
                    voltage_mv = int(voltage_match.group(1))
                    battery_info['battery_voltage'] = round(voltage_mv / 1000.0, 2)  # Convert to volts
                
                # Battery health
                health_match = re.search(r'health: (\d+)', result)
                if health_match:
                    battery_info['battery_health'] = int(health_match.group(1))
                
                # Charging status
                status_match = re.search(r'status: (\d+)', result)
                if status_match:
                    battery_info['battery_status'] = int(status_match.group(1))
                
                return battery_info
                
        except Exception as e:
            logger.debug(f"Failed to get battery info: {e}")
        return {}
        
    def _get_system_load(self) -> Dict[str, float]:
        """Get system load information"""
        try:
            # Get load average
            result = self._run_adb_command('shell cat /proc/loadavg')
            if result:
                parts = result.strip().split()
                if len(parts) >= 3:
                    return {
                        'load_1min': float(parts[0]),
                        'load_5min': float(parts[1]),
                        'load_15min': float(parts[2])
                    }
                    
        except Exception as e:
            logger.debug(f"Failed to get system load: {e}")
            
        # Alternative: get process count as load indicator
        try:
            result = self._run_adb_command('shell ps | wc -l')
            if result and result.strip().isdigit():
                process_count = int(result.strip())
                return {'process_count': process_count}
        except Exception as e:
            logger.debug(f"Failed to get process count: {e}")
            
        return {}
        
    def _get_display_info(self) -> Dict[str, float]:
        """Get display-related information"""
        try:
            display_info = {}
            
            # Screen brightness
            brightness_result = self._run_adb_command('shell settings get system screen_brightness')
            if brightness_result and brightness_result.strip().isdigit():
                brightness = int(brightness_result.strip())
                # Normalize to percentage (usually 0-255)
                brightness_percent = round((brightness / 255.0) * 100, 2)
                display_info['screen_brightness'] = brightness_percent
            
            # Screen timeout
            timeout_result = self._run_adb_command('shell settings get system screen_off_timeout')
            if timeout_result and timeout_result.strip().isdigit():
                timeout_ms = int(timeout_result.strip())
                timeout_sec = timeout_ms / 1000.0
                display_info['screen_timeout_sec'] = timeout_sec
            
            # Display size and density
            display_result = self._run_adb_command('shell wm size')
            if display_result:
                size_match = re.search(r'(\d+)x(\d+)', display_result)
                if size_match:
                    width = int(size_match.group(1))
                    height = int(size_match.group(2))
                    display_info['screen_width'] = width
                    display_info['screen_height'] = height
            
            density_result = self._run_adb_command('shell wm density')
            if density_result:
                density_match = re.search(r'(\d+)', density_result)
                if density_match:
                    display_info['screen_density'] = int(density_match.group(1))
                    
            # Screen state (on/off)
            screen_state = self._run_adb_command('shell dumpsys power | grep "Display Power"')
            if screen_state:
                if 'ON' in screen_state.upper():
                    display_info['screen_on'] = 1.0
                else:
                    display_info['screen_on'] = 0.0
                    
            return display_info
            
        except Exception as e:
            logger.debug(f"Failed to get display info: {e}")
        return {}
    
    # Optimized parser methods for parallel execution
    def _parse_cpu_usage(self, result: str) -> Optional[float]:
        """Parse CPU usage from /proc/stat output"""
        try:
            lines = result.split('\n')
            cpu_line = lines[0]  # First line is total CPU
            values = cpu_line.split()[1:]
            values = [int(v) for v in values]
            
            total = sum(values)
            idle = values[3]  # idle time
            usage = ((total - idle) / total) * 100
            return round(usage, 2)
        except:
            return None
    
    def _parse_cpu_temperature(self, result: str) -> Optional[float]:
        """Parse CPU temperature from thermal zone"""
        try:
            temp = int(result.strip()) / 1000.0  # Convert from millidegrees
            return round(temp, 1)
        except:
            return None
    
    def _parse_memory_info(self, result: str) -> Dict[str, float]:
        """Parse memory info from /proc/meminfo"""
        memory_info = {}
        try:
            for line in result.split('\n'):
                if 'MemTotal:' in line:
                    total_match = re.search(r'(\d+)', line)
                    if total_match:
                        memory_info['memory_total'] = round(int(total_match.group(1)) / 1024, 2)
                elif 'MemAvailable:' in line:
                    avail_match = re.search(r'(\d+)', line)
                    if avail_match:
                        memory_info['memory_available'] = round(int(avail_match.group(1)) / 1024, 2)
                elif 'MemFree:' in line:
                    free_match = re.search(r'(\d+)', line)
                    if free_match:
                        memory_info['memory_free'] = round(int(free_match.group(1)) / 1024, 2)
                        
            # Calculate used memory and usage percentage
            if 'memory_total' in memory_info and 'memory_available' in memory_info:
                memory_info['memory_used'] = round(memory_info['memory_total'] - memory_info['memory_available'], 2)
                memory_info['memory_system_available'] = memory_info['memory_available']
                # 计算内存使用百分比
                usage_percent = (memory_info['memory_used'] / memory_info['memory_total']) * 100
                memory_info['memory_usage_percent'] = round(usage_percent, 2)
                
        except Exception as e:
            logger.debug(f"Failed to parse memory info: {e}")
        return memory_info
    
    def _parse_storage_info(self, result: str) -> Dict[str, float]:
        """Parse storage info from df output"""
        storage_info = {}
        try:
            lines = result.split('\n')
            if len(lines) > 1:
                parts = lines[1].split()
                if len(parts) >= 4:
                    total_kb = int(parts[1])
                    used_kb = int(parts[2])
                    avail_kb = int(parts[3])
                    
                    storage_info['storage_total'] = round(total_kb / 1024, 2)
                    storage_info['storage_used'] = round(used_kb / 1024, 2)
                    storage_info['storage_available'] = round(avail_kb / 1024, 2)
                    storage_info['storage_usage_percent'] = round((used_kb / total_kb) * 100, 2)
        except Exception as e:
            logger.debug(f"Failed to parse storage info: {e}")
        return storage_info
    
    def _parse_battery_info(self, result: str) -> Dict[str, float]:
        """Parse battery info from dumpsys battery"""
        battery_info = {}
        try:
            for line in result.split('\n'):
                if 'level:' in line:
                    level_match = re.search(r'level: (\d+)', line)
                    if level_match:
                        battery_info['battery_level'] = float(level_match.group(1))
                elif 'temperature:' in line:
                    temp_match = re.search(r'temperature: (\d+)', line)
                    if temp_match:
                        battery_info['battery_temperature'] = round(int(temp_match.group(1)) / 10.0, 1)
                elif 'voltage:' in line:
                    volt_match = re.search(r'voltage: (\d+)', line)
                    if volt_match:
                        battery_info['battery_voltage'] = round(int(volt_match.group(1)) / 1000.0, 3)
        except Exception as e:
            logger.debug(f"Failed to parse battery info: {e}")
        return battery_info
    
    def _parse_network_stats(self, result: str) -> Dict[str, float]:
        """Parse network stats from /proc/net/dev"""
        network_data = {}
        try:
            lines = result.split('\n')[2:]  # Skip headers
            total_rx = total_tx = 0
            
            for line in lines:
                if ':' in line:
                    parts = line.split(':')[1].split()
                    rx_bytes = int(parts[0])
                    tx_bytes = int(parts[8])
                    total_rx += rx_bytes
                    total_tx += tx_bytes
            
            # Convert to KB
            current_time = time.time()
            rx_kb = total_rx / 1024
            tx_kb = total_tx / 1024
            
            network_data = {
                'network_rx_total': round(rx_kb, 2),
                'network_tx_total': round(tx_kb, 2)
            }
            
            # Calculate speed if we have previous data
            if hasattr(self, '_last_system_network'):
                time_diff = current_time - self._last_system_network['time']
                if time_diff > 0:
                    rx_speed = (rx_kb - self._last_system_network['rx']) / time_diff
                    tx_speed = (tx_kb - self._last_system_network['tx']) / time_diff
                    network_data['network_rx'] = round(max(0, rx_speed), 2)
                    network_data['network_tx'] = round(max(0, tx_speed), 2)
            
            self._last_system_network = {
                'time': current_time,
                'rx': rx_kb,
                'tx': tx_kb
            }
            
        except Exception as e:
            logger.debug(f"Failed to parse network stats: {e}")
        return network_data
    
    def _parse_load_info(self, result: str) -> Dict[str, float]:
        """Parse system load from /proc/loadavg"""
        load_info = {}
        try:
            parts = result.strip().split()
            if len(parts) >= 3:
                load_info['load_1min'] = float(parts[0])
                load_info['load_5min'] = float(parts[1])
                load_info['load_15min'] = float(parts[2])
        except Exception as e:
            logger.debug(f"Failed to parse load info: {e}")
        return load_info
    
    def _parse_display_info(self, result: str) -> Dict[str, float]:
        """Parse display info from wm size output"""
        display_info = {}
        try:
            if 'x' in result:
                size_match = re.search(r'(\d+)x(\d+)', result)
                if size_match:
                    display_info['screen_width'] = float(size_match.group(1))
                    display_info['screen_height'] = float(size_match.group(2))
        except Exception as e:
            logger.debug(f"Failed to parse display info: {e}")
        return display_info
    
    def _parse_uptime_info(self, result: str) -> Dict[str, float]:
        """Parse uptime info from /proc/uptime"""
        uptime_info = {}
        try:
            # /proc/uptime format: "uptime_seconds idle_seconds"
            # Example: "12345.67 98765.43"
            parts = result.strip().split()
            if len(parts) >= 2:
                uptime_seconds = float(parts[0])
                idle_seconds = float(parts[1])
                
                # Convert to more readable formats
                uptime_info['uptime_seconds'] = round(uptime_seconds, 2)
                uptime_info['uptime_hours'] = round(uptime_seconds / 3600, 2)
                uptime_info['uptime_days'] = round(uptime_seconds / 86400, 2)
                
                # Calculate system load percentage (100% - idle percentage)
                if uptime_seconds > 0:
                    idle_percentage = (idle_seconds / uptime_seconds) * 100
                    system_load_percentage = 100 - idle_percentage
                    uptime_info['system_load_percentage'] = round(max(0, min(100, system_load_percentage)), 2)
                    uptime_info['idle_percentage'] = round(min(100, idle_percentage), 2)
                
                # Add idle time info
                uptime_info['idle_seconds'] = round(idle_seconds, 2)
                
        except Exception as e:
            logger.debug(f"Failed to parse uptime info: {e}")
        return uptime_info
    
    # App-specific parser methods
    def _parse_app_cpu_usage(self, result: str, package_name: str) -> Optional[float]:
        """Parse app CPU usage from cpuinfo output"""
        try:
            if package_name in result:
                lines = result.split('\n')
                for line in lines:
                    if package_name in line and '%' in line:
                        match = re.search(r'(\d+(?:\.\d+)?)%', line)
                        if match:
                            return float(match.group(1))
        except:
            return None
        return None
    
    def _parse_app_memory_info(self, result: str) -> Dict[str, float]:
        """Parse app memory info from meminfo output"""
        memory_info = {}
        try:
            # Parse PSS memory
            pss_match = re.search(r'TOTAL\s+(\d+)', result)
            if pss_match:
                memory_info['memory_pss'] = round(int(pss_match.group(1)) / 1024, 2)
            
            # Parse Java heap
            java_match = re.search(r'Java Heap:\s+(\d+)', result)
            if java_match:
                memory_info['memory_java'] = round(int(java_match.group(1)) / 1024, 2)
            
            # Parse Native heap
            native_match = re.search(r'Native Heap:\s+(\d+)', result)
            if native_match:
                memory_info['memory_native'] = round(int(native_match.group(1)) / 1024, 2)
                
        except Exception as e:
            logger.debug(f"Failed to parse app memory info: {e}")
        return memory_info
    
    def _parse_app_fps(self, result: str) -> Optional[float]:
        """Parse app FPS from gfxinfo framestats output"""
        try:
            lines = result.split('\n')
            frame_times = []
            
            for line in lines:
                if line.strip() and not line.startswith('---'):
                    parts = line.split(',')
                    if len(parts) >= 2:
                        try:
                            # Parse frame time (usually in column 1 or 2)
                            frame_start = int(parts[1])
                            frame_end = int(parts[2]) if len(parts) > 2 else frame_start
                            frame_duration = frame_end - frame_start
                            
                            if frame_duration > 0:
                                frame_times.append(frame_duration)
                        except (ValueError, IndexError):
                            continue
            
            if frame_times and len(frame_times) > 5:
                # Calculate average frame time and convert to FPS
                avg_frame_time_ns = sum(frame_times) / len(frame_times)
                avg_frame_time_ms = avg_frame_time_ns / 1_000_000  # Convert to milliseconds
                
                if avg_frame_time_ms > 0:
                    fps = 1000 / avg_frame_time_ms  # Convert to FPS
                    fps = round(min(fps, 120), 1)  # Cap at 120 FPS
                    
                    # Validate FPS (should be reasonable)
                    if 1 <= fps <= 120:
                        logger.debug(f"Calculated FPS: {fps} from {len(frame_times)} samples")
                        return fps
                    else:
                        logger.debug(f"Invalid FPS calculated: {fps}")
            
            # If framestats parsing fails, try alternative method
            logger.debug("Framestats parsing failed, trying alternative FPS detection")
            return self._parse_fps_alternative(result)
                    
        except Exception as e:
            logger.debug(f"Failed to parse app FPS: {e}")
            logger.debug(f"FPS result sample: {result[:200] if result else 'None'}")
        return None
    
    def _parse_fps_alternative(self, result: str) -> Optional[float]:
        """Alternative FPS parsing method"""
        try:
            # Use compiled patterns for better performance
            for pattern in self._compiled_patterns['fps_alternative']:
                fps_match = pattern.search(result)
                if fps_match:
                    fps = float(fps_match.group(1))
                    if 1 <= fps <= 120:
                        logger.debug(f"Found FPS via alternative method: {fps}")
                        return round(fps, 1)
            
        except Exception as e:
            logger.debug(f"Alternative FPS parsing failed: {e}")
        return None
    
    def _parse_app_power_info(self, result: str) -> Dict[str, float]:
        """Parse app power info from batterystats output"""
        power_info = {}
        if not result or result.strip() == "":
            logger.debug("Empty power info result")
            return power_info
            
        try:
            # Log first 300 characters of batterystats output for debugging
            logger.debug(f"Batterystats output sample: {result[:300]}...")
            
            # Use compiled patterns for better performance
            for i, pattern in enumerate(self._compiled_patterns['power_consumption']):
                power_match = pattern.search(result)
                if power_match:
                    power_value = float(power_match.group(1))
                    # Validate power consumption (should be reasonable)
                    if 0 <= power_value <= 10000:  # 0 to 10000 mAh seems reasonable
                        power_info['power_consumption'] = round(power_value, 2)
                        logger.debug(f"Found power consumption: {power_value} using pattern {i}")
                        break
                    else:
                        logger.debug(f"Power value {power_value} out of range, trying next pattern")
            
            # If no power consumption found, try parsing battery usage statistics
            if 'power_consumption' not in power_info:
                logger.debug("No direct power consumption found, trying alternative parsing")
                power_info.update(self._parse_alternative_power_data(result))
            
            # Parse wakelock count with multiple patterns
            wakelock_patterns = [
                r'Wake lock.*?count=(\d+)',
                r'Wakelock.*?(\d+)\s+times',
                r'partial.*?count:\s*(\d+)',
                r'Wakelocks:\s*(\d+)',
                r'Wake locks:\s*(\d+)'
            ]
            
            for pattern in wakelock_patterns:
                wakelock_match = re.search(pattern, result, re.IGNORECASE)
                if wakelock_match:
                    wakelock_count = int(wakelock_match.group(1))
                    if 0 <= wakelock_count <= 10000:  # Reasonable range
                        power_info['wakelock_count'] = wakelock_count
                        break
            
            # If no direct power data found, try to estimate
            if 'power_consumption' not in power_info:
                estimated_power = self._estimate_power_consumption_from_stats(result)
                if estimated_power is not None:
                    power_info['power_consumption'] = estimated_power
                    logger.debug(f"Estimated power consumption: {estimated_power} mAh")
                    
        except Exception as e:
            logger.debug(f"Failed to parse app power info: {e}")
            logger.debug(f"Power result sample: {result[:200] if result else 'None'}")
        return power_info
    
    def _parse_app_power_info_enhanced(self, result: str, package_name: str) -> Dict[str, float]:
        """Enhanced app power info parsing with multiple fallback methods"""
        power_info = {}
        
        # First try the standard parsing
        power_info = self._parse_app_power_info(result)
        
        # If no power consumption found, try additional methods
        if 'power_consumption' not in power_info or power_info['power_consumption'] == 0:
            logger.debug(f"Standard parsing failed for {package_name}, trying enhanced methods")
            
            # Method 1: Try different batterystats command variations
            enhanced_power = self._try_alternative_batterystats_commands(package_name)
            if enhanced_power:
                power_info.update(enhanced_power)
                return power_info
            
            # Method 2: Try parsing general batterystats (without package name)
            general_batterystats = self._get_general_batterystats_for_package(package_name)
            if general_batterystats:
                power_info.update(general_batterystats)
                return power_info
                
            # Method 3: Estimate based on current app performance metrics
            estimated_power = self._estimate_power_consumption(package_name)
            if estimated_power is not None:
                power_info['power_consumption'] = estimated_power
                logger.debug(f"Using estimated power for {package_name}: {estimated_power} mAh")
        
        return power_info
    
    def _try_alternative_batterystats_commands(self, package_name: str) -> Dict[str, float]:
        """Try alternative batterystats commands for better power data"""
        alternative_commands = [
            f"shell dumpsys batterystats --charged {package_name}",
            f"shell dumpsys batterystats --reset {package_name}",
            f"shell dumpsys battery",  # General battery info
            f"shell cat /proc/power/wakeup_sources",  # Wakelock info
        ]
        
        for cmd in alternative_commands:
            try:
                result = self._run_adb_command(cmd)
                if result:
                    # Parse result for power information
                    power_info = self._parse_app_power_info(result)
                    if power_info and 'power_consumption' in power_info:
                        logger.debug(f"Found power data using alternative command: {cmd}")
                        return power_info
            except Exception as e:
                logger.debug(f"Alternative command failed {cmd}: {e}")
                continue
        
        return {}
    
    def _get_general_batterystats_for_package(self, package_name: str) -> Dict[str, float]:
        """Get power data from general batterystats and extract package-specific info"""
        try:
            # Get general batterystats
            result = self._run_adb_command("shell dumpsys batterystats")
            if result and package_name in result:
                # Extract package-specific section
                lines = result.split('\n')
                package_section = []
                in_package_section = False
                
                for line in lines:
                    if package_name in line:
                        in_package_section = True
                        package_section.append(line)
                    elif in_package_section:
                        if line.strip() and not line.startswith(' '):
                            # End of package section
                            break
                        package_section.append(line)
                
                if package_section:
                    section_text = '\n'.join(package_section)
                    power_info = self._parse_app_power_info(section_text)
                    if power_info:
                        logger.debug(f"Found power data in general batterystats for {package_name}")
                        return power_info
                        
        except Exception as e:
            logger.debug(f"General batterystats parsing failed: {e}")
        
        return {}
    
    def reset_battery_stats(self) -> bool:
        """Reset battery statistics to get fresh power consumption data"""
        try:
            logger.info("Resetting battery statistics for fresh power data collection")
            result = self._run_adb_command("shell dumpsys batterystats --reset")
            if result is not None:
                # Also try alternative reset methods
                self._run_adb_command("shell dumpsys battery reset")
                logger.info("Battery statistics reset successfully")
                return True
        except Exception as e:
            logger.debug(f"Failed to reset battery stats: {e}")
        return False
    
    def _parse_alternative_power_data(self, result: str) -> Dict[str, float]:
        """Parse alternative power data when standard patterns fail"""
        power_info = {}
        try:
            # Try to find any numeric value followed by power-related keywords
            alternative_patterns = [
                # Look for patterns with various separators and formats
                r'(\d+(?:\.\d+)?)\s*(?:mah|mAh|MAH)',
                r'battery.*?(\d+(?:\.\d+)?)',
                r'power.*?(\d+(?:\.\d+)?)',
                r'consumption.*?(\d+(?:\.\d+)?)',
                r'usage.*?(\d+(?:\.\d+)?)',
                # Look for percentage values that might indicate relative power usage
                r'(\d+(?:\.\d+)?)%.*?(?:battery|power|consumption)',
                # Look for time-based power indicators
                r'(\d+(?:\.\d+)?)\s*(?:ms|seconds?).*?cpu',
                r'wake.*?(\d+(?:\.\d+)?)',
            ]
            
            for pattern in alternative_patterns:
                matches = re.findall(pattern, result, re.IGNORECASE)
                if matches:
                    # Take the first reasonable value
                    for match_str in matches:
                        try:
                            value = float(match_str)
                            if 0.1 <= value <= 1000:  # Reasonable range for power consumption
                                power_info['power_consumption'] = round(value, 2)
                                logger.debug(f"Found alternative power value: {value} using pattern: {pattern}")
                                return power_info
                        except ValueError:
                            continue
            
            # If still no power data, try to extract from CPU/system activity
            power_info.update(self._estimate_power_from_activity(result))
            
        except Exception as e:
            logger.debug(f"Alternative power parsing failed: {e}")
        
        return power_info
    
    def _estimate_power_from_activity(self, result: str) -> Dict[str, float]:
        """Estimate power consumption from system activity indicators"""
        power_info = {}
        try:
            # Look for activity indicators that suggest power consumption
            activity_score = 0
            
            # CPU activity
            cpu_patterns = [r'cpu.*?(\d+(?:\.\d+)?)', r'processor.*?(\d+(?:\.\d+)?)']
            for pattern in cpu_patterns:
                matches = re.findall(pattern, result, re.IGNORECASE)
                if matches:
                    activity_score += sum(float(m) for m in matches[:3]) * 0.1  # Weight CPU activity
            
            # Network activity
            network_patterns = [r'network.*?(\d+(?:\.\d+)?)', r'wifi.*?(\d+(?:\.\d+)?)']
            for pattern in network_patterns:
                matches = re.findall(pattern, result, re.IGNORECASE)
                if matches:
                    activity_score += sum(float(m) for m in matches[:3]) * 0.05  # Weight network activity
            
            # Wake locks and alarms (high power consumers)
            wakelock_patterns = [r'wake.*?(\d+)', r'alarm.*?(\d+)']
            for pattern in wakelock_patterns:
                matches = re.findall(pattern, result, re.IGNORECASE)
                if matches:
                    activity_score += sum(float(m) for m in matches[:5]) * 0.2  # High weight for wakelocks
            
            if activity_score > 0:
                # Convert activity score to estimated power consumption (very rough approximation)
                estimated_power = min(activity_score * 0.1, 100)  # Cap at 100mAh
                power_info['power_consumption'] = round(estimated_power, 2)
                logger.debug(f"Estimated power from activity: {estimated_power} mAh (score: {activity_score})")
            
        except Exception as e:
            logger.debug(f"Activity-based power estimation failed: {e}")
        
        return power_info
    
    def _estimate_power_consumption_from_stats(self, result: str) -> Optional[float]:
        """Estimate power consumption from available battery stats"""
        try:
            # Look for CPU time, network activity, etc.
            cpu_time_patterns = [
                r'Cpu time:\s*(\d+(?:\.\d+)?)ms',
                r'CPU:\s*(\d+(?:\.\d+)?)ms',
                r'Process time:\s*(\d+(?:\.\d+)?)ms'
            ]
            
            cpu_time = 0
            for pattern in cpu_time_patterns:
                cpu_match = re.search(pattern, result, re.IGNORECASE)
                if cpu_match:
                    cpu_time = float(cpu_match.group(1))
                    break
            
            if cpu_time > 0:
                # Very rough estimation: 1ms CPU time ≈ 0.001 mAh
                estimated = round(cpu_time * 0.001, 2)
                return max(0.1, min(estimated, 100))  # Clamp between 0.1 and 100 mAh
                
        except Exception as e:
            logger.debug(f"Power estimation failed: {e}")
        return None
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        cache_stats = self.enhanced_cache.get_stats()
        
        return {
            'cache_performance': cache_stats,
            'command_execution_times': dict(self._performance_stats),
            'slow_commands': list(self._slow_commands),
            'collection_intervals': self._collection_intervals,
            'last_collection_times': dict(self._last_collection_time)
        }
    
    def optimize_collection_intervals(self):
        """动态优化采集间隔"""
        stats = self.get_performance_stats()
        
        # 根据缓存命中率调整间隔
        hit_rate = stats['cache_performance']['hit_rate']
        
        if hit_rate > 0.8:  # 命中率高，可以增加间隔
            for key in self._collection_intervals:
                self._collection_intervals[key] *= 1.1
        elif hit_rate < 0.3:  # 命中率低，减少间隔
            for key in self._collection_intervals:
                self._collection_intervals[key] *= 0.9
                
        # 限制间隔范围
        for key in self._collection_intervals:
            self._collection_intervals[key] = max(1.0, 
                min(self._collection_intervals[key], 10.0))
    
    def reset_performance_tracking(self):
        """重置性能跟踪"""
        self._performance_stats.clear()
        self._slow_commands.clear()
        self.enhanced_cache = EnhancedCache()
        self._last_collection_time.clear()
        
    def cleanup_expired_cache(self):
        """清理过期缓存"""
        current_time = time.time()
        
        # 清理L1缓存
        expired_keys = []
        for key, data in self.enhanced_cache.l1_cache.items():
            if current_time - data['time'] > 60:  # 60秒过期
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.enhanced_cache.l1_cache[key]
            
        # 清理L2缓存
        expired_keys = []
        for key, data in self.enhanced_cache.l2_cache.items():
            if current_time - data['time'] > 120:  # 120秒过期
                expired_keys.append(key)
                
        for key in expired_keys:
            del self.enhanced_cache.l2_cache[key]
    
    def _parse_top_system(self, top_output: str) -> Dict[str, float]:
        """解析系统级别的top命令输出"""
        data = {}
        
        try:
            lines = top_output.strip().split('\n')
            
            for line in lines:
                # 解析CPU总体使用率
                if 'CPU:' in line or '%cpu' in line.lower():
                    # 示例: CPU: 15%usr 5%sys 0%nic 75%idle 5%io 0%irq 0%sirq
                    cpu_match = re.search(r'(\d+(?:\.\d+)?)%idle', line)
                    if cpu_match:
                        idle_percent = float(cpu_match.group(1))
                        data['top_cpu_usage'] = 100.0 - idle_percent
                
                # 解析内存使用情况
                elif 'Mem:' in line or 'KiB Mem' in line:
                    # 示例: Mem: 1024000k total, 800000k used, 224000k free
                    mem_parts = re.findall(r'(\d+)k?\s+(\w+)', line.lower())
                    total_mem = used_mem = 0
                    
                    for value, unit in mem_parts:
                        if 'total' in unit:
                            total_mem = int(value)
                        elif 'used' in unit:
                            used_mem = int(value)
                    
                    if total_mem > 0:
                        data['top_memory_usage_percent'] = (used_mem / total_mem) * 100
                        data['top_memory_total_kb'] = total_mem
                        data['top_memory_used_kb'] = used_mem
                        
        except Exception as e:
            print(f"解析top系统输出失败: {e}")
            
        return data
    
    def _parse_top_app(self, top_output: str, package_name: str) -> Dict[str, float]:
        """解析应用级别的top命令输出"""
        data = {}
        
        try:
            lines = top_output.strip().split('\n')
            
            for line in lines:
                if package_name in line:
                    # 跳过grep命令本身的行
                    if 'grep' in line or 'sh -c' in line:
                        continue
                        
                    # 典型的top输出格式:
                    # PID USER     PR  NI  VIRT  RES  SHR S %CPU %MEM     TIME+ COMMAND
                    # 1234 u0_a123  20   0  1.2G 100M  50M S  5.0  2.5   0:10.23 com.example.app
                    
                    parts = line.split()
                    if len(parts) >= 11 and (parts[-1] == package_name or parts[-1].startswith(package_name + '.')):
                        # 匹配精确包名或以包名开头的进程名（如 com.example.app.service）
                        try:
                            cpu_percent = float(parts[8].replace('%', ''))
                            mem_percent = float(parts[9].replace('%', ''))
                            
                            data['top_cpu_usage'] = cpu_percent
                            data['top_memory_percent'] = mem_percent
                            
                            # 解析内存大小（RES列）
                            if len(parts) >= 6:
                                res_mem = parts[5]  # RES列
                                mem_kb = self._parse_memory_size(res_mem)
                                if mem_kb:
                                    data['top_memory_res_kb'] = mem_kb
                                    
                        except (ValueError, IndexError) as e:
                            print(f"解析top应用数据失败: {e}")
                            
        except Exception as e:
            print(f"解析top应用输出失败: {e}")
            
        return data
    
    def _get_actual_process_name_from_top(self, top_output: str, package_name: str) -> Optional[str]:
        """从top输出中获取实际的进程名"""
        try:
            lines = top_output.strip().split('\n')
            
            for line in lines:
                if package_name in line:
                    # 跳过grep命令本身的行
                    if 'grep' in line or 'sh -c' in line:
                        continue
                        
                    parts = line.split()
                    if len(parts) >= 11:
                        # 最后一列是进程名
                        process_name = parts[-1]
                        if process_name.startswith(package_name):
                            return process_name
                            
        except Exception as e:
            logger.debug(f"获取实际进程名失败 {package_name}: {e}")
            
        return None
    
    def _parse_memory_size(self, mem_str: str) -> float:
        """解析内存大小字符串，返回KB"""
        try:
            if not mem_str:
                return 0
                
            mem_str = mem_str.upper().strip()
            
            if mem_str.endswith('K'):
                return float(mem_str[:-1])
            elif mem_str.endswith('M'):
                return float(mem_str[:-1]) * 1024
            elif mem_str.endswith('G'):
                return float(mem_str[:-1]) * 1024 * 1024
            else:
                # 假设是字节
                return float(mem_str) / 1024
                
        except (ValueError, AttributeError):
            return 0