#!/usr/bin/env python3
import html
import os
import re
import shutil
import stat
import subprocess
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402


APP_ID = "linux-webapp-maker"
APP_NAME = "Web App Maker"
RUNNER_NAME = "linux-webapp-runner"
APP_ID_PREFIX = "io.github.linuxwebappmaker"


def bundled_icon_path() -> Path:
    return Path(__file__).resolve().with_name("webapp-maker.svg")


def xdg_data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))


def xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def local_bin() -> Path:
    return Path.home() / ".local/bin"


def app_home() -> Path:
    return xdg_data_home() / APP_ID


def normalize_url(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Enter a URL.")
    if "://" not in value:
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Use an http or https URL.")
    if not parsed.netloc:
        raise ValueError("The URL must include a domain.")
    return urllib.parse.urlunparse(parsed)


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value[:48] or "webapp"


def app_id_from_slug(slug: str) -> str:
    safe = slug.replace("-", "_")
    if safe[0].isdigit():
        safe = "app_" + safe
    return f"{APP_ID_PREFIX}.{safe}"


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def desktop_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n")


def fetch(url: str, timeout: int = 12):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome Safari LinuxWebAppMaker/3"
            )
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        final_url = response.geturl()
        return response.read(2_500_000), content_type, final_url


class PageParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.in_title = False
        self.title_parts = []
        self.icons = []

    def handle_starttag(self, tag, attrs):
        attrs = {key.lower(): value for key, value in attrs if key}
        if tag.lower() == "title":
            self.in_title = True
        if tag.lower() != "link":
            return
        rel = attrs.get("rel", "").lower()
        href = attrs.get("href")
        if not href:
            return
        if any(part in rel for part in ("icon", "apple-touch-icon", "mask-icon")):
            sizes = attrs.get("sizes", "")
            score = 0
            match = re.search(r"(\d+)x(\d+)", sizes)
            if match:
                score = int(match.group(1)) * int(match.group(2))
            if "apple-touch" in rel:
                score += 50_000
            if "shortcut" in rel or "icon" in rel:
                score += 25_000
            self.icons.append((score, urllib.parse.urljoin(self.base_url, href)))

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)

    @property
    def title(self):
        title = " ".join(part.strip() for part in self.title_parts if part.strip())
        return html.unescape(re.sub(r"\s+", " ", title)).strip()


def inspect_page(url: str):
    data, content_type, final_url = fetch(url)
    parser = PageParser(final_url)
    if "html" in content_type or data.startswith((b"<!", b"<html", b"<HTML")):
        parser.feed(data.decode("utf-8", errors="replace"))
    parsed = urllib.parse.urlparse(final_url)
    fallback_name = parsed.netloc.replace("www.", "")
    icon_candidates = sorted(parser.icons, reverse=True)
    icon_candidates.append((1, urllib.parse.urljoin(final_url, "/favicon.ico")))
    return {
        "url": final_url,
        "title": parser.title or fallback_name,
        "host": parsed.netloc,
        "icons": [candidate[1] for candidate in icon_candidates],
    }


def extension_from_type(content_type: str, url: str):
    lowered = content_type.lower()
    if "svg" in lowered:
        return ".svg"
    if "png" in lowered:
        return ".png"
    if "jpeg" in lowered or "jpg" in lowered:
        return ".jpg"
    if "webp" in lowered:
        return ".webp"
    if "x-icon" in lowered or "image/vnd.microsoft.icon" in lowered:
        return ".ico"
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    return suffix if suffix in (".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico") else ".png"


def create_fallback_icon(path: Path, name: str):
    initials = "".join(word[0] for word in re.findall(r"[A-Za-z0-9]+", name)[:2]).upper() or "WA"
    color_seed = sum(ord(char) for char in name)
    hue = color_seed % 360
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="hsl({hue}, 70%, 42%)"/>
      <stop offset="100%" stop-color="hsl({(hue + 70) % 360}, 72%, 34%)"/>
    </linearGradient>
  </defs>
  <rect width="256" height="256" rx="56" fill="url(#g)"/>
  <text x="128" y="153" text-anchor="middle" font-family="Cantarell, Inter, Arial, sans-serif"
        font-size="82" font-weight="700" fill="white">{html.escape(initials)}</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def download_icon(candidates, destination_base: Path, name: str) -> Path:
    for icon_url in candidates:
        try:
            data, content_type, final_url = fetch(icon_url, timeout=8)
        except Exception:
            continue
        is_image = content_type.lower().startswith("image/")
        has_image_ext = final_url.lower().endswith((".ico", ".png", ".svg", ".jpg", ".jpeg", ".webp"))
        if not is_image and not has_image_ext:
            continue
        ext = extension_from_type(content_type, final_url)
        icon_path = destination_base.with_suffix(ext)
        icon_path.write_bytes(data)
        return icon_path
    icon_path = destination_base.with_suffix(".svg")
    create_fallback_icon(icon_path, name)
    return icon_path


def copy_custom_icon(custom_icon: str, destination_base: Path) -> Path | None:
    if not custom_icon:
        return None
    source = Path(custom_icon).expanduser()
    if not source.exists() or not source.is_file():
        raise ValueError("The selected custom icon file does not exist.")
    suffix = source.suffix.lower()
    if suffix not in (".png", ".svg", ".jpg", ".jpeg", ".webp", ".ico"):
        raise ValueError("Custom icons must be PNG, SVG, JPG, WEBP, or ICO files.")
    destination = destination_base.with_suffix(".jpg" if suffix == ".jpeg" else suffix)
    shutil.copyfile(source, destination)
    return destination


def write_executable(path: Path, content: str):
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def make_launch_script(path: Path, url: str, profile_dir: Path, app_id: str, name: str, icon_path: Path):
    runner = local_bin() / RUNNER_NAME
    content = f"""#!/bin/sh
set -eu
exec {shell_quote(str(runner))} \\
  --app-id {shell_quote(app_id)} \\
  --name {shell_quote(name)} \\
  --url {shell_quote(url)} \\
  --profile {shell_quote(str(profile_dir))} \\
  --icon {shell_quote(str(icon_path))} \\
  "$@"
"""
    write_executable(path, content)


def make_desktop_file(path: Path, name: str, launch_script: Path, icon_path: Path, app_id: str, url: str):
    content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name={desktop_escape(name)}
Comment=Web app created by Linux WebApp Maker
Exec={launch_script}
Icon={icon_path}
Terminal=false
Categories=Network;WebBrowser;
StartupNotify=true
StartupWMClass={desktop_escape(app_id)}
X-GNOME-WMClass={desktop_escape(app_id)}
X-KDE-StartupNotify=true
X-WebApp-URL={desktop_escape(url)}
X-WebApp-Maker={APP_ID}
"""
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def refresh_desktop_database():
    applications = xdg_data_home() / "applications"
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(applications)], check=False)


def pin_kde(desktop_id: str):
    config_path = xdg_config_home() / "plasma-org.kde.plasma.desktop-appletsrc"
    if "KDE" not in os.environ.get("XDG_CURRENT_DESKTOP", "").upper() or not config_path.exists():
        return False, "Automatic pinning was only attempted on KDE Plasma."

    launcher = f"applications:{desktop_id}.desktop"
    lines = config_path.read_text(encoding="utf-8").splitlines()
    current_section = ""

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1]
            continue
        if not current_section.endswith("][Configuration][General"):
            continue
        if not line.startswith("launchers="):
            continue
        launchers = line.split("=", 1)[1]
        if "applications:" not in launchers:
            continue

        values = [item for item in launchers.split(",") if item]
        if launcher in values:
            return True, "This app was already pinned in Plasma."
        values.append(launcher)
        backup = config_path.with_suffix(config_path.suffix + ".bak")
        if not backup.exists():
            backup.write_bytes(config_path.read_bytes())
        lines[index] = "launchers=" + ",".join(values)
        config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        subprocess.run(
            [
                "qdbus6",
                "org.kde.plasmashell",
                "/PlasmaShell",
                "org.kde.PlasmaShell.evaluateScript",
                "plasmashell.reloadConfig()",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True, "App pinned to the KDE Plasma task manager."

    return False, "I could not find the Plasma task manager launcher list."


def unpin_kde(desktop_id: str):
    config_path = xdg_config_home() / "plasma-org.kde.plasma.desktop-appletsrc"
    if not config_path.exists():
        return
    launcher = f"applications:{desktop_id}.desktop"
    lines = config_path.read_text(encoding="utf-8").splitlines()
    current_section = ""
    changed = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1]
            continue
        if not current_section.endswith("][Configuration][General") or not line.startswith("launchers="):
            continue
        values = [item for item in line.split("=", 1)[1].split(",") if item]
        filtered = [item for item in values if item != launcher]
        if filtered != values:
            lines[index] = "launchers=" + ",".join(filtered)
            changed = True

    if changed:
        config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        subprocess.run(
            [
                "qdbus6",
                "org.kde.plasmashell",
                "/PlasmaShell",
                "org.kde.PlasmaShell.evaluateScript",
                "plasmashell.reloadConfig()",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def pin_gnome(desktop_id: str):
    if not shutil.which("gsettings"):
        return False, "gsettings is not available."
    desktop_file = f"{desktop_id}.desktop"
    try:
        current = subprocess.check_output(
            ["gsettings", "get", "org.gnome.shell", "favorite-apps"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return False, "I could not read GNOME favorites."
    if desktop_file in current:
        return True, "This app was already in GNOME favorites."
    apps = re.findall(r"'([^']+)'", current)
    apps.append(desktop_file)
    value = "[" + ", ".join(repr(app) for app in apps) + "]"
    try:
        subprocess.run(["gsettings", "set", "org.gnome.shell", "favorite-apps", value], check=True)
    except Exception:
        return False, "I could not add the app to GNOME favorites."
    return True, "App added to GNOME favorites."


def unpin_gnome(desktop_id: str):
    if not shutil.which("gsettings"):
        return
    desktop_file = f"{desktop_id}.desktop"
    try:
        current = subprocess.check_output(
            ["gsettings", "get", "org.gnome.shell", "favorite-apps"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return
    apps = [app for app in re.findall(r"'([^']+)'", current) if app != desktop_file]
    value = "[" + ", ".join(repr(app) for app in apps) + "]"
    subprocess.run(["gsettings", "set", "org.gnome.shell", "favorite-apps", value], check=False)


def pin_to_taskbar(desktop_id: str):
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if "KDE" in desktop:
        return pin_kde(desktop_id)
    if "GNOME" in desktop:
        return pin_gnome(desktop_id)
    return False, "This desktop environment does not expose a reliable automatic pinning API."


def unpin_from_taskbar(desktop_id: str):
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if "KDE" in desktop:
        unpin_kde(desktop_id)
    if "GNOME" in desktop:
        unpin_gnome(desktop_id)


def electron_binary() -> Path | None:
    local = app_home() / "node_modules" / ".bin" / "electron"
    if local.exists():
        return local
    system = shutil.which("electron")
    return Path(system) if system else None


def electron_available():
    binary = electron_binary()
    if not binary:
        return False, ""
    return True, str(binary)


def read_desktop_entry(path: Path):
    data = {}
    if not path.exists():
        return data
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("[") or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value
    return data


def app_slug_from_desktop_id(desktop_id: str):
    prefix = APP_ID_PREFIX + "."
    if not desktop_id.startswith(prefix):
        return ""
    return desktop_id[len(prefix):].replace("_", "-")


def list_installed_apps():
    apps = []
    for desktop_file in sorted((xdg_data_home() / "applications").glob(f"{APP_ID_PREFIX}.*.desktop")):
        data = read_desktop_entry(desktop_file)
        if data.get("X-WebApp-Maker") != APP_ID:
            continue
        desktop_id = desktop_file.stem
        slug = app_slug_from_desktop_id(desktop_id)
        apps.append(
            {
                "name": data.get("Name", desktop_id),
                "url": data.get("X-WebApp-URL", ""),
                "desktop_id": desktop_id,
                "desktop_file": desktop_file,
                "launch_script": Path(data.get("Exec", "")) if data.get("Exec") else None,
                "icon": Path(data.get("Icon", "")) if data.get("Icon") else None,
                "app_dir": app_home() / "apps" / slug if slug else None,
            }
        )
    return apps


def remove_web_app(desktop_id: str):
    matched = None
    for app_info in list_installed_apps():
        if app_info["desktop_id"] == desktop_id:
            matched = app_info
            break
    if not matched:
        raise ValueError("Selected app was not found.")

    unpin_from_taskbar(desktop_id)

    for key in ("desktop_file", "launch_script"):
        path = matched.get(key)
        if path and path.exists():
            path.unlink()

    app_dir = matched.get("app_dir")
    if app_dir and app_dir.exists() and app_home() in app_dir.parents:
        shutil.rmtree(app_dir)

    desktop_shortcut = Path.home() / "Desktop" / f"{desktop_id}.desktop"
    if desktop_shortcut.exists():
        desktop_shortcut.unlink()

    refresh_desktop_database()
    return matched["name"]


def create_web_app(url: str, name: str, pin: bool, desktop_shortcut: bool, custom_icon: str = ""):
    clean_url = normalize_url(url)
    app_name = name.strip()
    page_info = {}
    if not app_name:
        try:
            page_info = inspect_page(clean_url)
            app_name = page_info["title"]
            clean_url = page_info["url"]
        except Exception:
            parsed = urllib.parse.urlparse(clean_url)
            app_name = parsed.netloc.replace("www.", "")
            page_info = {"icons": []}
    else:
        try:
            page_info = inspect_page(clean_url)
            clean_url = page_info["url"]
        except Exception:
            page_info = {"icons": []}

    slug = slugify(app_name)
    app_id = app_id_from_slug(slug)
    desktop_id = app_id
    created_app_dir = app_home() / "apps" / slug
    profile_dir = created_app_dir / "profile"
    icon_base = created_app_dir / "icon"
    launch_script = local_bin() / f"{APP_ID}-{slug}"
    desktop_file = xdg_data_home() / "applications" / f"{desktop_id}.desktop"

    created_app_dir.mkdir(parents=True, exist_ok=True)
    profile_dir.mkdir(parents=True, exist_ok=True)
    local_bin().mkdir(parents=True, exist_ok=True)
    desktop_file.parent.mkdir(parents=True, exist_ok=True)

    icon_path = copy_custom_icon(custom_icon, icon_base) or download_icon(page_info.get("icons", []), icon_base, app_name)
    make_launch_script(launch_script, clean_url, profile_dir, app_id, app_name, icon_path)
    make_desktop_file(desktop_file, app_name, launch_script, icon_path, app_id, clean_url)
    refresh_desktop_database()

    desktop_message = ""
    if desktop_shortcut:
        desktop_dir = Path.home() / "Desktop"
        if desktop_dir.exists():
            shortcut = desktop_dir / f"{desktop_id}.desktop"
            shortcut.write_text(desktop_file.read_text(encoding="utf-8"), encoding="utf-8")
            shortcut.chmod(shortcut.stat().st_mode | stat.S_IXUSR)
            desktop_message = f"Desktop shortcut created at {shortcut}."
        else:
            desktop_message = "The Desktop folder does not exist, so no desktop shortcut was created."

    pin_message = ""
    if pin:
        ok, pin_message = pin_to_taskbar(desktop_id)
        if not ok:
            pin_message += " The app was added to the application menu, so you can pin it manually from there."

    electron_ok, electron_path = electron_available()
    return {
        "name": app_name,
        "url": clean_url,
        "desktop_file": desktop_file,
        "launch_script": launch_script,
        "icon_path": icon_path,
        "app_id": app_id,
        "electron_ok": electron_ok,
        "electron_path": electron_path,
        "pin_message": pin_message,
        "desktop_message": desktop_message,
    }


class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title=APP_NAME)
        self.set_default_size(680, 520)
        self.set_size_request(560, 420)
        self.set_border_width(18)
        geometry = Gdk.Geometry()
        geometry.max_width = 820
        geometry.max_height = 720
        self.set_geometry_hints(None, geometry, Gdk.WindowHints.MAX_SIZE)
        icon_path = bundled_icon_path()
        if icon_path.exists():
            self.set_icon_from_file(str(icon_path))
        self.custom_icon_path = ""
        self.installed_store = None
        self._build_ui()

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.add(root)

        title = Gtk.Label()
        title.set_markup("<span size='xx-large' weight='bold'>Web App Maker</span>")
        title.set_xalign(0)
        root.pack_start(title, False, False, 0)

        subtitle = Gtk.Label(
            label="Create real Linux web apps with an isolated Electron runtime. No external browser window is launched."
        )
        subtitle.set_xalign(0)
        subtitle.set_line_wrap(True)
        root.pack_start(subtitle, False, False, 0)

        grid = Gtk.Grid(column_spacing=12, row_spacing=12)
        root.pack_start(grid, False, False, 0)

        url_label = Gtk.Label(label="URL")
        url_label.set_xalign(0)
        grid.attach(url_label, 0, 0, 1, 1)
        self.url_entry = Gtk.Entry()
        self.url_entry.set_hexpand(True)
        self.url_entry.set_placeholder_text("example: music.apple.com, chat.openai.com, notion.so")
        grid.attach(self.url_entry, 1, 0, 1, 1)

        name_label = Gtk.Label(label="Name")
        name_label.set_xalign(0)
        grid.attach(name_label, 0, 1, 1, 1)
        self.name_entry = Gtk.Entry()
        self.name_entry.set_hexpand(True)
        self.name_entry.set_placeholder_text("Optional: leave empty to use the page title")
        grid.attach(self.name_entry, 1, 1, 1, 1)

        icon_label = Gtk.Label(label="Custom Icon")
        icon_label.set_xalign(0)
        grid.attach(icon_label, 0, 2, 1, 1)

        icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        icon_box.set_hexpand(True)
        grid.attach(icon_box, 1, 2, 1, 1)

        self.icon_entry = Gtk.Entry()
        self.icon_entry.set_hexpand(True)
        self.icon_entry.set_editable(False)
        self.icon_entry.set_placeholder_text("Optional: PNG, SVG, JPG, WEBP, or ICO")
        icon_box.pack_start(self.icon_entry, True, True, 0)

        self.icon_button = Gtk.Button(label="Browse")
        self.icon_button.connect("clicked", self.on_choose_icon)
        icon_box.pack_start(self.icon_button, False, False, 0)

        self.clear_icon_button = Gtk.Button(label="Clear")
        self.clear_icon_button.connect("clicked", self.on_clear_icon)
        icon_box.pack_start(self.clear_icon_button, False, False, 0)

        self.pin_check = Gtk.CheckButton(label="Pin/add to the taskbar when possible")
        self.pin_check.set_active(True)
        root.pack_start(self.pin_check, False, False, 0)

        self.desktop_check = Gtk.CheckButton(label="Also create a desktop shortcut")
        root.pack_start(self.desktop_check, False, False, 0)

        self.warning = Gtk.Label()
        self.warning.set_xalign(0)
        self.warning.set_line_wrap(True)
        root.pack_start(self.warning, False, False, 0)
        self._refresh_warning()

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        root.pack_start(button_box, False, False, 0)

        self.create_button = Gtk.Button(label="Create App")
        self.create_button.connect("clicked", self.on_create)
        button_box.pack_start(self.create_button, False, False, 0)

        self.open_folder_button = Gtk.Button(label="Open Apps Folder")
        self.open_folder_button.connect("clicked", self.on_open_folder)
        button_box.pack_start(self.open_folder_button, False, False, 0)

        self.status = Gtk.Label()
        self.status.set_xalign(0)
        self.status.set_selectable(True)
        self.status.set_line_wrap(True)
        self.status.set_line_wrap_mode(Pango.WrapMode.CHAR)
        self.status.set_max_width_chars(88)
        root.pack_start(self.status, False, False, 0)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        root.pack_start(separator, False, False, 0)

        apps_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        root.pack_start(apps_header, False, False, 0)

        apps_title = Gtk.Label()
        apps_title.set_markup("<b>Installed Apps</b>")
        apps_title.set_xalign(0)
        apps_header.pack_start(apps_title, True, True, 0)

        self.refresh_button = Gtk.Button(label="Refresh")
        self.refresh_button.connect("clicked", self.on_refresh_apps)
        apps_header.pack_start(self.refresh_button, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_size_request(-1, 130)
        root.pack_start(scroller, True, True, 0)

        self.installed_store = Gtk.ListStore(str, str, str)
        self.installed_view = Gtk.TreeView(model=self.installed_store)
        self.installed_view.set_headers_visible(True)
        self.installed_view.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        scroller.add(self.installed_view)

        for index, title_text in enumerate(("Name", "URL")):
            renderer = Gtk.CellRendererText()
            renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            column = Gtk.TreeViewColumn(title_text, renderer, text=index)
            column.set_expand(index == 1)
            self.installed_view.append_column(column)

        apps_buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        root.pack_start(apps_buttons, False, False, 0)

        self.open_selected_button = Gtk.Button(label="Open Selected")
        self.open_selected_button.connect("clicked", self.on_open_selected_app)
        apps_buttons.pack_start(self.open_selected_button, False, False, 0)

        self.remove_selected_button = Gtk.Button(label="Remove Selected")
        self.remove_selected_button.connect("clicked", self.on_remove_selected_app)
        apps_buttons.pack_start(self.remove_selected_button, False, False, 0)

        self.refresh_installed_apps()

    def _refresh_warning(self):
        ok, path = electron_available()
        if ok:
            self.warning.set_markup(
                f"<span foreground='#2e7d32'>Electron runtime found: {html.escape(path)}.</span>"
            )
        else:
            self.warning.set_markup(
                "<span foreground='#b00020'>Electron runtime is missing. Run ./install-deps.sh before opening created apps.</span>"
            )

    def on_create(self, _button):
        self.create_button.set_sensitive(False)
        self.status.set_text("Creating app... fetching page title and icon.")

        def worker():
            try:
                result = create_web_app(
                    self.url_entry.get_text(),
                    self.name_entry.get_text(),
                    self.pin_check.get_active(),
                    self.desktop_check.get_active(),
                    self.custom_icon_path,
                )
                GLib.idle_add(self._created, result)
            except Exception as exc:
                GLib.idle_add(self._failed, str(exc))

        import threading

        threading.Thread(target=worker, daemon=True).start()

    def _created(self, result):
        self.create_button.set_sensitive(True)
        lines = [
            f"Created: {result['name']}",
            f"URL: {result['url']}",
            f"App ID: {result['app_id']}",
            f"Menu file: {result['desktop_file']}",
            f"Icon: {result['icon_path']}",
        ]
        if result["electron_ok"]:
            lines.append(f"Runtime: {result['electron_path']}")
        else:
            lines.append("Warning: Electron is not installed yet. Run ./install-deps.sh before opening this app.")
        if result["pin_message"]:
            lines.append(result["pin_message"])
        if result["desktop_message"]:
            lines.append(result["desktop_message"])
        self.status.set_text("\n".join(lines))
        self._refresh_warning()
        self.refresh_installed_apps()
        return False

    def _failed(self, message):
        self.create_button.set_sensitive(True)
        self.status.set_text(f"Could not create the app: {message}")
        return False

    def on_choose_icon(self, _button):
        dialog = Gtk.FileChooserDialog(
            title="Choose Custom Icon",
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK),
        )
        image_filter = Gtk.FileFilter()
        image_filter.set_name("Image files")
        for pattern in ("*.png", "*.svg", "*.jpg", "*.jpeg", "*.webp", "*.ico"):
            image_filter.add_pattern(pattern)
            image_filter.add_pattern(pattern.upper())
        dialog.add_filter(image_filter)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.custom_icon_path = dialog.get_filename() or ""
            self.icon_entry.set_text(self.custom_icon_path)
        dialog.destroy()

    def on_clear_icon(self, _button):
        self.custom_icon_path = ""
        self.icon_entry.set_text("")

    def refresh_installed_apps(self):
        if not self.installed_store:
            return
        self.installed_store.clear()
        for app_info in list_installed_apps():
            self.installed_store.append([app_info["name"], app_info["url"], app_info["desktop_id"]])

    def selected_desktop_id(self):
        selection = self.installed_view.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter is None:
            return ""
        return model[tree_iter][2]

    def on_refresh_apps(self, _button):
        self.refresh_installed_apps()
        self.status.set_text("Installed app list refreshed.")

    def on_open_selected_app(self, _button):
        desktop_id = self.selected_desktop_id()
        if not desktop_id:
            self.status.set_text("Select an installed app first.")
            return
        desktop_file = xdg_data_home() / "applications" / f"{desktop_id}.desktop"
        if shutil.which("gtk-launch"):
            subprocess.Popen(["gtk-launch", desktop_id])
        elif desktop_file.exists() and shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", str(desktop_file)])
        else:
            self.status.set_text(f"Could not open {desktop_file}.")

    def on_remove_selected_app(self, _button):
        desktop_id = self.selected_desktop_id()
        if not desktop_id:
            self.status.set_text("Select an installed app first.")
            return

        app_name = desktop_id
        for app_info in list_installed_apps():
            if app_info["desktop_id"] == desktop_id:
                app_name = app_info["name"]
                break

        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.CANCEL,
            text=f"Remove {app_name}?",
        )
        dialog.format_secondary_text("This removes its menu entry, launcher script, icon, and isolated app profile.")
        remove_button = dialog.add_button("Remove", Gtk.ResponseType.OK)
        remove_button.get_style_context().add_class("destructive-action")
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return

        try:
            removed_name = remove_web_app(desktop_id)
            self.refresh_installed_apps()
            self.status.set_text(f"Removed: {removed_name}")
        except Exception as exc:
            self.status.set_text(f"Could not remove the app: {exc}")

    def on_open_folder(self, _button):
        folder = app_home() / "apps"
        folder.mkdir(parents=True, exist_ok=True)
        if shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", str(folder)])
        else:
            self.status.set_text(str(folder))


def main():
    ok, _args = Gtk.init_check(sys.argv)
    if not ok:
        print("Could not start GTK. Run this inside a graphical Linux session.", file=sys.stderr)
        return 1
    icon_path = bundled_icon_path()
    if icon_path.exists():
        Gtk.Window.set_default_icon_from_file(str(icon_path))
    window = MainWindow()
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
