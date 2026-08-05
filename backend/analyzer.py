import os
import json
from typing import List, Dict, Any
from groq import Groq

class Analyzer:
    def __init__(self):
        self.client = None
        api_key = os.getenv('GROQ_API_KEY')
        if api_key:
            self.client = Groq(api_key=api_key)
    
    def analyze_command_result(self, command: str, exit_code: int, stdout: str, stderr: str) -> Dict[str, Any]:
        """Analyze a single command result using Groq API"""
        if not self.client:
            # Skip AI analysis if API is not available, don't return an error
            return None
        
        # Only analyze if there's an error (non-zero exit code or stderr)
        if exit_code == 0 and not stderr.strip():
            return None
        
        # Prepare the error output (limit to 2000 chars)
        error_output = stderr if stderr.strip() else stdout
        error_output = error_output[:2000]
        
        prompt = f"""You are a deployment error analyzer. A developer tried to deploy their project and got this error. Explain what went wrong in 2-3 plain English sentences that a junior developer can understand. Then give one specific fix.

Command that was run: {command}
Exit code: {exit_code}
Error output:
{error_output}

Respond in this exact JSON format:
{{
  "severity": "critical|warning|info",
  "title": "short title of the issue",
  "explanation": "plain english explanation",
  "fix": "exact fix they should apply",
  "file": "which file to fix, or null"
}}"""

        try:
            response = self.client.chat.completions.create(
                model="moonshotai/kimi-k2-instruct",
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            response_text = response.choices[0].message.content
            # Extract JSON from response
            try:
                # Find JSON in the response
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}') + 1
                if start_idx != -1 and end_idx > start_idx:
                    json_str = response_text[start_idx:end_idx]
                    return json.loads(json_str)
                else:
                    raise ValueError("No JSON found in response")
            except json.JSONDecodeError as e:
                return {
                    "error": f"Failed to parse Claude response: {e}",
                    "severity": "warning",
                    "title": "Analysis Error",
                    "explanation": "Could not analyze the error automatically",
                    "fix": "Review the raw error output manually",
                    "file": None
                }
                
        except Exception as e:
            return {
                "error": f"Claude API error: {e}",
                "severity": "warning",
                "title": "API Error",
                "explanation": "Failed to analyze error with AI",
                "fix": "Check API configuration and try again",
                "file": None
            }
    
    def analyze_cross_file_issues(self, command_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Analyze all command outputs for cross-file conflicts"""
        if not self.client:
            return []
        
        # Combine all outputs
        all_outputs = []
        for result in command_results:
            output_section = f"Command: {result['command']}\n"
            output_section += f"Exit Code: {result['exit_code']}\n"
            if result['stdout'].strip():
                output_section += f"STDOUT:\n{result['stdout'][:1000]}\n"
            if result['stderr'].strip():
                output_section += f"STDERR:\n{result['stderr'][:1000]}\n"
            output_section += "---\n"
            all_outputs.append(output_section)
        
        combined_output = "\n".join(all_outputs)
        
        prompt = f"""You are a deployment analyzer. Look at these deployment command outputs from a project. Identify any cross-file conflicts or configuration mismatches that would cause deployment to fail. Only report real issues, not general advice.

{combined_output}

Return a JSON array of issues in this format:
[{{"severity": "critical|warning|info", "title": "short title", "explanation": "explanation", "fix": "fix", "file": "filename or null"}}]
Return empty array [] if no cross-file issues found."""

        try:
            response = self.client.chat.completions.create(
                model="moonshotai/kimi-k2-instruct",
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            response_text = response.choices[0].message.content
            # Extract JSON array from response
            try:
                start_idx = response_text.find('[')
                end_idx = response_text.rfind(']') + 1
                if start_idx != -1 and end_idx > start_idx:
                    json_str = response_text[start_idx:end_idx]
                    return json.loads(json_str)
                else:
                    return []
            except json.JSONDecodeError:
                return []
                
        except Exception as e:
            print(f"Cross-file analysis error: {e}")
            return []
    
    def analyze_env_var_mismatch(self, env_vars: Dict[str, str], env_usage: Dict[str, List[Dict[str, str]]]) -> List[Dict[str, Any]]:
        """Analyze environment variable mismatches"""
        issues = []
        
        # Check Python env usage
        for usage in env_usage.get('python', []):
            var_name = usage['var']
            if var_name not in env_vars:
                issues.append({
                    "severity": "warning",
                    "title": f"Missing Environment Variable: {var_name}",
                    "explanation": f"The file {usage['file']} uses environment variable '{var_name}' but it's not defined in .env file",
                    "fix": f"Add '{var_name}=your_value_here' to your .env file",
                    "file": usage['file']
                })
        
        # Check JavaScript env usage
        for usage in env_usage.get('javascript', []):
            var_name = usage['var']
            if var_name not in env_vars:
                issues.append({
                    "severity": "warning",
                    "title": f"Missing Environment Variable: {var_name}",
                    "explanation": f"The file {usage['file']} uses environment variable '{var_name}' but it's not defined in .env file",
                    "fix": f"Add '{var_name}=your_value_here' to your .env file",
                    "file": usage['file']
                })
        
        return issues
