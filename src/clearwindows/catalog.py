"""Small reviewed catalogs; unknown software is never automatically recommended."""
from dataclasses import dataclass


@dataclass(frozen=True)
class AppRule:
    name: str
    label: str
    reason: str
    consequence: str
    tier: int


APPS = {r.name: r for r in [
    AppRule("Clipchamp.Clipchamp", "Clipchamp", "Optional video editor; review if unused.", "Video editor removed for this user. Projects are not backed up by this tool.", 0),
    AppRule("Microsoft.BingNews", "Microsoft News", "Optional news reader.", "News app removed for this user.", 0),
    AppRule("Microsoft.BingWeather", "Weather", "Optional weather reader.", "Weather app removed for this user.", 0),
    AppRule("Microsoft.MicrosoftSolitaireCollection", "Solitaire", "Optional game collection.", "Games removed; unsynced game data may be lost.", 0),
    AppRule("Microsoft.MicrosoftOfficeHub", "Microsoft 365 hub", "Optional Microsoft 365 launch hub; not the Office suite.", "Hub removed; installed Office programs remain.", 0),
    AppRule("MicrosoftTeams", "Teams personal", "Optional consumer communications app.", "Personal Teams removed; export any unsynced data first.", 1),
    AppRule("MSTeams", "Microsoft Teams", "Communications app; retain if used for work or school.", "Teams app removed for this user; work communication may be affected.", 2),
    AppRule("Microsoft.Copilot", "Copilot", "Separately installed optional assistant.", "Standalone Copilot app removed; Windows integrations may remain.", 1),
    AppRule("Microsoft.GamingApp", "Xbox", "Optional gaming launcher; keep if used for Game Pass.", "Xbox launcher removed; Game Pass workflows may be affected.", 2),
    AppRule("Microsoft.XboxGamingOverlay", "Xbox Game Bar", "Optional capture and gaming overlay.", "Game Bar capture and shortcuts unavailable.", 2),
]}


@dataclass(frozen=True)
class Setting:
    id: str
    label: str
    path: str
    name: str
    value: int
    reason: str
    side_effect: str
    group: str
    restart: bool = False


SETTINGS = {s.id: s for s in [
    Setting("advertising", "Disable advertising ID", r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled", 0,
            "Reduce personalization using the per-user advertising ID.", "Apps may show less relevant ads; this does not block all telemetry.", "Privacy Settings"),
    Setting("suggestions", "Disable suggested content in Settings", r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "SubscribedContent-338393Enabled", 0,
            "Reduce optional promotional suggestions.", "Some Windows versions may ignore this preference.", "Windows Debloater"),
    Setting("explorer-extensions", "Show filename extensions", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "HideFileExt", 0,
            "Make file types visible in Explorer.", "Full filename extensions become visible. Explorer may need reopening.", "System Optimization"),
    Setting("game-mode", "Enable Windows Game Mode", r"Software\Microsoft\GameBar", "AutoGameModeEnabled", 1,
            "Use Windows' built-in game scheduling preference.", "No FPS gain is promised; behavior depends on the game and hardware.", "Gaming Optimization"),
]}

PRESETS = ["Essential Cleanup", "Balanced Optimization", "Advanced Debloat"]


def recommended_apps(packages, tier):
    """Only observed, removable, exact identities in the reviewed catalog."""
    return [p for p in packages if p.get("Name") in APPS
            and p.get("NonRemovable") is False and p.get("IsFramework") is False
            and p.get("IsResourcePackage") is False and APPS[p["Name"]].tier <= tier]
