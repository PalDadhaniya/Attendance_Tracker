@echo off
echo Starting Attendance Tracker Server...
echo.
echo Server will be accessible at:
echo - Local: http://localhost:8000
echo - Network: http://[YOUR_IP_ADDRESS]:8000
echo.
echo Press Ctrl+C to stop the server
echo.

cd /d %~dp0
python manage.py runserver 0.0.0.0:8000
