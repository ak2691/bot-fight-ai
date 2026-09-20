import asyncio
import json
from pathlib import Path
from typing import Any


class JavaBridgeError(RuntimeError):
    pass


class JavaBridge:
    def __init__(self, server_root: str, timeout_seconds: float) -> None:
        self.server_root = server_root
        self.timeout_seconds = timeout_seconds
        self.script = Path(__file__).resolve().parents[2] / "tools" / "invoke-botfight-bridge.ps1"

    async def invoke(self, mode: str, payload: dict[str, Any]) -> dict[str, Any]:
        process = await asyncio.create_subprocess_exec(
            "powershell.exe", "-NoProfile", "-File", str(self.script),
            "-Mode", mode, "-BotFightServerRoot", self.server_root,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(json.dumps(payload).encode("utf-8")),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise JavaBridgeError(f"authoritative bridge timed out after {self.timeout_seconds:g}s") from exc
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace")[-2000:]
            raise JavaBridgeError(f"authoritative bridge failed: {detail}")
        try:
            return json.loads(stdout.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JavaBridgeError("authoritative bridge returned invalid JSON") from exc
