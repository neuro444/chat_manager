Start-Job -Name "ChatManagerServer" -ScriptBlock {
    Set-Location "C:\Users\maxyo\OneDrive\Documents\restaurant-workspace\chat_manager"
    python -m uvicorn api:app --host 127.0.0.1 --port 8000
}

Write-Host "Waiting 5 seconds for server to start..."
Start-Sleep -Seconds 5

Write-Host "Running tests..."
python test_3_orders.py

Write-Host "Stopping server..."
Stop-Job -Name "ChatManagerServer"
Remove-Job -Name "ChatManagerServer"
