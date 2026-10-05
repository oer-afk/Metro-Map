@echo off
rem Metro learning map launcher: double-click to start a local server and open the browser.
rem To stop the server, close the "metro-map server" window (minimized on the taskbar).
setlocal
set PORT=8765
set URL=http://localhost:%PORT%/

rem If the server is already running, just open the browser.
curl.exe -s -o nul --max-time 2 %URL% && goto open

set PY=
where python >nul 2>&1 && set PY=python
if not defined PY where py >nul 2>&1 && set PY=py
if not defined PY (
  echo Python was not found. Install Python 3 from https://www.python.org/ and try again.
  pause
  exit /b 1
)

start "metro-map server" /min %PY% -m http.server %PORT% --bind 127.0.0.1 --directory "%~dp0site"

rem Wait until the server answers (about 15 seconds at most).
for /l %%i in (1,1,15) do (
  ping -n 2 127.0.0.1 >nul
  curl.exe -s -o nul --max-time 2 %URL% && goto open
)
echo The server did not start. Check the "metro-map server" window for errors.
echo (Another program may be using port %PORT%.)
pause
exit /b 1

:open
start "" "%URL%"
endlocal
