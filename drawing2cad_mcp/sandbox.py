"""
Sandboxed Python CAD script runner.
Enforces process isolation, no network access, and strict time limits.
"""

import sys
import os
import tempfile
import subprocess
import time
from typing import Dict, Any, Optional
import build123d as bd


SANDBOX_SECURITY_HEADER = """
# Sandboxed environment initialization
import sys
import socket

# Disable network connections in sandbox
_orig_socket = socket.socket

class _SandboxDisabledSocket(_orig_socket):
    def connect(self, *args, **kwargs):
        raise PermissionError("Network connection forbidden in CAD sandbox.")
    def connect_ex(self, *args, **kwargs):
        raise PermissionError("Network connection forbidden in CAD sandbox.")

socket.socket = _SandboxDisabledSocket
socket.create_connection = lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("Network connection forbidden in CAD sandbox."))

import build123d as bd
"""

class CADSandbox:
    def __init__(self, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds

    def execute_script(self, script_code: str) -> Dict[str, Any]:
        """
        Execute arbitrary CadQuery / build123d script in an isolated subprocess.
        Script must assign the resulting model to `result_solid` or export to `export_path`.
        """
        start_time = time.time()
        temp_dir = tempfile.mkdtemp(prefix="cad_sandbox_")
        script_path = os.path.join(temp_dir, "sandbox_run.py")
        step_output_path = os.path.join(temp_dir, "model_output.step").replace("\\", "/")

        full_code = f"""{SANDBOX_SECURITY_HEADER}

export_path = "{step_output_path}"

# User generated CAD code:
{script_code}

# Auto-export result
if 'result_solid' in locals() and result_solid is not None:
    bd.export_step(result_solid, export_path)
    print("SANDBOX_SUCCESS: Exported result_solid to STEP.")
elif os.path.exists(export_path):
    print("SANDBOX_SUCCESS: Found exported STEP file.")
else:
    print("SANDBOX_WARNING: No result_solid defined and no STEP file found.")
"""
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(full_code)

        try:
            # Execute subprocess with timeout
            proc = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                cwd=temp_dir
            )
            duration = round(time.time() - start_time, 3)

            if proc.returncode != 0:
                return {
                    "success": False,
                    "error": f"Script exited with error code {proc.returncode}",
                    "stderr": proc.stderr,
                    "stdout": proc.stdout,
                    "duration_seconds": duration,
                    "step_path": None
                }

            if os.path.exists(step_output_path):
                # Verify re-importability
                shape = bd.import_step(step_output_path)
                is_closed_solid = bool(len(shape.solids()) > 0 and shape.volume > 0)
                return {
                    "success": True,
                    "duration_seconds": duration,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "step_path": step_output_path,
                    "is_valid": bool(shape.is_valid),
                    "is_closed": is_closed_solid,
                    "volume": round(float(shape.volume), 4)
                }
            else:
                return {
                    "success": False,
                    "error": "No STEP output was produced by the script.",
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "duration_seconds": duration,
                    "step_path": None
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Execution timed out after {self.timeout_seconds} seconds.",
                "duration_seconds": round(time.time() - start_time, 3),
                "step_path": None
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "duration_seconds": round(time.time() - start_time, 3),
                "step_path": None
            }
