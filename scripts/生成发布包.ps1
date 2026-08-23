[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('部署包', '修复包')]
  [string]$类型,

  [Parameter(Mandatory = $true)]
  [ValidateNotNullOrEmpty()]
  [string]$名称,

  [string]$版本 = (Get-Date -Format 'yyyyMMdd-HHmm'),
  [string]$说明 = '未填写',
  [string]$基线 = 'origin/main',
  [switch]$同步GitHub
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw '未找到 Git。'
}

$safeName = $名称 -replace '[\\/:*?"<>|\s]+', '-'
$safeVersion = $版本 -replace '[\\/:*?"<>|\s]+', '-'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$branchPrefix = if ($类型 -eq '部署包') { '部署' } else { '修复' }
$branchName = "$branchPrefix/$safeName-$safeVersion"
$category = Join-Path $repoRoot "发布包/$类型"
$packageName = "$safeName-$safeVersion"
$stageDir = Join-Path $env:TEMP "CAET-$packageName-$stamp"
$zipPath = Join-Path $category "$packageName.zip"
$notePath = Join-Path $category "$packageName-说明.md"

New-Item -ItemType Directory -Force -Path $category, $stageDir | Out-Null

try {
  $currentBranch = (git branch --show-current).Trim()
  if (-not $currentBranch) { throw '当前处于 detached HEAD，无法创建发布分支。' }

  $existing = git branch --list $branchName
  if ($existing) { throw "分支已存在：$branchName，请更换名称或版本。" }
  git switch -c $branchName
  if ($LASTEXITCODE -ne 0) { throw '创建中文分支失败。' }

  if ($类型 -eq '部署包') {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw '前端构建失败。' }

    Copy-Item -Recurse -Force -LiteralPath (Join-Path $repoRoot 'dist') -Destination $stageDir
    @('Dockerfile', 'docker-compose.yml', 'nginx.caet.conf', '.env.example', 'README.md') |
      ForEach-Object {
        $source = Join-Path $repoRoot $_
        if (Test-Path -LiteralPath $source) { Copy-Item -Force -LiteralPath $source -Destination $stageDir }
      }
    $backend = Join-Path $repoRoot 'caet-backend'
    if (Test-Path -LiteralPath $backend) {
      Copy-Item -Recurse -Force -LiteralPath $backend -Destination $stageDir
      Get-ChildItem -LiteralPath (Join-Path $stageDir 'caet-backend') -Directory -Recurse -Force |
        Where-Object Name -in @('node_modules', '__pycache__') |
        Remove-Item -Recurse -Force
    }
  }
  else {
    git rev-parse --verify $基线 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "找不到基线：$基线" }

    $changedFiles = @(
      git diff --name-only --diff-filter=ACMRT $基线
      git ls-files --others --exclude-standard
    ) | Where-Object { $_ -and -not $_.StartsWith('发布包/') } | Sort-Object -Unique

    if (-not $changedFiles) { throw "相对 $基线 没有可打包的变更。" }
    foreach ($relative in $changedFiles) {
      $source = Join-Path $repoRoot $relative
      if (Test-Path -LiteralPath $source -PathType Leaf) {
        $target = Join-Path $stageDir $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
        Copy-Item -Force -LiteralPath $source -Destination $target
      }
    }
    git diff --binary $基线 | Set-Content -LiteralPath (Join-Path $stageDir '修复内容.patch') -Encoding utf8
  }

  $commit = (git rev-parse --short HEAD).Trim()
  $note = @"
# $类型：$名称

- 版本：$版本
- 创建时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')
- Git 分支：$branchName
- 基准提交：$commit
- 说明：$说明

## 使用方式

$(if ($类型 -eq '部署包') { '解压后按 README.md 与部署配置执行；前端静态文件位于 dist。' } else { '压缩包保留原目录结构，同时附带 `修复内容.patch` 供审核或应用。' })
"@
  Set-Content -LiteralPath (Join-Path $stageDir '发布说明.md') -Value $note -Encoding utf8

  if (Test-Path -LiteralPath $zipPath) { Remove-Item -Force -LiteralPath $zipPath }
  Compress-Archive -Path (Join-Path $stageDir '*') -DestinationPath $zipPath -CompressionLevel Optimal
  $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash
  Set-Content -LiteralPath $notePath -Value ($note + "`n- SHA256：$hash") -Encoding utf8

  Write-Host "已生成：$zipPath" -ForegroundColor Green
  Write-Host "中文分支：$branchName" -ForegroundColor Green

  if ($同步GitHub) {
    git add -A
    git commit -m "$branchPrefix：$名称 $版本"
    if ($LASTEXITCODE -ne 0) { throw 'Git 提交失败。' }
    git push -u origin $branchName
    if ($LASTEXITCODE -ne 0) { throw '推送 GitHub 失败，请检查网络与 GitHub 凭据。' }
    Write-Host "已同步 GitHub：origin/$branchName" -ForegroundColor Cyan
  }
  else {
    Write-Host '尚未同步；确认包内容后，重新执行时添加 -同步GitHub。' -ForegroundColor Yellow
  }
}
finally {
  if (Test-Path -LiteralPath $stageDir) { Remove-Item -Recurse -Force -LiteralPath $stageDir }
}
