# Issue Prediction - Catch deployment errors before they happen

A web application that analyzes your project files and catches deployment errors before they reach production.

## Features

- **Upload & Analyze**: Upload your project as a zip file for comprehensive analysis
- **Real Execution**: Runs actual deployment commands in isolated Docker containers
- **AI-Powered Analysis**: Uses Groq AI to explain errors in plain English
- **Multi-Language Support**: Supports Python, Node.js, Docker, and docker-compose projects
- **Environment Variable Detection**: Identifies missing environment variables
- **Cross-File Analysis**: Detects configuration mismatches across files

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Groq API key (for AI analysis)

### Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd issuse_prediction
   ```

2. **Set up environment variables**:
   ```bash
   # Create .env file for docker-compose
   echo "GROQ_API_KEY=your_api_key_here" > .env
   ```

3. **Build and run the application**:
   ```bash
   docker-compose up --build
   ```

4. **Access the application**:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000

### Try with Sample Project

A sample project with intentional errors is included in the `sample_project/` directory:

1. **Create a zip file**:
   ```bash
   cd sample_project
   zip -r ../sample_project.zip .
   cd ..
   ```

2. **Upload the zip file** to the web interface at http://localhost:3000

## Supported Files

The application analyzes the following files:

- `requirements.txt` - Python dependencies
- `package.json` - Node.js dependencies
- `Dockerfile` - Docker build configuration
- `docker-compose.yml` - Docker Compose configuration
- `.env` - Environment variables

## What Gets Analyzed

### Python Projects
- `pip install --dry-run` - Checks dependency installation
- `pip check` - Verifies dependency conflicts

### Node.js Projects
- `npm install --dry-run` - Checks dependency installation
- `npm ls` - Lists installed packages

### Docker Projects
- `docker build . --no-cache` - Validates Dockerfile syntax and build process

### Docker Compose Projects
- `docker-compose config` - Validates compose file syntax

### Environment Variables
- Scans `.py` and `.js` files for environment variable usage
- Compares with `.env` file to detect missing variables
- Reports configuration mismatches

## API Endpoints

### POST /upload
Upload and analyze a zip file.

**Request**: Multipart form data with file field
**Response**: JSON with analysis results including:
- Files detected
- Commands executed
- Raw output
- Issues found (with AI explanations)

### GET /health
Health check endpoint.

## Security Features

- **Isolated Execution**: All user code runs in isolated Docker containers
- **Resource Limits**: Containers have memory (512MB) and CPU (0.5 cores) limits
- **Network Isolation**: No internet access during analysis
- **Read-Only Mounts**: User files are mounted read-only
- **Auto-Cleanup**: Containers and temporary files are automatically removed

## Development

### Backend Development

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend Development

The frontend is a single HTML file. Simply open `frontend/index.html` in a browser or serve it with any web server.

## Sample Project Errors

The included `sample_project/` contains these intentional errors:

1. **Non-existent package** in requirements.txt
2. **Missing environment variables** (DB_PASSWORD, REDIS_URL)
3. **Port mismatch** in Dockerfile vs docker-compose
4. **Missing POSTGRES_PASSWORD** in docker-compose

These demonstrate the types of issues DeployCheck can detect and explain.

## Troubleshooting

### Docker Issues
- Ensure Docker is running and accessible
- Check that `/var/run/docker.sock` is accessible to the backend container

### API Key Issues
- Verify GROQ_API_KEY is set correctly
- Get free API key from console.groq.com

### Frontend Issues
- Ensure backend is running on port 8000
- Check browser console for JavaScript errors


