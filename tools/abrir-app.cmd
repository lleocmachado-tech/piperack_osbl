@echo off
title COMBIO - Abrir aplicativo
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\Iniciar.ps1" -AbrirNavegador
if errorlevel 1 (
    echo.
    echo Nao foi possivel abrir o aplicativo. Veja a mensagem acima.
    pause
)
