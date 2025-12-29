@echo off
echo ==========================================
echo    🔍 ATTENDANCE TRACKER - IP FINDER
echo ==========================================
echo.
echo Finding your server IP addresses...
echo.

for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "ipv4"') do (
    for /f "tokens=*" %%b in ("%%a") do (
        echo   🌐 %%b
        echo      Access URL: http://%%b:8000
        echo.
    )
)

echo ==========================================
echo Share the IP address above with your team!
echo They can access: http://[IP_ADDRESS]:8000
echo ==========================================
pause
