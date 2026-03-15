"""
make_launcher.py - Creates launcher/PyProxy.exe
A tiny exe that silently launches tray_app.py via pythonw.
Run: python make_launcher.py
"""
import os
import sys
import subprocess
from pathlib import Path

LAUNCHER_DIR = Path(__file__).parent / "launcher"
LAUNCHER_DIR.mkdir(exist_ok=True)

SRC = LAUNCHER_DIR / "_launcher_src.py"
OUT = LAUNCHER_DIR / "PyProxy.exe"

# Write the launcher source
SRC.write_text(
    "import subprocess, sys\n"
    "from pathlib import Path\n"
    "base = Path(sys.executable).parent\n"
    "script = base / 'tray_app.py'\n"
    "subprocess.Popen(['pythonw', str(script)], cwd=str(base))\n"
)

print("Building launcher exe via PyInstaller...")

result = subprocess.run(
    [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",
        "--name", "PyProxy",
        "--distpath", str(LAUNCHER_DIR),
        "--workpath", str(LAUNCHER_DIR / "_build"),
        "--specpath", str(LAUNCHER_DIR),
        str(SRC),
    ],
    capture_output=True,
    text=True,
)

# Cleanup temp files
SRC.unlink(missing_ok=True)
spec = LAUNCHER_DIR / "PyProxy.spec"
if spec.exists():
    spec.unlink()
build_dir = LAUNCHER_DIR / "_build"
if build_dir.exists():
    import shutil
    shutil.rmtree(build_dir, ignore_errors=True)

if result.returncode == 0 and OUT.exists():
    print(f"[OK] Created {OUT}")
    sys.exit(0)
else:
    print("[ERROR] PyInstaller failed:")
    print(result.stdout[-1000:] if result.stdout else "")
    print(result.stderr[-1000:] if result.stderr else "")
    sys.exit(1)