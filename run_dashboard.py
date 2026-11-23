"""Dashboard Launcher Script

Project: Email Automation & Reminder System
Author: Akash Das
Role: Launches the Streamlit interactive dashboard. Supports both direct Python invocation
and execution via 'streamlit run run_dashboard.py'.
"""

import subprocess
import sys
from pathlib import Path
import streamlit as st

def launch_dashboard() -> None:
    """Invokes Streamlit targeting dashboard/app.py."""
    dashboard_app = Path(__file__).parent / "dashboard" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(dashboard_app)])

if __name__ == "__main__":
    if st.runtime.exists():
        # Invoked directly via `streamlit run run_dashboard.py`
        from dashboard.app import main
        main()
    else:
        # Invoked via standard Python launcher `python run_dashboard.py`
        launch_dashboard()

