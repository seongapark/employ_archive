# 수집을 이 PC(한국)에서 돌리고 결과만 GitHub 에 올린다.
#
# KEIS 는 해외 IP 를 막는다(2026-09-15 확인: 55개국에서 접속 시도, 성공 0).
# 기재부도 같은 증상이다. GitHub 러너는 전부 해외라 수집이 원리적으로 안 된다.
# 그래서 수집만 국내에서 돌린다. 배포(pages)와 질의응답 동기화(D1)는 예전처럼
# GitHub 이 push 를 받아서 한다 — 그쪽은 해외에서도 되는 일이다.
#
# 손으로 돌릴 때:
#   powershell -ExecutionPolicy Bypass -File "C:\Users\seong\Desktop\고용데이터아카이브\collect-local.ps1"
#
# 수집이 실패해도 push 까지 간다. 한 게시판이 죽은 날에도 나머지 기관의
# 그날치는 남겨야 하기 때문이다. 무엇이 실패했는지는 마지막 줄과 logs\ 에 남는다.
#
# -Catchup 은 작업 스케줄러 전용이다. 11:00 말고도 로그온·잠금 해제·절전 복귀 때
# 불리는데, 그때는 "11시가 지났고 오늘 아직 안 돌았을 때"만 돈다.
# 2026-09-24 에 PC 가 05:52~19:31 최대절전이라 11:00 을 놓쳤고, StartWhenAvailable
# 이 켜져 있었는데도 복귀 뒤 따라잡지 않았다. 그래서 복귀 신호를 직접 잡는다.
# 손으로 돌릴 때는 이 스위치 없이 부르면 언제든 돈다.
param([switch]$Catchup)

$repo = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $repo

# 오늘 돈 날짜는 logs\ 에 둔다(저장소에 안 올라간다). last_run.json 은 --dry-run
# 도 오늘로 찍으므로 판단 근거로 못 쓴다.
$doneFile = Join-Path $repo "logs\last-run-date.txt"
$today = Get-Date -Format "yyyy-MM-dd"
if ($Catchup) {
    if ((Get-Date).Hour -lt 11) { exit 0 }
    if ((Test-Path $doneFile) -and ((Get-Content $doneFile -Raw).Trim() -eq $today)) { exit 0 }
}

# 파이썬은 실측한 경로를 먼저 본다. 스토어 스텁(WindowsApps)이 가로채면
# 패키지가 하나도 안 보이기 때문이다. 그 경로가 없어지면 PATH 로 물러선다.
$python = "C:\Users\seong\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

# forecast 가 KEIS 고용동향브리프 PDF 를 OCR 할 때 쓴다. 설치 관리자가 PATH 에
# 넣지 않는 경우가 있어 여기서 붙인다.
$tesseract = "C:\Program Files\Tesseract-OCR"
if (Test-Path $tesseract) { $env:PATH = "$env:PATH;$tesseract" }

$env:PYTHONIOENCODING = "utf-8"
# 추천 판정은 구독(`claude -p`)으로 돈다. API 키로 도는 길은 코드에서 지웠다.
$env:JUDGE_PROVIDER = "cli"
# 고용동향의 사업체노동력조사(est)는 KOSIS 열쇠가 있어야 받는다. 저장소에 두지
# 않는다 — 이 PC 의 ~\.config\kosis\apikey.txt 에서 읽는다. 없으면 est 하나만
# 빠지고 나머지는 그대로 돈다. 빠진 것은 회차 판정이 잡는다.
if (-not $env:KOSIS_API_KEY) {
    $keyFile = Join-Path $env:USERPROFILE ".config\kosis\apikey.txt"
    if (Test-Path $keyFile) {
        $env:KOSIS_API_KEY = (Get-Content $keyFile -Raw).Trim()
    } else {
        Write-Host "!! KOSIS 열쇠 파일이 없다($keyFile) — 사업체노동력조사는 빠진다"
    }
}
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 도는 동안 잠들지 않게 붙잡는다.
#
# 2026-09-16 11:36 회차가 대기 모드(Modern Standby) 안에서 시작했다. git pull 만
# 하고 94분을 멈춰 있다가, 사람이 노트북을 연 13:10:33 에야 이어졌다. 깨어난 직후
# 6초 동안은 무선이 다시 붙기 전이라 이름 해석이 안 된다 — 그 창에 걸린 첫 두
# 게시판(KLI 연구보고서·노동리뷰)이 재시도 세 번을 다 쓰고 빈 채로 끝났다.
# 사이트가 막은 것이 아니다. 재시도 간격을 늘려 덮을 일도 아니다 — 수집이 대기
# 모드 안에서 도는 것 자체가 틀렸다.
#
# ES_SYSTEM_REQUIRED 만 건다. 화면은 꺼져도 된다 — 깨어 있어야 하는 것은 회선이다.
Add-Type -Namespace Win32 -Name Power -MemberDefinition @"
[DllImport("kernel32.dll", SetLastError = true)]
public static extern uint SetThreadExecutionState(uint esFlags);
"@
# PowerShell 5.1 은 0x80000000 을 음수 int 로 읽는다. L 을 붙여 long 으로 받은 뒤 uint32 로 옮긴다.
$ES_CONTINUOUS = [uint32]0x80000000L
$ES_SYSTEM_REQUIRED = [uint32]0x00000001
if ([Win32.Power]::SetThreadExecutionState([uint32]($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)) -eq 0) {
    Write-Host "!! 깨어 있기 요청 실패 — 이 회차는 잠자기에 끊길 수 있다"
}

$logDir = Join-Path $repo "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("collect-" + (Get-Date -Format "yyyyMMdd-HHmm") + ".log")
Start-Transcript -Path $log | Out-Null
Write-Host ("시작 " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))

$failed = @()

function Step($name, $argv) {
    Write-Host ""
    Write-Host ("=== " + $name + " ===")
    & $python @argv
    if ($LASTEXITCODE -ne 0) {
        $script:failed += $name
        Write-Host ("!! " + $name + " 실패 (exit " + $LASTEXITCODE + ")")
    }
}

# 남이(=GitHub 워크플로나 다른 PC) 올린 것을 먼저 받는다. --autostash 는
# 작업 중이던 수정을 잠시 치워 뒀다 되돌린다 — 저장소가 지저분해도 멈추지 않는다.
Write-Host "=== git pull ==="
git pull --rebase --autostash origin main

Step "reports 수집"     @("-m", "domains.reports.pipeline.collect")
Step "reports 초록"     @("-m", "domains.reports.pipeline.enrich")
Step "reports 빌드"     @("-m", "domains.reports.pipeline.build")
Step "reports 추천판정" @("-m", "domains.reports.pipeline.recommend")
Step "forecast 수집"    @("-m", "domains.forecast.pipeline.collect")
Step "employment 수집"  @("-m", "domains.employment.pipeline.collect")

# **수집이 실패해도 여기까지 온다.** 부분 성공을 버리지 않는다.
Write-Host ""
Write-Host "=== push ==="
git add domains/reports/data/ domains/reports/sources/ domains/forecast/data/ domains/employment/data/
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m ("data: local collect " + (Get-Date -Format "yyyy-MM-dd"))
    # 커밋 뒤에 다시 받는다. 수집이 도는 사이 GitHub 쪽(보도자료·고용동향)이
    # 올렸을 수 있다. 충돌하면 방금 수집한 쪽을 쓴다 — 담기는 폴더가 서로 달라
    # 남의 것을 덮지 않는다.
    git pull --rebase -X theirs --autostash origin main
    git push
    if ($LASTEXITCODE -ne 0) { $failed += "push" }
} else {
    Write-Host "올릴 변경 없음"
}

# 무엇이 비었는지 사람 말로 남기고, **그 판정을 회차 성패에 넣는다.**
#
# 수집 단계는 게시판이 죽어도 exit 0 으로 끝난다 — 한 곳이 막힌 날에도 나머지를
# 남기려고 그렇게 만들었다. 그래서 여기서 판정을 받지 않으면 마지막 줄이 거짓말을
# 한다. 2026-09-16 11:36 회차가 KLI 두 게시판을 빈 채로 두고 "전부 성공" 으로
# 끝났고, 작업 스케줄러에도 0 으로 남았다.
#
# 초록 결측률은 경고일 뿐 실패가 아니다 — 같은 목록을 찍고도 OK 로 끝난다.
# 오래 가는 장애는 KNOWN_DOWN 으로 기한을 붙여 유예한다.
Write-Host ""
Write-Host "=== 회차 판정 ==="
& $python -m domains.reports.pipeline.check_run
if ($LASTEXITCODE -ne 0) { $failed += "reports 회차 판정" }
& $python -m domains.forecast.pipeline.check_run
if ($LASTEXITCODE -ne 0) { $failed += "forecast 회차 판정" }
& $python -m domains.employment.pipeline.check_run
if ($LASTEXITCODE -ne 0) { $failed += "employment 회차 판정" }

Write-Host ""
if ($failed.Count -eq 0) {
    Write-Host "전부 성공"
} else {
    Write-Host ("실패한 단계: " + ($failed -join ", "))
}
Write-Host ("로그: " + $log)

# 끝까지 온 회차만 오늘 돈 것으로 친다. 실패가 있어도 찍는다 — 안 그러면 잠금을
# 풀 때마다 같은 날 회차가 되풀이된다. 도중에 끊긴 회차는 여기까지 못 와서 안 찍힌다.
Set-Content -Path $doneFile -Value $today -Encoding ascii

# 로그는 30회분만 둔다.
Get-ChildItem $logDir -Filter "collect-*.log" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 30 |
    Remove-Item -Force -ErrorAction SilentlyContinue

# 붙잡아 둔 것을 놓는다. 이 뒤로는 평소대로 잠들어도 된다.
[void][Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS)

Stop-Transcript | Out-Null
exit $failed.Count
