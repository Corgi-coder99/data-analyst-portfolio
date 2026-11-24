<#
Record a scripted tour of the Power BI report as several short clips (nothing is recorded while waiting).
The narration is added later (assemble_video.py).

Run with Windows PowerShell 5.1 in a normal, interactive session:
  powershell.exe -File record_powerbi.ps1 -NarrDir <dir with m1..m7.wav> -OutDir <dir> -Ffmpeg <ffmpeg.exe>
Needs: Power BI Desktop open on TGV_Punctuality.pbip, data NOT loaded yet, maximised on a 1920x1080 screen.
Do not touch the mouse or keyboard while it runs: it drives the real cursor.
Output: OutDir\c01.mkv, c02.mkv ... and OutDir\timeline.json (clip lengths, scene start times in output time).
#>
param([string]$NarrDir, [string]$OutDir, [string]$Ffmpeg, [double]$IntroHold = 3.8)

Add-Type -AssemblyName System.Windows.Forms, System.Drawing, Microsoft.VisualBasic
$pbiHome = (Get-AppxPackage -Name Microsoft.MicrosoftPowerBIDesktop | Select-Object -First 1).InstallLocation
try { Add-Type -Path (Join-Path $pbiHome "bin\Microsoft.PowerBI.AdomdClient.dll") -ErrorAction Stop } catch { }   # a harmless partial-load warning is possible
if (-not ('Microsoft.AnalysisServices.AdomdClient.AdomdConnection' -as [type])) { throw 'Power BI ADOMD library not found: the "model loaded" check would never succeed.' }
Add-Type @"
using System; using System.Runtime.InteropServices;
public class WinIO {
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint x, uint y, uint d, UIntPtr e);
  [DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);
}
"@
[WinIO]::SetThreadExecutionState(0x80000003) | Out-Null   # keep the display and the system awake while this script runs
New-Item -ItemType Directory -Force $OutDir | Out-Null
Get-ChildItem $OutDir -Filter 'c*.mkv' -ErrorAction SilentlyContinue | ForEach-Object { $_.Delete() }
$ox = -8; $oy = -8   # the maximised window starts 8 px off-screen: image coords -> screen coords

function Dur($wav) {
    $o = & $Ffmpeg -hide_banner -i $wav 2>&1 | Select-String "Duration: (\d+):(\d+):([\d.]+)"
    $m = $o.Matches[0].Groups
    return [int]$m[1].Value * 3600 + [int]$m[2].Value * 60 + [double]$m[3].Value
}
function Activate { [Microsoft.VisualBasic.Interaction]::AppActivate((Get-Process PBIDesktop | Select-Object -First 1).Id); Start-Sleep -Milliseconds 800 }
function GlideTo($x, $y, $secs = 0.9) {
    $p = [System.Windows.Forms.Cursor]::Position; $sx = $x + $ox; $sy = $y + $oy
    $n = [int]($secs * 60)
    for ($i = 1; $i -le $n; $i++) {
        $t = $i / $n; $t = $t * $t * (3 - 2 * $t)
        [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point([int]($p.X + ($sx - $p.X) * $t), [int]($p.Y + ($sy - $p.Y) * $t))
        Start-Sleep -Milliseconds 16
    }
}
function Click($x, $y) {
    GlideTo $x $y 0.8; Start-Sleep -Milliseconds 250
    [WinIO]::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 90; [WinIO]::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero)
}
function Wiggle { $p = [System.Windows.Forms.Cursor]::Position; [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point(($p.X + 2), $p.Y); Start-Sleep -Milliseconds 50; [System.Windows.Forms.Cursor]::Position = $p }
function RegionHash($x, $y, $w, $h) {
    $bmp = New-Object System.Drawing.Bitmap($w, $h)
    $g = [System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($x + $ox, $y + $oy, 0, 0, (New-Object System.Drawing.Size($w, $h)))
    $ms = New-Object System.IO.MemoryStream; $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    $md5 = [System.Security.Cryptography.MD5]::Create(); $s = [BitConverter]::ToString($md5.ComputeHash($ms.ToArray()))
    $g.Dispose(); $bmp.Dispose(); return $s
}
function ModelLoaded {
    try {
        $c = (Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe'").CommandLine
        $ws = (($c -split '-s ')[1] -replace '"', '').Trim()
        $port = [int]((Get-Content (Join-Path $ws 'msmdsrv.port.txt') -Raw -Encoding Unicode) -replace '\D', '')
        $cn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$port"); $cn.Open()
        $cmd = $cn.CreateCommand(); $cmd.CommandText = 'EVALUATE ROW("p",[Trains Planned])'
        $r = $cmd.ExecuteReader(); $ok = $false; if ($r.Read()) { $ok = ($r.GetValue(0) -ne $null -and "$($r.GetValue(0))" -ne "") }; $r.Close(); $cn.Close(); return $ok
    } catch { return $false }
}

# ---- clip recorder: one ffmpeg process per clip, stopped cleanly with 'q'
$script:acc = 0.0; $script:clips = @(); $script:scenes = @(); $script:n = 0; $script:sw = $null; $script:ffp = $null
function StartRec {
    $script:n++; $name = 'c{0:D2}' -f $script:n; $file = Join-Path $OutDir "$name.mkv"
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Ffmpeg; $psi.UseShellExecute = $false; $psi.RedirectStandardInput = $true; $psi.CreateNoWindow = $true
    $psi.Arguments = "-y -loglevel error -nostats -f gdigrab -framerate 30 -offset_x 0 -offset_y 0 -video_size 1920x1040 -draw_mouse 1 -i desktop -c:v libx264 -preset veryfast -crf 19 -pix_fmt yuv420p `"$file`""
    $script:ffp = [System.Diagnostics.Process]::Start($psi)
    Start-Sleep -Milliseconds 1000
    $script:sw = [Diagnostics.Stopwatch]::StartNew(); $script:file = $file
}
function StopRec {
    $len = $script:sw.Elapsed.TotalSeconds
    Start-Sleep -Milliseconds 250
    try { $script:ffp.StandardInput.WriteLine('q'); $script:ffp.StandardInput.Flush() } catch { }
    if (-not $script:ffp.WaitForExit(10000)) { $script:ffp.Kill() }
    $script:clips += , @{ file = (Split-Path $script:file -Leaf); sw_len = $len }
    $script:acc += $len; $script:sw = $null
}
function OutT { $script:acc + $(if ($script:sw) { $script:sw.Elapsed.TotalSeconds } else { 0 }) }
function WaitOut($t) { while ((OutT) -lt $t) { Start-Sleep -Milliseconds 40 } }
function BeginScene($id) { $script:cur = @{ id = $id; out_start = (OutT) } }
function EndScene { $script:cur.out_end = (OutT); $script:scenes += , $script:cur }
function WaitUntil($sb, $maxSecs) {   # poll a condition while keeping the screen awake
    $limit = (Get-Date).AddSeconds($maxSecs); $k = 0
    while (-not (& $sb) -and (Get-Date) -lt $limit) { Start-Sleep -Milliseconds 700; $k++; if ($k % 20 -eq 0) { Wiggle } }
}

$dur = @{}; foreach ($id in 'm1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7') { $dur[$id] = Dur (Join-Path $NarrDir "$id.wav") }
Activate

# ---- clip 1: intro + scene 1 (data model) + scene 2 up to the Refresh dialog
StartRec
GlideTo 960 540 1.0
$cp = [System.Windows.Forms.Cursor]::Position
if ([math]::Abs($cp.X - (960 + $ox)) -gt 6) { StopRec; throw 'The cursor cannot be controlled from this session. Run this script in a normal PowerShell window.' }
Click 28 268                                   # Model view
WaitOut $IntroHold
$S1 = OutT; $script:cur = @{ id = 'm1'; out_start = $S1 }
GlideTo 700 420 2.0; GlideTo 1000 560 2.5; GlideTo 800 700 2.5; GlideTo 600 500 2.5
WaitOut ($S1 + $dur['m1'] + 0.8); EndScene

BeginScene 'm2'; $S2 = $script:cur.out_start; Activate
Click 28 188                                   # Report view
Start-Sleep -Milliseconds 600
Click 295 998                                  # Overview page
GlideTo 1766 258 0.8; Click 1766 258           # expand the _Measures table in the Data pane
GlideTo 1830 420 1.5; GlideTo 1830 520 1.5
WaitOut ($S2 + 0.30 * $dur['m2'])
$hb = RegionHash 60 176 460 18
Click 1489 185                                 # step 1: red bar "Refresh now" (relationships)
Start-Sleep -Milliseconds 1500
StopRec                                        # -- waiting for the relationships refresh is not recorded
WaitUntil { (RegionHash 60 176 460 18) -ne $hb } 150
Start-Sleep -Seconds 3
Activate
StartRec
GlideTo 1000 600 0.8
Click 616 105                                  # step 2: ribbon Refresh (loads the data)
GlideTo 960 540 1.2
Start-Sleep -Seconds 14                        # the Refresh dialog with the row counts stays on screen
StopRec                                        # -- everything below is waiting, not recorded
WaitUntil { ModelLoaded } 300
Start-Sleep -Seconds 4
Activate
StartRec                                       # -- clip 2: the loaded report
GlideTo 1000 700 1.0
WaitOut ($S2 + $dur['m2'] + 0.8); EndScene

# ---- scene 3: overview numbers
BeginScene 'm3'; $S3 = $script:cur.out_start
foreach ($x in 400, 610, 820, 1030, 1240) { GlideTo $x 330 1.1 }
GlideTo 480 470 1.5; GlideTo 1005 470 2.0; GlideTo 1100 760 1.5
WaitOut ($S3 + $dur['m3'] + 0.8); EndScene

# ---- scene 4: interactive filter (the repaint delay is cut out)
BeginScene 'm4'; $S4 = $script:cur.out_start
$h0 = RegionHash 300 320 190 50
Click 150 703                                  # Cross-country
Start-Sleep -Milliseconds 900
StopRec
WaitUntil { (RegionHash 300 320 190 50) -ne $h0 } 60
Start-Sleep -Milliseconds 600
StartRec                                       # -- clip 3: the filtered report
GlideTo 820 330 1.2; GlideTo 1090 800 1.5; GlideTo 480 470 1.5
WaitOut ($S4 + 0.72 * $dur['m4'])
$h1 = RegionHash 300 320 190 50
Click 150 703                                  # clear the filter
Start-Sleep -Milliseconds 900
StopRec
WaitUntil { (RegionHash 300 320 190 50) -ne $h1 } 60
Start-Sleep -Milliseconds 600
StartRec                                       # -- clip 4: back to the full network
GlideTo 1000 330 1.0
WaitOut ($S4 + $dur['m4'] + 0.8); EndScene

# ---- scene 5: Home page findings
BeginScene 'm5'; $S5 = $script:cur.out_start
Click 213 998
GlideTo 700 330 1.5; GlideTo 700 470 2.0; GlideTo 1100 620 2.0
WaitOut ($S5 + $dur['m5'] + 0.8); EndScene

# ---- scene 6: Routes & Causes
BeginScene 'm6'; $S6 = $script:cur.out_start
Click 407 998
Start-Sleep -Seconds 2
GlideTo 600 520 1.5; GlideTo 700 540 2.0; GlideTo 750 830 2.0; GlideTo 250 800 2.0; GlideTo 1200 830 1.5
WaitOut ($S6 + $dur['m6'] + 0.8); EndScene

# ---- scene 7: wrap-up
BeginScene 'm7'; $S7 = $script:cur.out_start
Click 295 998
GlideTo 960 600 1.5
WaitOut ($S7 + $dur['m7'] + 1.5); EndScene
StopRec

[WinIO]::SetThreadExecutionState(0x80000000) | Out-Null
@{ intro_hold = $IntroHold; total = $script:acc; scenes = $script:scenes; clips = $script:clips; durations = $dur } | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $OutDir "timeline.json") -Encoding UTF8
"recorded $($script:clips.Count) clips, $([math]::Round($script:acc,1)) s in $OutDir"
