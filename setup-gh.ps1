$url = 'https://github.com/cli/cli/releases/download/v2.93.0/gh_2.93.0_windows_amd64.zip'
$zip = "$env:TEMP\gh.zip"
$extractDir = "$env:TEMP\gh-cli"

Write-Host "Downloading gh..."
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing

Write-Host "Extracting..."
Remove-Item -Path $extractDir -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -Path $zip -DestinationPath $extractDir -Force

$ghExe = Get-ChildItem -Path $extractDir -Recurse -Filter "gh.exe" | Select-Object -First 1 -ExpandProperty FullName
Write-Host "gh installed at: $ghExe"
& $ghExe --version

# 创建仓库
Write-Host "Creating GitHub repository..."
& $ghExe auth login
