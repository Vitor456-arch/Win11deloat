"""Fixed PowerShell programs with data passed as JSON, never interpolated commands.

No scripts are downloaded and no shell command is accepted from the UI.
"""
import base64
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys


class PlatformUnavailable(RuntimeError):
    pass


class Windows:
    @property
    def supported(self):
        return sys.platform == "win32"

    def require(self):
        if not self.supported:
            raise PlatformUnavailable("This operation requires Windows 10/11. No simulated Windows data is provided.")

    def run(self, script, data=None, timeout=120):
        self.require()
        payload = base64.b64encode(json.dumps(data or {}).encode()).decode()
        prefix = "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
        prefix += "$d = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + payload + "')) | ConvertFrom-Json; "
        code = base64.b64encode((prefix + script).encode("utf-16le")).decode()
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        result = subprocess.run([str(executable), "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", code],
                                capture_output=True, timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        output = result.stdout.decode("utf-8-sig", errors="replace").strip()
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or "Windows operation failed")
        return json.loads(output) if output else None

    def admin(self):
        return self.supported and bool(ctypes.windll.shell32.IsUserAnAdmin())

    def inventory(self):
        return self.run(r'''
$issues = @()
$os = Get-CimInstance Win32_OperatingSystem
$cpu = @(Get-CimInstance Win32_Processor | Select-Object Name, NumberOfLogicalProcessors)
$gpu = @(Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion)
$apps = @(Get-AppxPackage | Select-Object Name, PackageFullName, PackageFamilyName, Version, Publisher, NonRemovable, IsFramework, IsResourcePackage)
$startup = @(Get-CimInstance Win32_StartupCommand | Select-Object Name, Command, Location, User)
$services = @(Get-CimInstance Win32_Service | Select-Object Name, DisplayName, Description, State, StartMode, PathName)
$desktop = @()
foreach ($key in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*')) {
 $desktop += @(Get-ItemProperty $key -ErrorAction SilentlyContinue | Where-Object DisplayName | Select-Object DisplayName, DisplayVersion, Publisher, EstimatedSize, InstallDate)
}
$features = @(); $tasks = @()
try { $features = @(Get-CimInstance Win32_OptionalFeature | Select-Object Name, Caption, InstallState) } catch { $issues += "Optional features: $($_.Exception.Message)" }
try { $tasks = @(Get-ScheduledTask | Select-Object TaskName, TaskPath, State) } catch { $issues += "Scheduled tasks: $($_.Exception.Message)" }
@{OS=$os.Caption; Build=$os.BuildNumber; Version=$os.Version; Boot=$os.LastBootUpTime.ToString('o'); CPU=$cpu; GPU=$gpu; Apps=$apps; DesktopApps=$desktop; Startup=$startup; Services=$services; Features=$features; Tasks=$tasks; Issues=$issues} | ConvertTo-Json -Depth 6 -Compress
''', timeout=180)

    def metrics(self):
        return self.run(r'''
$os=Get-CimInstance Win32_OperatingSystem
$perf=Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
$cpu=Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'"
$procs=@(Get-Process | ForEach-Object {
 $p=$_; $path=$null; $cpuSeconds=$null; try {$path=$p.Path} catch {}; try {$cpuSeconds=$p.CPU} catch {}
 @{Id=$p.Id; Name=$p.ProcessName; Memory=$p.WorkingSet64; CpuSeconds=$cpuSeconds; Path=$path; StartTicks=$(try {$p.StartTime.ToUniversalTime().Ticks.ToString()} catch {$null})}
})
@{Total=[long]$os.TotalVisibleMemorySize*1024; Available=[long]$os.FreePhysicalMemory*1024; Cache=[long]$perf.CacheBytes; Committed=[long]$perf.CommittedBytes; Cpu=$cpu.PercentProcessorTime; Processes=$procs} | ConvertTo-Json -Depth 5 -Compress
''')

    def package(self, name):
        return self.run(r'''$p=@(Get-AppxPackage | Where-Object {$_.Name -ceq $d.name} | Select-Object Name, PackageFullName, PackageFamilyName, NonRemovable, IsFramework, IsResourcePackage); ConvertTo-Json -InputObject $p -Compress''', {"name": name})

    def remove_package(self, name, full_name):
        # Defense in depth: enforce catalog even when called outside the executor.
        from .catalog import APPS
        if name not in APPS:
            raise ValueError("Package is outside the reviewed optional-app catalog")
        return self.run(r'''
$p=@(Get-AppxPackage | Where-Object {$_.Name -ceq $d.name -and $_.PackageFullName -ceq $d.full})
if ($p.Count -ne 1 -or $p[0].NonRemovable -ne $false -or $p[0].IsFramework -ne $false -or $p[0].IsResourcePackage -ne $false) {throw 'Package changed or is protected'}
Remove-AppxPackage -Package $p[0].PackageFullName -ErrorAction Stop
if (@(Get-AppxPackage | Where-Object {$_.Name -ceq $d.name}).Count -ne 0) {throw 'Removal could not be verified'}
@{verified=$true} | ConvertTo-Json -Compress
''', {"name": name, "full": full_name})

    def registry_read(self, setting):
        self.require()
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, setting.path) as key:
                value, kind = winreg.QueryValueEx(key, setting.name)
                return {"exists": True, "value": value, "type": kind}
        except FileNotFoundError:
            return {"exists": False}

    def registry_write(self, setting, state):
        self.require()
        from .catalog import SETTINGS
        if setting not in SETTINGS.values():
            raise ValueError("Registry setting is outside the reviewed catalog")
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, setting.path, 0, winreg.KEY_SET_VALUE) as key:
            if state["exists"]:
                winreg.SetValueEx(key, setting.name, 0, state["type"], state["value"])
            else:
                try:
                    winreg.DeleteValue(key, setting.name)
                except FileNotFoundError:
                    pass

    def restore_status(self):
        return self.run(r'''
$points=@(); $errorText=$null
try { $points=@(Get-ComputerRestorePoint | Select-Object SequenceNumber, Description, CreationTime) } catch {$errorText=$_.Exception.Message}
$disabled=$null
try { $disabled=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore' -Name DisableSR -ErrorAction Stop).DisableSR } catch {}
@{Points=$points; PolicyDisabled=$disabled; Error=$errorText; Protection='Open System Protection to confirm protection for the system drive; policy and existing points alone do not prove it is enabled.'} | ConvertTo-Json -Depth 4 -Compress
''')

    def create_restore_point(self):
        if not self.admin():
            raise PermissionError("Restore point creation needs an explicitly elevated app. No automatic elevation is performed.")
        return self.run(r'''
$before=@(Get-ComputerRestorePoint | Select-Object -ExpandProperty SequenceNumber)
$label='Clear Windows '+[guid]::NewGuid().ToString()
Checkpoint-Computer -Description $label -RestorePointType MODIFY_SETTINGS -ErrorAction Stop
$new=@(Get-ComputerRestorePoint | Where-Object {$_.Description -eq $label -and $_.SequenceNumber -notin $before})
if ($new.Count -ne 1) {throw 'A new restore point was not verified. Windows may throttle creation or protection may be disabled.'}
$new[0] | Select-Object SequenceNumber, Description, CreationTime | ConvertTo-Json -Compress
''', timeout=240)

    def terminate(self, pid, start_ticks):
        if not start_ticks:
            raise ValueError("Process identity unavailable; termination blocked")
        return self.run(r'''
$p=Get-Process -Id $d.pid -ErrorAction Stop
$protected=@('system','idle','registry','smss','csrss','wininit','services','lsass','winlogon','svchost','fontdrvhost','dwm','sihost','securityhealthservice','msmpeng','nissrv','sgrmbroker','spoolsv','explorer','powershell','python','pythonw','clearwindows')
if ($p.ProcessName.ToLowerInvariant() -in $protected -or $p.Id -le 4) {throw 'Protected process'}
if ($p.StartTime.ToUniversalTime().Ticks.ToString() -cne $d.ticks) {throw 'PID was reused; refresh before trying again'}
$owner=(Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)" | Invoke-CimMethod -MethodName GetOwnerSid).Sid
if ($owner -ne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value) {throw 'Only current-user processes can be terminated'}
$exe=$p.MainModule.FileName
$win=[IO.Path]::GetFullPath($env:SystemRoot).TrimEnd('\')+'\'
if (!$exe -or [IO.Path]::GetFullPath($exe).StartsWith($win,[StringComparison]::OrdinalIgnoreCase)) {throw 'Windows system executable or inaccessible path'}
$p.Kill(); if (!$p.WaitForExit(10000)) {throw 'Process exit not verified'}
@{verified=$true} | ConvertTo-Json -Compress
''', {"pid": int(pid), "ticks": str(start_ticks)})

    def open_settings(self, target):
        self.require()
        allowed = {"apps": "ms-settings:appsfeatures", "startup": "ms-settings:startupapps", "privacy": "ms-settings:privacy", "gaming": "ms-settings:gaming-gamemode", "recovery": "ms-settings:recovery", "storage": "ms-settings:storagesense"}
        if target == "protection":
            subprocess.Popen([str(Path(os.environ["SystemRoot"]) / "System32/SystemPropertiesProtection.exe")])
        elif target in allowed:
            os.startfile(allowed[target])
        else:
            raise ValueError("Unsupported settings destination")
