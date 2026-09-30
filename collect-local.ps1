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
# 하루 두 번(10시·15시) 돈다(2026-09-30 사용자 결정, 전에는 11시 한 번). 15시 회차는
# 정오에 나오는 고용행정통계·사업체노동력조사·KDI 전망을 그날 받으려는 것이다.
#
# -Catchup 은 작업 스케줄러 전용이다. 10:00·15:00 말고도 로그온·잠금 해제·절전 복귀
# 때 불리는데, 그때는 "지금 시각의 회차(10시 또는 15시)를 아직 안 돌았을 때"만 돈다.
# 2026-09-24 에 PC 가 05:52~19:31 최대절전이라 11:00 을 놓쳤고, StartWhenAvailable
# 이 켜져 있었는데도 복귀 뒤 따라잡지 않았다. 그래서 복귀 신호를 직접 잡는다.
# 손으로 돌릴 때는 이 스위치 없이 부르면 언제든 돈다.
#
# -Due 는 '발표일 재수집' 작업 전용이다(10~23시 매시간). 고용전망 기관 중 지금이
# 발표 시각을 지난 발표일인 곳만 다시 수집한다 — OECD 는 17시, IMF 는 22시에
# 내므로 정기 수집으로는 그날 반영이 안 된다. 어느 기관이 언제인지는
# domains/forecast/pipeline/calendar.py 가 정한다. 볼 기관이 없으면 로그도 안 남긴다.
param([switch]$Catchup, [switch]$Due)

$repo = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $repo

# 마지막으로 돈 회차("2026-09-30 15")는 logs\ 에 둔다(저장소에 안 올라간다).
# last_run.json 은 --dry-run 도 오늘로 찍으므로 판단 근거로 못 쓴다.
# 문자열 비교로 순서가 맞다: "2026-09-30 10" < "2026-09-30 15" < "2026-10-01 10".
# 예전 형식("2026-09-30")도 그날 두 회차보다 앞으로 읽혀 문제없다.
$doneFile = Join-Path $repo "logs\last-run-date.txt"
$today = Get-Date -Format "yyyy-MM-dd"
$slotHours = @(10, 15)
$slotHour = @($slotHours | Where-Object { $_ -le (Get-Date).Hour } | Select-Object -Last 1)
$slot = if ($slotHour.Count) { "{0} {1:D2}" -f $today, $slotHour[0] } else { "$today 00" }
if ($Catchup) {
    if (-not $slotHour.Count) { exit 0 }
    if ((Test-Path $doneFile) -and ((Get-Content $doneFile -Raw).Trim() -ge $slot)) { exit 0 }
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

# 매일 수집과 발표일 재수집이 같은 저장소를 동시에 만지지 않게 한다. 재수집은
# 자리가 차 있으면 이번 시각을 건너뛰고(한 시간 뒤 또 온다), 매일 수집은 기다린다.
$mutex = New-Object System.Threading.Mutex($false, "Local\employ-archive-collect")
try {
    $owned = $mutex.WaitOne($(if ($Due) { 0 } else { [TimeSpan]::FromMinutes(30) }))
} catch [System.Threading.AbandonedMutexException] {
    $owned = $true  # 앞 회차가 도중에 죽었다 — 넘겨받는다
}
if (-not $owned) {
    [void][Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS)
    exit 0
}

$logDir = Join-Path $repo "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# 네이티브 명령(파이썬·git)의 출력을 기록에 남긴다. Start-Transcript 는 PowerShell 이
# 화면에 쓰는 것만 담아서, `& $python ...` 를 그대로 부르면 로그에 단계 제목만 남고
# 무엇이 왜 실패했는지가 빠졌다(2026-09-30 까지의 로그가 전부 그랬다). 파이프라인으로
# 한 번 받아 Out-Host 로 다시 쓰면 기록된다. 알림에 실을 오류 줄도 여기서 모은다.
$script:errorLines = @()
function Native([scriptblock]$command) {
    $lines = & $command 2>&1 | ForEach-Object { "$_" }
    $code = $LASTEXITCODE
    $lines | Out-Host
    $script:errorLines += @($lines | Where-Object { $_ -match '^(::error::|!! )' })
    return $code
}

# 실패하면 GitHub 이슈로 알린다(작업 스케줄러의 종료 코드는 아무도 안 본다 —
# BOK 2025년 11월판이 그렇게 넉 달 빠져 있었다). 열린 알림이 있으면 댓글을 달고,
# 매일 수집이 전부 성공하면 닫는다. 저장소가 공개라 로컬 경로는 싣지 않는다 —
# 오류 줄은 어차피 공개로 커밋되는 last_run.json 과 같은 내용이다.
function Update-Alert([string[]]$problems, [switch]$MayClose) {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        Write-Host "!! gh 가 없어 실패 알림을 못 보낸다"
        return
    }
    $label = "collect-alert"
    $open = gh issue list --label $label --state open --json number --jq ".[0].number" 2>$null
    if ($problems.Count -gt 0) {
        $details = @($script:errorLines | Select-Object -Unique | Select-Object -First 30)
        $body = "**" + (Get-Date -Format "yyyy-MM-dd HH:mm") + " 로컬 수집에서 실패한 단계**`n`n" +
                (($problems | ForEach-Object { "- $_" }) -join "`n") + "`n`n" +
                $(if ($details.Count) { "``````text`n" + ($details -join "`n") + "`n``````" } else { "" })
        $tmp = [IO.Path]::GetTempFileName()
        [IO.File]::WriteAllText($tmp, $body, (New-Object Text.UTF8Encoding $false))
        if ($open) {
            gh issue comment $open --body-file $tmp *> $null
        } else {
            gh label create $label --color d73a4a --description "로컬 수집이 실패하면 자동으로 열리고, 전부 성공하면 닫힌다" *> $null
            gh issue create --title "로컬 수집 실패" --label $label --body-file $tmp *> $null
        }
        if ($LASTEXITCODE -ne 0) { Write-Host "!! 실패 알림 이슈를 올리지 못했다" }
        Remove-Item $tmp -ErrorAction SilentlyContinue
    } elseif ($open -and $MayClose) {
        gh issue close $open --comment ((Get-Date -Format "yyyy-MM-dd HH:mm") + " 매일 수집이 전부 성공했다 — 자동으로 닫는다.") *> $null
    }
}

if ($Due) {
    git pull --rebase --autostash origin main *> $null
    $out = & $python -m domains.forecast.pipeline.collect --due 2>&1 | Out-String
    $code = $LASTEXITCODE
    if ($out -notmatch "지금 볼 기관 없음") {
        git add domains/forecast/data/
        git diff --cached --quiet
        if ($LASTEXITCODE -ne 0) {
            git commit -m ("data: release-day collect " + (Get-Date -Format "yyyy-MM-dd HH:mm")) | Out-Null
            git pull --rebase -X theirs --autostash origin main *> $null
            git push *> $null
            if ($LASTEXITCODE -ne 0) { $out += "`n!! push 실패"; $code = 1 }
        }
        $out += "`n" + (& $python -m domains.forecast.pipeline.check_run 2>&1 | Out-String)
        if ($LASTEXITCODE -ne 0) { $code = 1 }
        if ($code -ne 0) {
            $script:errorLines = @($out -split "`r?`n" | Where-Object { $_ -match '^(::error::|!! )' })
            Update-Alert @("발표일 재수집")
        }
        Set-Content -Path (Join-Path $logDir ("due-" + (Get-Date -Format "yyyyMMdd-HHmm") + ".log")) -Value $out -Encoding utf8
        Get-ChildItem $logDir -Filter "due-*.log" | Sort-Object LastWriteTime -Descending |
            Select-Object -Skip 60 | Remove-Item -Force -ErrorAction SilentlyContinue
    }
    [void][Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS)
    $mutex.ReleaseMutex()
    exit $code
}

$log = Join-Path $logDir ("collect-" + (Get-Date -Format "yyyyMMdd-HHmm") + ".log")
Start-Transcript -Path $log | Out-Null
Write-Host ("시작 " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))

$failed = @()

function Step($name, $argv) {
    Write-Host ""
    Write-Host ("=== " + $name + " ===")
    $code = Native { & $python @argv }
    if ($code -ne 0) {
        $script:failed += $name
        Write-Host ("!! " + $name + " 실패 (exit " + $code + ")")
    }
}

# 남이(=GitHub 워크플로나 다른 PC) 올린 것을 먼저 받는다. --autostash 는
# 작업 중이던 수정을 잠시 치워 뒀다 되돌린다 — 저장소가 지저분해도 멈추지 않는다.
Write-Host "=== git pull ==="
[void](Native { git pull --rebase --autostash origin main })

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
    [void](Native { git commit -m ("data: local collect " + (Get-Date -Format "yyyy-MM-dd")) })
    # 커밋 뒤에 다시 받는다. 수집이 도는 사이 GitHub 쪽(보도자료·고용동향)이
    # 올렸을 수 있다. 충돌하면 방금 수집한 쪽을 쓴다 — 담기는 폴더가 서로 달라
    # 남의 것을 덮지 않는다.
    [void](Native { git pull --rebase -X theirs --autostash origin main })
    if ((Native { git push }) -ne 0) { $failed += "push" }
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
if ((Native { & $python -m domains.reports.pipeline.check_run }) -ne 0) { $failed += "reports 회차 판정" }
if ((Native { & $python -m domains.forecast.pipeline.check_run }) -ne 0) { $failed += "forecast 회차 판정" }
if ((Native { & $python -m domains.employment.pipeline.check_run }) -ne 0) { $failed += "employment 회차 판정" }

Write-Host ""
if ($failed.Count -eq 0) {
    Write-Host "전부 성공"
} else {
    Write-Host ("실패한 단계: " + ($failed -join ", "))
}
Write-Host ("로그: " + $log)
Update-Alert $failed -MayClose

# 끝까지 온 회차만 오늘 돈 것으로 친다. 실패가 있어도 찍는다 — 안 그러면 잠금을
# 풀 때마다 같은 날 회차가 되풀이된다. 도중에 끊긴 회차는 여기까지 못 와서 안 찍힌다.
Set-Content -Path $doneFile -Value $slot -Encoding ascii

# 로그는 30회분만 둔다.
Get-ChildItem $logDir -Filter "collect-*.log" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 30 |
    Remove-Item -Force -ErrorAction SilentlyContinue

# 붙잡아 둔 것을 놓는다. 이 뒤로는 평소대로 잠들어도 된다.
[void][Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS)

Stop-Transcript | Out-Null
$mutex.ReleaseMutex()
exit $failed.Count
