from PIL import Image
import customtkinter
import requests
import os
import uuid
from tkinter import messagebox
import webbrowser
import tempfile
import subprocess
import time
import pystray
from pystray import MenuItem as item
import threading
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
import json
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

console = Console()
CONFIG_FILE = "last-launch.json"
mc_process = None

def save_launcher_config():
    username = entry.get().strip()
    
    if not username:
        console.print("[yellow]⚠️ No Username, using default name: Steve.[/yellow]")
        console.print("[yellow]⚠️ Warning, if you don't fill a username in, BeaconCraft will NOT save your:[/yellow]")
        console.print("[yellow]⚠️ Username[/yellow]")
        console.print("[yellow]⚠️ Version[/yellow]")
        console.print("[yellow]⚠️ Mod loader[/yellow]")
        return

    data = {
        "username": username,
        "version": version_var.get(),
        "loader": loader_var.get()
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)
    console.print(f"[green]💾 Config saved for user: {username}[/green]")

def load_launcher_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            console.print(f"[red]Could not load config: {e}[/red]")
            return None
    return None

local_version = "1.2.1"
update_url = "https://beaconcraft.wasmer.app/BeaconCraft-Setup.exe"
version_txt_url = "https://beaconcraft.wasmer.app/version.txt"

def check_update():
    try:
        response = requests.get(version_txt_url, timeout=5)
        response.raise_for_status()
        online_version = response.text.strip()

        if online_version != local_version:
            result = messagebox.askyesno(
                "Update available!",
                f"A newer version of BeaconCraft is available: {online_version}\n"
                f"You are using: {local_version}.\n\n"
                "Do you want to update the launcher?"
            )
            if result:
                download_and_run_update(update_url)
            else:
                print("Update cancelled by user.")
    except Exception as e:
        print("Cannot check for new updates:", e)

def download_and_run_update(url):
    try:
        temp_file = os.path.join(tempfile.gettempdir(), "BeaconCraft_Setup.exe")
        print(f"⬇️ Downloading update to {temp_file}...")
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(temp_file, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
        print("Update downloaded! Starting installation...")
        subprocess.Popen([temp_file])
        print("Close the launcher to install the update...")
        time.sleep(2.5)
        quit()
    except Exception as e:
        print("There was an error during downloading/installing update:", e)
        result2 = messagebox.askyesno(
                "Error!",
                f"There was an error during downloading/installing the update:\n{e}\n\n"
                f"Download the newest version in the browser: beaconcraft.wasmer.app\n"
                f"If the setup has already opened, ignore this message...\n\n"
                "Do you want to open the browser?"
            )
        if result2:
                webbrowser.open('https://beaconcraft.wasmer.app')

check_update()

# --- Get Minecraft versions ---
all_versions = [] 

def version_is_newer_or_equal(v, minimum="1.19"):
    try:
        a = list(map(int, v.split(".")))
        b = list(map(int, minimum.split(".")))
        return a >= b
    except:
        return False

def update_versions():
    global all_versions
    versions = []
    
    try:
        console.print("[cyan]🌐 Fetching online version manifest...[/cyan]")
        response = requests.get(
            "https://launchermeta.mojang.com/mc/game/version_manifest.json", 
            timeout=2 
        )
        data = response.json()
        all_versions = data["versions"]
        
        online_versions = [
            v["id"] for v in all_versions
            if v["type"] == "release" and version_is_newer_or_equal(v["id"])
        ]
        versions = online_versions
        console.print("[green]✔️ Online version list loaded.[/green]")
    except Exception:
        console.print("[yellow]⚠️ Internet connection failed. Scanning local folders...[/yellow]")
        versions_dir = os.path.join(os.path.abspath(""), "versions")
        if os.path.exists(versions_dir):
            try:
                local_folders = os.listdir(versions_dir)
                for folder in local_folders:
                    json_path = os.path.join(versions_dir, folder, f"{folder}.json")
                    if os.path.exists(json_path):
                        if "forge" not in folder.lower() and "fabric" not in folder.lower():
                            versions.append(folder)
                versions.sort(key=lambda s: [int(u) for u in s.split('.')], reverse=True)
            except Exception as scan_error:
                console.print(f"[red]❌ Error scanning local versions: {scan_error}[/red]")

    if versions:
        dropdown.configure(values=versions)
        current_selection = version_var.get()
        if current_selection not in versions:
            version_var.set(versions[0])
    else:
        error_msg = "No versions downloaded"
        dropdown.configure(values=[error_msg])
        version_var.set(error_msg)

# ---------------- FABRIC HELPERS ----------------

def get_fabric_loader(mc_version):
    url = f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}"
    try:
        response = requests.get(url, verify=False, timeout=1.5)
        response.raise_for_status()
        return response.json()[0]["loader"]
    except:
        return None

def maven_to_path(maven):
    group, artifact, version = maven.split(":")
    return f"{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}.jar"

def download_file(url, path):
    """Downloads a file with a Rich progress bar and temporary file safety."""
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return

    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = path + ".tmp"
    
    try:
        with requests.get(url, stream=True, timeout=10, verify=False) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console,
                transient=True  # Bar disappears after finishing to keep console clean
            ) as progress:
                task = progress.add_task(f"[cyan]Downloading {os.path.basename(path)}", total=total_size)
                with open(temp_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            progress.update(task, advance=len(chunk))
        
        if os.path.exists(path):
            os.remove(path)
        os.rename(temp_path, path)
        console.print(f"[green]✅ Finished:[/green] {os.path.basename(path)}")
        
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        console.print(f"[yellow]⚠️ Download failed: {os.path.basename(path)} ({e})[/yellow]")
        
# ---------------- DOWNLOAD GAME ----------------

def download_version(version_id):
    vdir = os.path.join("versions", version_id)
    json_path = os.path.join(vdir, f"{version_id}.json")
    jar_path = os.path.join(vdir, f"{version_id}.jar")

    vjson = {}
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            vjson = json.load(f)
    elif all_versions:
        info_url = next(v["url"] for v in all_versions if v["id"] == version_id)
        vjson = requests.get(info_url).json()
        os.makedirs(vdir, exist_ok=True)
        with open(json_path, "w") as f:
            json.dump(vjson, f)
    else:
        raise RuntimeError("Version metadata not found locally. Please connect to the internet once.")

    if not os.path.exists(jar_path) and vjson:
        if all_versions:
            download_file(vjson["downloads"]["client"]["url"], jar_path)
        else:
            raise RuntimeError("Minecraft JAR missing and no internet to download it.")

    libs = []
    if vjson:
        for lib in vjson.get("libraries", []):
            if "rules" in lib:
                is_for_windows = False
                for rule in lib["rules"]:
                    if rule["action"] == "allow":
                        if "os" not in rule or rule["os"].get("name") == "windows":
                            is_for_windows = True
                    if rule["action"] == "disallow":
                        if rule.get("os", {}).get("name") == "windows":
                            is_for_windows = False
                if not is_for_windows:
                    continue

            if "artifact" in lib.get("downloads", {}):
                a = lib["downloads"]["artifact"]
                path = os.path.abspath(os.path.join("libraries", a["path"]))
                if os.path.exists(path):
                    libs.append(path)
                elif all_versions:
                    download_file(a["url"], path)
                    libs.append(path)

    return jar_path, libs, vjson
    
# ----------- DOWNLOAD SOUNDS ------------
from concurrent.futures import ThreadPoolExecutor

def download_single_asset(args):
    url, out_path, size, progress, task = args
    if os.path.exists(out_path):
        progress.update(task, advance=size)
        return

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    try:
        r = requests.get(url, timeout=10)
        with open(out_path, "wb") as f:
            f.write(r.content)
        progress.update(task, advance=size)
    except:
        pass 

def download_sound_assets(vjson):
    if not vjson: return
    asset_id = vjson["assetIndex"]["id"]
    index_url = vjson["assetIndex"]["url"]
    index_path = os.path.join("assets", "indexes", f"{asset_id}.json")

    if not os.path.exists(index_path):
        try:
            r = requests.get(index_url)
            with open(index_path, "w") as f: f.write(r.text)
        except: return

    with open(index_path, "r") as f: data = json.load(f)
    objects = {k: v for k, v in data["objects"].items() if k.startswith("minecraft/sounds/")}
    total_size = sum(v["size"] for v in objects.values())

    with Progress(TextColumn("[bold green]Sounds[/]"), BarColumn(), DownloadColumn(), console=console) as progress:
        task = progress.add_task("Downloading assets...", total=total_size)
        download_tasks = []
        for name, info in objects.items():
            h = info["hash"]
            url = f"https://resources.download.minecraft.net/{h[:2]}/{h}"
            out_path = os.path.join("assets", "objects", h[:2], h)
            download_tasks.append((url, out_path, info["size"], progress, task))

        with ThreadPoolExecutor(max_workers=5) as executor:
            executor.map(download_single_asset, download_tasks)

    console.print("[green]✅ Sounds finished![/]\n")

# ----------------- TRAY -----------------
tray_icon = None

def show_window(icon=None, item=None):
    app.after(0, app.deiconify)
    if icon:
        icon.stop()

def quit_app(icon=None, item=None):
    if icon:
        icon.stop()
    app.destroy()

def minimize_to_tray():
    global tray_icon
    app.withdraw()

    try:
        image = Image.open("assets/icon.ico")
        tray_icon = pystray.Icon(
            "BeaconCraft",
            image,
            "BeaconCraft",
            menu=(
                item("Open BeaconCraft", show_window),
                item("Kill Minecraft", kill_minecraft),
                item("Quit", quit_app)
            )
        )
        threading.Thread(target=tray_icon.run, daemon=True).start()
    except:
        pass
    
def kill_minecraft(icon=None, item=None):
    global mc_process
    if mc_process and mc_process.poll() is None:
        console.print("[bold red]Force Quitting Minecraft...[/bold red]")
        mc_process.terminate()
    else:
        console.print("[yellow]Minecraft isn't running.[/yellow]")

# ------------- MONITOR FUNCTION -------------
def monitor_minecraft():
    global mc_process
    
    if tray_icon:
        tray_icon.title = f"BeaconCraft - Playing {version_var.get()}"

    for line in mc_process.stdout:
        l = line.strip()
        if any(x in l for x in ["ERROR", "FATAL", "Exception"]):
            console.print(f"[bold red]{l}[/bold red]")
        elif "WARN" in l:
            console.print(f"[yellow]{l}[/yellow]")
        elif "Caused by:" in l:
            console.print(f"[bold cyan]🔍 {l}[/bold cyan]")
        else:
            console.print(f"[dim]{l}[/dim]")

    mc_process.wait()
    console.print("[bold blue]Minecraft is closed. Launcher restoring...[/bold blue]")
    
    if tray_icon:
        tray_icon.stop()
    app.after(0, app.deiconify)

# ------------- LAUNCH FORGE -------------
import minecraft_launcher_lib

def launch_forge():
    global mc_process
    save_launcher_config()
    
    username = entry.get().strip() or "Steve"
    mc_version = version_var.get()
    minecraft_directory = os.path.abspath("")
    versions_dir = os.path.join(minecraft_directory, "versions")
    
    actual_forge_id = None

    # 1. ROBUST OFFLINE CHECK
    # We look for any folder that contains BOTH the MC version and the word "forge"
    if os.path.exists(versions_dir):
        for folder in os.listdir(versions_dir):
            if mc_version in folder and "forge" in folder.lower():
                # Check if the .json file exists inside
                json_path = os.path.join(versions_dir, folder, f"{folder}.json")
                if os.path.exists(json_path):
                    actual_forge_id = folder
                    console.print(f"[green]✔️ Found local Forge version: {actual_forge_id}[/green]")
                    break

    # 2. INSTALL ONLY IF NOT FOUND
    if not actual_forge_id:
        console.print("[yellow]Forge not found locally. Attempting to install...[/yellow]")
        try:
            # We use a try-except specifically for the installer to handle file locks
            forge_id_from_lib = minecraft_launcher_lib.forge.find_forge_version(mc_version)
            if forge_id_from_lib:
                actual_forge_id = forge_id_from_lib
                console.print(f"[cyan]Installing {actual_forge_id}... please wait.[/cyan]")
                minecraft_launcher_lib.forge.install_forge_version(actual_forge_id, minecraft_directory)
        except Exception as e:
            console.print(f"[red]Forge Installation Error: {e}[/red]")
            messagebox.showerror("Forge Error", f"Could not install Forge.\n\nNote: If you use OneDrive, try pausing it temporarily.\n\nError: {e}")
            return

    if not actual_forge_id:
        return

    # 3. LAUNCH
    minimize_to_tray()
    options = {
        "username": username,
        "uuid": str(uuid.uuid4()),
        "token": str(uuid.uuid4()),
        "jvmArguments": ["-Xmx4G"],
        "executablePath": os.path.abspath("java\\bin\\java.exe")
    }

    try:
        console.print(f"[yellow]🚀 Launching Forge {actual_forge_id}...[/yellow]")
        cmd = minecraft_launcher_lib.command.get_minecraft_command(actual_forge_id, minecraft_directory, options)
        mc_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        threading.Thread(target=monitor_minecraft, daemon=True).start()
    except Exception as e:
        console.print(f"[red]Launch error: {e}[/red]")
        app.after(0, app.deiconify)
        
# ------------ LAUNCH FABRIC -------------
def launch_fabric():
    global mc_process
    save_launcher_config()
    
    username = entry.get().strip() or "Steve"
    mc_version = version_var.get()
    token = uuid.uuid4()
    
    if mc_version == "No versions downloaded":
        messagebox.showerror("Error", "Please download a Minecraft version first!")
        return

    minimize_to_tray()

    try:
        # 1. Connection Check
        has_internet = True
        try:
            requests.get("https://launchermeta.mojang.com", timeout=1.5)
            console.print("[cyan]🌐 Internet detected. Starting Online Flow...[/cyan]")
        except:
            has_internet = False
            console.print("[yellow]📡 No internet. Switching to Offline Flow...[/yellow]")

        # 2. Get Base Files
        jar, vanilla_libs, vjson = download_version(mc_version)
        
        loader_path = ""
        fabric_libs = []

        # 3. Handle Libraries
        fabric_loader = get_fabric_loader(mc_version) if has_internet else None

        if fabric_loader:
            # --- ONLINE FLOW ---
            loader_maven = fabric_loader["maven"]
            loader_path = os.path.abspath(os.path.join("libraries", maven_to_path(loader_maven)))
            download_file(f"https://maven.fabricmc.net/{maven_to_path(loader_maven)}", loader_path)

            profile_url = f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}/{fabric_loader['version']}/profile/json"
            profile = requests.get(profile_url, verify=False).json()
            
            for lib in profile["libraries"]:
                m = lib["name"]
                path = os.path.abspath(os.path.join("libraries", maven_to_path(m)))
                url = lib.get("url", "https://maven.fabricmc.net/") + maven_to_path(m)
                download_file(url, path)
                fabric_libs.append(path)
        else:
            # --- PRECISION OFFLINE SCAN ---
            console.print("[yellow]⚠️ Offline mode: Deep scanning for all required components...[/yellow]")
            base_lib_dir = os.path.abspath("libraries")
            latest_libs = {}

            if os.path.exists(base_lib_dir):
                for root, dirs, files in os.walk(base_lib_dir):
                    blocked = ["forge", "minecraftforge", "securemodules", "org/spongepowered/mixin", "org\\spongepowered\\mixin"]
                    if any(x in root.lower() for x in blocked):
                        continue
                        
                    for file in files:
                        if file.endswith(".jar"):
                            full_path = os.path.join(root, file)
                            if "fabric-loader" in file.lower():
                                if not loader_path or "net/fabricmc" in full_path.replace("\\", "/"):
                                    loader_path = full_path
                                continue
                            file_no_ext = file.replace(".jar", "")
                            parts = file_no_ext.split('-')
                            name_parts = []
                            for p in parts:
                                if p and p[0].isdigit():
                                    break
                                name_parts.append(p)
                            component_id = "-".join(name_parts)
                            folder_version = os.path.basename(root)
                            is_fabric_native = "net/fabricmc" in root.lower().replace("\\", "/")
                            if component_id not in latest_libs:
                                latest_libs[component_id] = full_path
                            else:
                                existing_path = latest_libs[component_id]
                                existing_is_fabric = "net/fabricmc" in existing_path.lower().replace("\\", "/")
                                if (is_fabric_native and not existing_is_fabric) or \
                                   (is_fabric_native == existing_is_fabric and folder_version > os.path.basename(os.path.dirname(existing_path))):
                                    latest_libs[component_id] = full_path

            fabric_libs = list(latest_libs.values())
            console.print(f"[green]✔️ Found {len(fabric_libs)} unique components locally.[/green]")

        if not loader_path or not os.path.exists(loader_path):
            raise RuntimeError("Fabric loader not found! Please launch online once.")

        classpath_list = list(set(vanilla_libs + fabric_libs + [loader_path, os.path.abspath(jar)]))
        classpath = ";".join(classpath_list)
        game_dir = os.path.abspath("")

        cmd = [
            "java\\bin\\java.exe",
            "-Xmx4G",
            "-cp", classpath,
            "net.fabricmc.loader.impl.launch.knot.KnotClient",
            "--username", username,
            "--version", mc_version,
            "--gameDir", game_dir,
            "--assetsDir", os.path.join(game_dir, "assets"),
            "--assetIndex", vjson.get("assetIndex", {}).get("id", "legacy") if vjson else "legacy",
            "--uuid", str(uuid.uuid4()),
            "--accessToken", str(token),
            "--userType", "legacy"
        ]

        console.print(f"[yellow]🚀 Launching Fabric {mc_version}...[/yellow]")
        mc_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        threading.Thread(target=monitor_minecraft, daemon=True).start()

    except Exception as e:
        console.print(f"[red]Fabric Launch Error: {e}[/red]")
        messagebox.showerror("Launch Error", f"Launch failed: {e}")
        app.after(0, app.deiconify)
        
# --- App setup ---
app = customtkinter.CTk()
app.geometry("960x540")
app.title("BeaconCraft")
customtkinter.set_appearance_mode("dark")

# --- Background ---
original_image = Image.open("assets/background.png")
ctk_image = customtkinter.CTkImage(original_image, size=(960, 540))
bg_label = customtkinter.CTkLabel(app, image=ctk_image, text="")
bg_label.place(relx=0, rely=0, relwidth=1, relheight=1)

cornerbar = customtkinter.CTkLabel(app, text="")
cornerbar.place(relx=1, rely=1, anchor="se", relwidth=0.32, relheight=0.27)

my_image = customtkinter.CTkImage(Image.open("assets/logo.png"), size=(240, 90))
image_label = customtkinter.CTkLabel(app, image=my_image, text="")
image_label.place(anchor="nw", relwidth=1, relheight=0.2)

entry = customtkinter.CTkEntry(app, placeholder_text="Username")
entry.place(relx=0.95, rely=0.93, anchor="se", relwidth=0.25, relheight=0.06)

version_var = customtkinter.StringVar()
dropdown = customtkinter.CTkOptionMenu(app, values=[], variable=version_var)
dropdown.place(relx=0.95, rely=0.87, anchor="se", relwidth=0.25, relheight=0.06)

loader_var = customtkinter.StringVar(value="Fabric")
loader_dropdown = customtkinter.CTkOptionMenu(app, values=["Fabric", "Forge"], variable=loader_var)
loader_dropdown.place(relx=0.95, rely=0.82, anchor="se", relwidth=0.25, relheight=0.06)

update_versions()

def start_game():
    if loader_var.get() == "Fabric":
        launch_fabric()
    else:
        launch_forge()

button = customtkinter.CTkButton(app, text="Play", command=start_game)
button.place(relx=0.95, rely=0.99, anchor="se", relwidth=0.25, relheight=0.06)

sidebar = customtkinter.CTkFrame(app, fg_color="#212121", corner_radius=0)
sidebar.place(relx=0, rely=0.2, relwidth=0.07, relheight=0.8)

homeb = customtkinter.CTkButton(app, text="⌂")
homeb.place(relx=0, rely=0.20, relwidth=0.07, relheight=0.07)

modb = customtkinter.CTkButton(app, text="+")
modb.place(relx=0, rely=0.28, relwidth=0.07, relheight=0.07)

shadeb = customtkinter.CTkButton(app, text="🌟")
shadeb.place(relx=0, rely=0.36, relwidth=0.07, relheight=0.07)

worldb = customtkinter.CTkButton(app, text="🌍")
worldb.place(relx=0, rely=0.44, relwidth=0.07, relheight=0.07)

profb = customtkinter.CTkButton(app, text="👤")
profb.place(relx=0, rely=0.52, relwidth=0.07, relheight=0.07)

setb = customtkinter.CTkButton(app, text="⚙︎")
setb.place(relx=0, rely=0.60, relwidth=0.07, relheight=0.07)

def resize_bg(event):
    new_image = customtkinter.CTkImage(original_image, size=(event.width, event.height))
    bg_label.configure(image=new_image)
    bg_label.image = new_image

saved_data = load_launcher_config()
if saved_data:
    entry.delete(0, "end")
    if saved_data.get("username"):
        entry.insert(0, saved_data["username"])
    if saved_data.get("version") in dropdown.cget("values"):
        version_var.set(saved_data["version"])
    if saved_data.get("loader"):
        loader_var.set(saved_data["loader"])

app.bind("<Configure>", resize_bg)
app.mainloop()