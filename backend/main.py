import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file FIRST before any imports
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
    print(f"Loaded .env from: {env_path}")
else:
    # Fallback to current directory
    load_dotenv()
    print("Loaded .env from current directory")

# Debug: Check if API key is loaded
api_key = os.getenv('GROQ_API_KEY')
if api_key:
    print(f"GROQ_API_KEY loaded successfully (length: {len(api_key)})")
else:
    print("WARNING: GROQ_API_KEY not found in environment variables")

import tempfile
import shutil
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Dict, Any, List
import uvicorn

from file_handler import FileHandler
from executor import Executor
from analyzer import Analyzer
from database import init_db, get_db
from auth import get_current_user_optional, get_current_user
import json

app = FastAPI(title="DeployCheck API", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
init_db()

# Initialize components
file_handler = FileHandler()
executor = Executor()
analyzer = Analyzer()

# Include auth router
from auth import router as auth_router
app.include_router(auth_router)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "deploycheck-api"}

@app.post("/upload")
async def upload_and_analyze(
    file: UploadFile = File(...),
    current_user = Depends(get_current_user_optional)
):
    """Upload zip file and analyze deployment issues"""
    
    # Validate file type
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Only zip files are allowed")
    
    # Create temporary file for upload
    temp_zip_path = None
    try:
        # Save uploaded file to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:
            temp_zip_path = temp_file.name
            shutil.copyfileobj(file.file, temp_file)
        
        # Extract and analyze files
        extract_result = file_handler.extract_zip(temp_zip_path)
        
        if not extract_result["success"]:
            raise HTTPException(status_code=400, detail=extract_result["error"])
        
        temp_dir = extract_result["temp_dir"]
        project_types = extract_result["project_types"]
        file_paths = extract_result["file_paths"]
        
        # Execute deployment commands
        exec_result = executor.execute_commands(project_types, temp_dir, file_paths)
        
        command_results = []
        all_issues = []
        
        if exec_result["success"]:
            command_results = exec_result["results"]
        else:
            # Docker not available - add a warning issue
            print(f"Docker execution failed: {exec_result.get('error', 'Unknown error')}")
            command_results = []
            # Add Docker availability issue
            all_issues.append({
                "severity": "warning",
                "title": "Docker Not Available",
                "explanation": "Docker is not running, so deployment command execution is skipped. Only file analysis and environment variable checks are performed.",
                "fix": "Start Docker Desktop to enable full deployment analysis including pip install, npm install, and Docker build checks.",
                "file": None
            })
        
        # Analyze environment variables
        env_vars = file_handler.get_env_file_content(temp_dir)
        env_usage = file_handler.find_env_usage_in_code(temp_dir)
        env_issues = analyzer.analyze_env_var_mismatch(env_vars, env_usage)
        
        # Analyze individual command results
        for result in command_results:
            issue = analyzer.analyze_command_result(
                result["command"],
                result["exit_code"],
                result["stdout"],
                result["stderr"]
            )
            if issue:
                all_issues.append(issue)
        
        # Analyze cross-file issues
        cross_file_issues = analyzer.analyze_cross_file_issues(command_results)
        all_issues.extend(cross_file_issues)
        
        # Add environment variable issues
        all_issues.extend(env_issues)
        
        # Prepare response
        response_data = {
            "files_detected": {
                "project_types": project_types,
                "file_count": len(file_paths),
                "files": list(file_paths.keys())
            },
            "commands_run": [
                {
                    "command": result["command"],
                    "exit_code": result["exit_code"],
                    "duration_ms": result["duration_ms"],
                    "success": result["exit_code"] == 0
                }
                for result in command_results
            ],
            "raw_output": [
                {
                    "command": result["command"],
                    "stdout": result["stdout"],
                    "stderr": result["stderr"],
                    "exit_code": result["exit_code"]
                }
                for result in command_results
            ],
            "issues": all_issues,
            "summary": {
                "total_issues": len(all_issues),
                "critical": len([i for i in all_issues if i.get("severity") == "critical"]),
                "warning": len([i for i in all_issues if i.get("severity") == "warning"]),
                "info": len([i for i in all_issues if i.get("severity") == "info"])
            }
        }
        
        # Save analysis to database if user is logged in
        if current_user:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO analyses 
                    (user_id, filename, critical_count, warning_count, passed_count, total_files, issues_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        current_user["id"],
                        file.filename,
                        len([i for i in all_issues if i.get("severity") == "critical"]),
                        len([i for i in all_issues if i.get("severity") == "warning"]),
                        len([r for r in command_results if r["exit_code"] == 0]),
                        len(file_paths),
                        json.dumps(response_data)
                    )
                )
                conn.commit()
                response_data["analysis_id"] = cursor.lastrowid
        
        return JSONResponse(content=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        # Cleanup
        if temp_zip_path and os.path.exists(temp_zip_path):
            try:
                os.unlink(temp_zip_path)
            except:
                pass
        
        file_handler.cleanup()

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "DeployCheck API",
        "description": "Catch deployment errors before they happen",
        "version": "1.0.0"
    }

@app.get("/dashboard")
async def get_dashboard(
    current_user = Depends(get_current_user)
):
    """Get dashboard statistics for logged in user"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get all analyses for the user
        cursor.execute(
            "SELECT * FROM analyses WHERE user_id = ? ORDER BY uploaded_at DESC",
            (current_user["id"],)
        )
        analyses = cursor.fetchall()
        
        # Calculate totals
        total_analyses = len(analyses)
        total_critical = sum(a["critical_count"] for a in analyses)
        total_warnings = sum(a["warning_count"] for a in analyses)
        
        # Get recent 10 analyses
        recent_analyses = []
        for analysis in analyses[:10]:
            recent_analyses.append({
                "id": analysis["id"],
                "filename": analysis["filename"],
                "uploaded_at": analysis["uploaded_at"],
                "critical_count": analysis["critical_count"],
                "warning_count": analysis["warning_count"],
                "passed_count": analysis["passed_count"],
                "total_files": analysis["total_files"]
            })
        
        return {
            "total_analyses": total_analyses,
            "total_critical": total_critical,
            "total_warnings": total_warnings,
            "member_since": current_user["created_at"],
            "recent_analyses": recent_analyses
        }

@app.get("/analyses/{analysis_id}")
async def get_analysis(
    analysis_id: int,
    current_user = Depends(get_current_user)
):
    """Get full analysis details by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM analyses WHERE id = ? AND user_id = ?",
            (analysis_id, current_user["id"])
        )
        analysis = cursor.fetchone()
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        return json.loads(analysis["issues_json"])

@app.delete("/analyses/{analysis_id}")
async def delete_analysis(
    analysis_id: int,
    current_user = Depends(get_current_user)
):
    """Delete an analysis by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM analyses WHERE id = ? AND user_id = ?",
            (analysis_id, current_user["id"])
        )
        analysis = cursor.fetchone()
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        cursor.execute(
            "DELETE FROM analyses WHERE id = ? AND user_id = ?",
            (analysis_id, current_user["id"])
        )
        conn.commit()
        
        return {"message": "Analysis deleted successfully"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
