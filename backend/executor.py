import os
import subprocess
import time
import shutil
from typing import List, Dict, Any, Optional

class Executor:
    def __init__(self):
        # Check if docker CLI is available
        self.docker_command = 'docker'  # Default, will be updated if found
        self.docker_available = self._check_docker_available()
        if not self.docker_available:
            print("Docker not available: docker command not found or Docker not running")
    
    def _check_docker_available(self) -> bool:
        """Check if docker command is available and running"""
        # Try different possible docker command paths
        docker_commands = ['docker']
        
        # On Windows, try common Docker Desktop installation paths
        if os.name == 'nt':
            docker_commands.extend([
                r'C:\Program Files\Docker\Docker\resources\bin\docker.exe',
                r'C:\Program Files\Docker\Docker\resources\docker.exe',
                r'C:\Program Files\Docker\Docker\docker.exe'
            ])
        
        for docker_cmd in docker_commands:
            try:
                # Test docker --version
                result = subprocess.run(
                    [docker_cmd, '--version'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    # Store the working docker command
                    self.docker_command = docker_cmd
                    
                    # Try docker info to verify daemon is running
                    result = subprocess.run(
                        [docker_cmd, 'info'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        print(f"Docker found at: {docker_cmd}")
                        return True
            except Exception:
                continue
        
        return False
    
    def execute_commands(self, project_types: List[str], temp_dir: str, file_paths: Dict[str, str]) -> Dict[str, Any]:
        """Execute deployment commands in Docker sandbox"""
        if not self.docker_available:
            return {
                "success": False,
                "error": "Docker is not available. Please ensure Docker is running and accessible."
            }
        
        results = []
        
        try:
            # Use standard python:3.11-slim image instead of custom sandbox
            sandbox_image = "python:3.11-slim"
            
            # Pull the image if not exists
            if not self._ensure_image_exists(sandbox_image):
                return {
                    "success": False,
                    "error": "Failed to pull Docker image"
                }
            
            # Execute commands based on project types
            if 'python' in project_types:
                results.extend(self._execute_python_commands(temp_dir, sandbox_image))
            
            if 'nodejs' in project_types:
                results.extend(self._execute_nodejs_commands(temp_dir, sandbox_image))
            
            if 'docker' in project_types:
                results.extend(self._execute_docker_commands(temp_dir))
            
            if 'compose' in project_types:
                results.extend(self._execute_compose_commands(temp_dir))
            
            return {
                "success": True,
                "results": results
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Execution failed: {str(e)}"
            }
    
    def _ensure_image_exists(self, image_name: str) -> bool:
        """Ensure Docker image exists, pull if not"""
        try:
            # Check if image exists locally
            result = subprocess.run(
                [self.docker_command, 'images', '-q', image_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                return True
            
            # Pull the image
            print(f"Pulling Docker image: {image_name}")
            result = subprocess.run(
                [self.docker_command, 'pull', image_name],
                capture_output=True,
                text=True,
                timeout=120
            )
            return result.returncode == 0
        except Exception as e:
            print(f"Failed to ensure image exists: {e}")
            return False
    
    def _execute_python_commands(self, temp_dir: str, sandbox_image: str) -> List[Dict[str, Any]]:
        """Execute Python-related commands"""
        results = []
        
        commands = [
            "pip install -r requirements.txt --dry-run",
            "pip check"
        ]
        
        for cmd in commands:
            result = self._run_in_container(
                image=sandbox_image,
                command=cmd,
                volume_path=temp_dir,
                workdir="/app"
            )
            result["command"] = cmd
            results.append(result)
        
        return results
    
    def _execute_nodejs_commands(self, temp_dir: str, sandbox_image: str) -> List[Dict[str, Any]]:
        """Execute Node.js-related commands"""
        results = []
        
        commands = [
            "npm install --dry-run",
            "npm ls"
        ]
        
        for cmd in commands:
            result = self._run_in_container(
                image=sandbox_image,
                command=cmd,
                volume_path=temp_dir,
                workdir="/app"
            )
            result["command"] = cmd
            results.append(result)
        
        return results
    
    def _execute_docker_commands(self, temp_dir: str) -> List[Dict[str, Any]]:
        """Execute Docker build commands"""
        results = []
        
        # Docker build needs to be run on the host, not in a container
        cmd = f"{self.docker_command} build {temp_dir} --no-cache"
        
        try:
            start_time = time.time()
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=temp_dir
            )
            duration = int((time.time() - start_time) * 1000)
            
            results.append({
                "command": cmd,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "duration_ms": duration
            })
            
        except subprocess.TimeoutExpired:
            results.append({
                "command": cmd,
                "stdout": "",
                "stderr": "Command timed out after 60 seconds",
                "exit_code": -1,
                "duration_ms": 60000
            })
        except Exception as e:
            results.append({
                "command": cmd,
                "stdout": "",
                "stderr": f"Failed to run command: {str(e)}",
                "exit_code": -1,
                "duration_ms": 0
            })
        
        return results
    
    def _execute_compose_commands(self, temp_dir: str) -> List[Dict[str, Any]]:
        """Execute docker-compose commands"""
        results = []
        
        cmd = f"{self.docker_command}-compose config"
        
        try:
            start_time = time.time()
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=temp_dir
            )
            duration = int((time.time() - start_time) * 1000)
            
            results.append({
                "command": cmd,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "duration_ms": duration
            })
            
        except subprocess.TimeoutExpired:
            results.append({
                "command": cmd,
                "stdout": "",
                "stderr": "Command timed out after 60 seconds",
                "exit_code": -1,
                "duration_ms": 60000
            })
        except Exception as e:
            results.append({
                "command": cmd,
                "stdout": "",
                "stderr": f"Failed to run command: {str(e)}",
                "exit_code": -1,
                "duration_ms": 0
            })
        
        return results
    
    def _run_in_container(self, image: str, command: str, volume_path: str, workdir: str = "/app") -> Dict[str, Any]:
        """Run a command inside a Docker container using subprocess"""
        try:
            start_time = time.time()
            
            # Convert Windows path to Docker volume path format
            if os.name == 'nt':  # Windows
                volume_path = volume_path.replace('\\', '/')
                volume_mount = f"{volume_path}:{workdir}:ro"
            else:
                volume_mount = f"{volume_path}:{workdir}:ro"
            
            # Build docker run command
            docker_cmd = [
                self.docker_command, 'run', '--rm',
                '-v', volume_mount,
                '-w', workdir,
                '--network=none',
                '--memory=512m',
                '--cpus=0.5',
                image,
                'sh', '-c', command
            ]
            
            # Execute docker run command
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            duration = int((time.time() - start_time) * 1000)
            
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "duration_ms": duration
            }
            
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": "Command timed out after 60 seconds",
                "exit_code": -1,
                "duration_ms": 60000
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": f"Container execution failed: {str(e)}",
                "exit_code": -1,
                "duration_ms": 0
            }
