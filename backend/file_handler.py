import os
import zipfile
import tempfile
import shutil
from typing import Dict, List, Any
from pathlib import Path

# Directories and files to skip
SKIP_DIRS = {'.git', '.venv', 'venv', '__pycache__', 'node_modules', '.idea', '.vscode', 'dist', 'build'}
SKIP_EXTENSIONS = {'.pyc', '.pyo', '.pyd', '.so', '.dll', '.exe', '.bin', '.zip', '.tar', '.gz', '.rar'}

class FileHandler:
    def __init__(self):
        self.temp_dir = None
    
    def extract_zip(self, zip_file_path: str) -> Dict[str, Any]:
        """Extract zip file to temporary directory and analyze contents"""
        try:
            # Create temporary directory
            self.temp_dir = tempfile.mkdtemp(prefix="deploycheck_")
            
            # Extract zip file
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                zip_ref.extractall(self.temp_dir)
            
            # Unwrap single top-level directory if present (e.g., zip created with root wrapper folder)
            entries = [e for e in os.listdir(self.temp_dir) if e not in SKIP_DIRS and not e.startswith('__MACOSX') and not e.startswith('.')]
            if len(entries) == 1:
                single_dir = os.path.join(self.temp_dir, entries[0])
                if os.path.isdir(single_dir):
                    self.temp_dir = single_dir

            # Analyze extracted files
            project_info = self._analyze_project(self.temp_dir)
            
            return {
                "success": True,
                "temp_dir": self.temp_dir,
                **project_info
            }
            
        except Exception as e:
            self.cleanup()
            return {
                "success": False,
                "error": f"Failed to extract zip file: {str(e)}"
            }
    
    def _analyze_project(self, directory: str) -> Dict[str, Any]:
        """Analyze project directory to detect project types and files"""
        project_types = []
        file_paths = {}
        
        # Walk through all files in the directory
        for root, dirs, files in os.walk(directory):
            # Skip directories we don't want to scan
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            
            for file in files:
                # Skip files with binary extensions
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext in SKIP_EXTENSIONS:
                    continue
                
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, directory)
                
                # Store all file paths
                file_paths[relative_path] = file_path
                
                # Detect project types based on specific files
                if file == 'requirements.txt':
                    project_types.append('python')
                elif file == 'package.json':
                    project_types.append('nodejs')
                elif file == 'Dockerfile':
                    project_types.append('docker')
                elif file == 'docker-compose.yml' or file == 'docker-compose.yaml':
                    project_types.append('compose')
                elif file == '.env':
                    project_types.append('env')
        
        # Remove duplicates while preserving order
        project_types = list(dict.fromkeys(project_types))
        
        return {
            "project_types": project_types,
            "file_paths": file_paths
        }
    
    def get_env_file_content(self, directory: str) -> Dict[str, str]:
        """Parse .env file and return key-value pairs"""
        env_vars = {}
        env_file_path = os.path.join(directory, '.env')
        
        if os.path.exists(env_file_path):
            try:
                with open(env_file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            env_vars[key.strip()] = value.strip()
            except Exception as e:
                print(f"Error reading .env file: {e}")
        
        return env_vars
    
    def find_env_usage_in_code(self, directory: str) -> Dict[str, List[str]]:
        """Find environment variable usage in Python and JavaScript files"""
        env_usage = {
            'python': [],
            'javascript': []
        }
        
        for root, dirs, files in os.walk(directory):
            # Skip directories we don't want to scan
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            
            for file in files:
                # Skip files with binary extensions
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext in SKIP_EXTENSIONS:
                    continue
                
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, directory)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                        # Check Python files for os.getenv, os.environ.get, or os.environ[...]
                        if file.endswith('.py'):
                            import re
                            matches = re.findall(r'(?:os\.environ\.get|os\.getenv)\([\'"]([^\'"]+)[\'"]', content)
                            matches.extend(re.findall(r'os\.environ\[[\'"]([^\'"]+)[\'"]\]', content))
                            for match in set(matches):
                                env_usage['python'].append({
                                    'file': relative_path,
                                    'var': match
                                })
                        
                        # Check JavaScript files for process.env usage
                        elif file.endswith('.js') or file.endswith('.ts') or file.endswith('.jsx') or file.endswith('.tsx'):
                            import re
                            matches = re.findall(r'process\.env\.([A-Za-z_][A-Za-z0-9_]*)', content)
                            for match in matches:
                                env_usage['javascript'].append({
                                    'file': relative_path,
                                    'var': match
                                })
                                
                except UnicodeDecodeError:
                    # Skip binary files that can't be decoded as UTF-8
                    pass
                except Exception as e:
                    print(f"Error reading file {file_path}: {e}")
        
        return env_usage
    
    def check_missing_project_files(self, directory: str, file_paths: Dict[str, str]) -> List[Dict[str, Any]]:
        """Detect missing package.json or requirements.txt when source files exist in a directory"""
        issues = []
        js_dirs = set()
        py_dirs = set()
        
        for rel_path in file_paths.keys():
            ext = os.path.splitext(rel_path)[1].lower()
            rel_dir = os.path.dirname(rel_path)
            if ext in ('.js', '.ts', '.jsx', '.tsx') and not rel_path.startswith('node_modules'):
                js_dirs.add(rel_dir)
            elif ext == '.py':
                py_dirs.add(rel_dir)
                
        for j_dir in js_dirs:
            pkg_file = os.path.join(directory, j_dir, 'package.json') if j_dir else os.path.join(directory, 'package.json')
            root_pkg = os.path.join(directory, 'package.json')
            if not os.path.exists(pkg_file) and not os.path.exists(root_pkg):
                dir_label = f"in '{j_dir}/'" if j_dir else "in root directory"
                issues.append({
                    "severity": "critical",
                    "title": f"Missing package.json {dir_label}",
                    "explanation": f"JavaScript/TypeScript source files were found {dir_label}, but no package.json file exists to define project dependencies.",
                    "fix": f"Add a package.json file {dir_label} specifying required dependencies.",
                    "file": os.path.join(j_dir, 'package.json') if j_dir else 'package.json'
                })

        for p_dir in py_dirs:
            req_file = os.path.join(directory, p_dir, 'requirements.txt') if p_dir else os.path.join(directory, 'requirements.txt')
            root_req = os.path.join(directory, 'requirements.txt')
            if not os.path.exists(req_file) and not os.path.exists(root_req):
                dir_label = f"in '{p_dir}/'" if p_dir else "in root directory"
                issues.append({
                    "severity": "warning",
                    "title": f"Missing requirements.txt {dir_label}",
                    "explanation": f"Python source files were found {dir_label}, but no requirements.txt file exists to define dependencies.",
                    "fix": f"Add a requirements.txt file {dir_label} specifying required Python packages.",
                    "file": os.path.join(p_dir, 'requirements.txt') if p_dir else 'requirements.txt'
                })

        return issues

    def cleanup(self):
        """Clean up temporary directory"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                self.temp_dir = None
            except Exception as e:
                print(f"Error cleaning up temp directory: {e}")
