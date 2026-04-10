import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(os.getcwd()) / "src"))

try:
    from missile_tracker import TacticalDisplay
    print("[OK] TacticalDisplay successfully imported.")
    
    # Test individual components
    TacticalDisplay.header()
    TacticalDisplay.section("UNIT TEST", "Verifying dashboard components")
    TacticalDisplay.status("Fix", "OK", "Restoration complete")
    TacticalDisplay.table(["Metric", "Value"], [["Bug", "Fixed"], ["Class", "Restored"]])
    print("\n[SUCCESS] Fix verified.")
except Exception as e:
    print(f"[FAIL] {e}")
    sys.exit(1)
