"""V1.3 live integration entry; requires running services and incurs model API calls."""
import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).with_name("live_v13.py")), run_name="__main__")
