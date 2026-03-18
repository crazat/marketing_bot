@echo off
REM ================================================================
REM Marketing Bot - Database Backup Scheduler Setup
REM Windows Task Scheduler에 일일 백업 작업 등록
REM ================================================================

echo.
echo ================================================================
echo    Marketing Bot - Database Backup Scheduler Setup
echo ================================================================
echo.

REM 관리자 권한 확인
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] 관리자 권한이 필요합니다.
    echo         이 스크립트를 "관리자 권한으로 실행" 해주세요.
    echo.
    pause
    exit /b 1
)

REM 현재 디렉토리 저장
set PROJECT_DIR=%~dp0
set PROJECT_DIR=%PROJECT_DIR:~0,-1%
set PYTHON_PATH=python

REM Python 확인
%PYTHON_PATH% --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Python을 찾을 수 없습니다.
    echo         Python이 PATH에 설정되어 있는지 확인하세요.
    pause
    exit /b 1
)

echo [INFO] 프로젝트 경로: %PROJECT_DIR%
echo [INFO] Python 경로: %PYTHON_PATH%
echo.

REM 기존 작업 삭제 (있으면)
echo [INFO] 기존 스케줄 작업 확인 중...
schtasks /query /tn "MarketingBot_DailyBackup" >nul 2>&1
if %errorLevel% equ 0 (
    echo [INFO] 기존 작업 삭제 중...
    schtasks /delete /tn "MarketingBot_DailyBackup" /f
)

REM 새 작업 생성 (매일 02:00에 실행)
echo [INFO] 일일 백업 작업 등록 중...
echo        실행 시간: 매일 02:00
echo.

schtasks /create /tn "MarketingBot_DailyBackup" ^
    /tr "\"%PYTHON_PATH%\" \"%PROJECT_DIR%\db_backup.py\"" ^
    /sc DAILY ^
    /st 02:00 ^
    /ru "%USERNAME%" ^
    /rl HIGHEST ^
    /f

if %errorLevel% equ 0 (
    echo.
    echo ================================================================
    echo    [SUCCESS] 일일 백업 스케줄이 등록되었습니다!
    echo ================================================================
    echo.
    echo    작업 이름: MarketingBot_DailyBackup
    echo    실행 시간: 매일 오전 2시
    echo    백업 위치: %PROJECT_DIR%\db\backups\
    echo.
    echo    [관리 명령어]
    echo    - 작업 확인: schtasks /query /tn "MarketingBot_DailyBackup"
    echo    - 즉시 실행: schtasks /run /tn "MarketingBot_DailyBackup"
    echo    - 작업 삭제: schtasks /delete /tn "MarketingBot_DailyBackup" /f
    echo.
) else (
    echo.
    echo [ERROR] 스케줄 작업 등록에 실패했습니다.
    echo         오류 코드: %errorLevel%
    echo.
)

pause
