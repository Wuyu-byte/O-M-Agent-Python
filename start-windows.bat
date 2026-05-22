@echo off
setlocal
cd /d "%~dp0"

echo ====================================
echo Starting SuperBizAgent services
echo ====================================
echo.

echo [1/8] Checking package manager...
where uv >nul 2>&1
if errorlevel 1 (
    echo [INFO] uv not found, pip fallback will be used.
    set "USE_UV=0"
) else (
    echo [OK] uv found.
    set "USE_UV=1"
)
echo.

echo [2/8] Checking Python version config...
if exist .python-version (
    set /p PYTHON_VERSION=<.python-version
    call echo [INFO] .python-version=%%PYTHON_VERSION%%
    findstr /C:"3.10" .python-version >nul
    if not errorlevel 1 (
        echo [WARN] Python 3.10 is not supported by this project. Updating .python-version to 3.13...
        echo 3.13> .python-version
    )
) else (
    echo [INFO] Creating .python-version...
    echo 3.13> .python-version
)
echo.

echo [3/8] Creating or syncing virtual environment...
if exist .venv\Scripts\python.exe (
    echo [INFO] Virtual environment already exists.
    if "%USE_UV%"=="1" (
        uv sync
        if errorlevel 1 (
            echo [WARN] uv sync failed, falling back to pip install.
            .venv\Scripts\python.exe -m pip install -e .
        )
    ) else (
        .venv\Scripts\python.exe -m pip install -e .
    )
) else (
    if "%USE_UV%"=="1" (
        echo [INFO] Creating environment with uv sync...
        uv sync
        if not errorlevel 1 goto :venv_ready
        echo [WARN] uv sync failed, falling back to python -m venv.
    )

    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment. Please install Python 3.11+.
        pause
        exit /b 1
    )
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -e .
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
)

:venv_ready
set "PYTHON_CMD=.venv\Scripts\python.exe"
if not exist logs mkdir logs
if not exist arxiv-papers mkdir arxiv-papers
echo [OK] Python environment is ready.
echo.

echo [4/8] Starting Milvus vector database...
docker ps --format "{{.Names}}" | findstr /C:"python-agent-milvus-standalone" >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Milvus container is already running.
) else (
    docker compose -f vector-database.yml up -d
    if errorlevel 1 (
        echo [ERROR] Docker compose failed. Please make sure Docker Desktop is running.
        pause
        exit /b 1
    )
    echo [INFO] Waiting for Milvus to start...
    timeout /t 10 /nobreak >nul
)
echo.

echo [5/8] Starting CLS MCP server...
start "CLS MCP Server" /min "%PYTHON_CMD%" "mcp_servers\cls_server.py"
timeout /t 2 /nobreak >nul
echo [OK] CLS MCP server started.
echo.

echo [6/8] Starting Monitor MCP server...
start "Monitor MCP Server" /min "%PYTHON_CMD%" "mcp_servers\monitor_server.py"
timeout /t 2 /nobreak >nul
echo [OK] Monitor MCP server started.
echo.

echo [7/8] Starting FastAPI server...
start "SuperBizAgent API" "%PYTHON_CMD%" -m uvicorn app.main:app --host 0.0.0.0 --port 9900
echo [INFO] Waiting for FastAPI to start...
timeout /t 15 /nobreak >nul
echo.

echo [8/8] Checking API health and uploading aiops docs...
curl -s http://localhost:9900/health >nul 2>&1
if errorlevel 1 (
    echo [WARN] FastAPI may still be starting. Open http://localhost:9900 after a moment.
) else (
    echo [OK] FastAPI is healthy.
    for %%f in (aiops-docs\*.md) do (
        echo Uploading %%~nxf
        curl -s -X POST http://localhost:9900/api/upload -F "file=@%%f" >nul 2>&1
    )
    echo [OK] Docs upload finished.
)

echo.
echo ====================================
echo Services started
echo ====================================
echo Web UI: http://localhost:9900
echo API docs: http://localhost:9900/docs
echo Attu: http://localhost:8000
echo.
echo Stop services: stop-windows.bat
echo ====================================
pause
