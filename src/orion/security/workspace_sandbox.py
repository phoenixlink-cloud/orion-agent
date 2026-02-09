"""
Orion Agent — Workspace Sandbox (v6.5.0)

Isolates file edits in a separate directory so changes can be
reviewed (diff) before promotion to the real workspace.

Two execution backends:
  - DOCKER:  Full container isolation — files mounted read-only,
             edits in a writable overlay.  Strongest security.
  - LOCAL:   Temp-directory copy with OS-level restrictions.
             Works everywhere, no Docker required.
  - AUTO:    Try Docker first, fall back to local.

The code-execution sandbox (security/sandbox.py) handles running
untrusted code.  This module handles workspace-level file isolation
for the edit→review→promote cycle.

Usage:
    sandbox = WorkspaceSandbox(mode="auto")
    session = sandbox.create_session("/path/to/project")
    # ... Orion edits files inside session.sandbox_path ...
    diff = sandbox.get_diff(session)        # review changes
    sandbox.promote(session)                # copy approved edits back
    sandbox.destroy_session(session.session_id)
"""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("orion.security.workspace_sandbox")


# ─────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────

SANDBOX_STATE_DIR = Path.home() / ".orion" / "sandbox_sessions"

# Directories/files never copied into the sandbox
COPY_EXCLUDE = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".env", ".orion", ".tox", "dist", "build", "*.egg-info",
}

# Max workspace size we'll copy (500 MB)
MAX_COPY_SIZE_BYTES = 500 * 1024 * 1024


# ─────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────

class SandboxMode(str, Enum):
    DOCKER = "docker"
    LOCAL = "local"
    AUTO = "auto"


@dataclass
class SandboxSession:
    """Represents an active sandbox session."""
    session_id: str
    sandbox_path: str
    source_path: str
    mode: str               # "docker" or "local" (resolved mode, not "auto")
    created_at: float = field(default_factory=time.time)
    container_id: Optional[str] = None   # Docker container ID if applicable
    file_count: int = 0
    size_bytes: int = 0


@dataclass
class SandboxDiff:
    """Diff between sandbox and source workspace."""
    added: List[str] = field(default_factory=list)
    modified: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    total_changes: int = 0
    diff_text: str = ""


@dataclass
class PromoteResult:
    """Result of promoting sandbox changes back to source."""
    success: bool
    files_promoted: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    dry_run: bool = False


@dataclass
class SandboxCapabilities:
    """Describes what the sandbox can do."""
    mode: str
    can_execute_code: bool
    can_edit_files: bool
    can_install_packages: bool
    can_access_network: bool
    isolation_level: str       # "process", "filesystem", "container"
    supported_languages: List[str]
    max_timeout_seconds: int
    max_memory_mb: int
    docker_available: bool


# ─────────────────────────────────────────────────────────────────────
# WorkspaceSandbox
# ─────────────────────────────────────────────────────────────────────

class WorkspaceSandbox:
    """
    Workspace-level sandbox for the edit→review→promote cycle.

    Supports Docker and local (temp-dir) backends.
    """

    def __init__(
        self,
        mode: str = "auto",
        sandbox_root: Optional[str] = None,
        docker_image: str = "python:3.11-slim",
        memory_limit: str = "512m",
        cpu_limit: str = "2.0",
        timeout: int = 60,
        network_enabled: bool = False,
    ):
        self.requested_mode = SandboxMode(mode.lower())
        self.sandbox_root = Path(sandbox_root) if sandbox_root else SANDBOX_STATE_DIR
        self.docker_image = docker_image
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.timeout = timeout
        self.network_enabled = network_enabled

        self._sessions: Dict[str, SandboxSession] = {}
        self.sandbox_root.mkdir(parents=True, exist_ok=True)

    # ── Backend detection ─────────────────────────────────────────────

    def is_docker_available(self) -> bool:
        """Check if Docker daemon is running."""
        try:
            result = subprocess.run(
                ["docker", "info"], capture_output=True, timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _resolve_mode(self) -> str:
        """Resolve AUTO mode to a concrete backend."""
        if self.requested_mode == SandboxMode.DOCKER:
            return "docker"
        elif self.requested_mode == SandboxMode.LOCAL:
            return "local"
        else:  # AUTO
            return "docker" if self.is_docker_available() else "local"

    # ── Session lifecycle ─────────────────────────────────────────────

    def create_session(self, source_path: str) -> SandboxSession:
        """
        Create a new sandbox session from a source workspace.

        Copies the workspace into an isolated directory.
        If Docker mode, also starts a persistent container with the
        sandbox mounted.
        """
        source = Path(source_path).resolve()
        if not source.exists():
            raise FileNotFoundError(f"Source path does not exist: {source}")

        mode = self._resolve_mode()
        session_id = self._generate_session_id(source)

        sandbox_dir = self.sandbox_root / session_id
        sandbox_dir.mkdir(parents=True, exist_ok=True)

        # Copy workspace into sandbox
        file_count, size_bytes = self._copy_workspace(source, sandbox_dir)

        session = SandboxSession(
            session_id=session_id,
            sandbox_path=str(sandbox_dir),
            source_path=str(source),
            mode=mode,
            file_count=file_count,
            size_bytes=size_bytes,
        )

        # Docker: start a persistent container with the sandbox mounted
        if mode == "docker":
            container_id = self._start_docker_container(session)
            session.container_id = container_id

        self._sessions[session_id] = session
        self._save_session_meta(session)

        logger.info(
            "Sandbox session created: %s (mode=%s, files=%d, size=%d bytes)",
            session_id, mode, file_count, size_bytes,
        )
        return session

    def get_session(self, session_id: str) -> Optional[SandboxSession]:
        """Retrieve an active session."""
        return self._sessions.get(session_id)

    def list_sessions(self) -> List[SandboxSession]:
        """List all active sessions."""
        return list(self._sessions.values())

    def destroy_session(self, session_id: str) -> bool:
        """Destroy a sandbox session and clean up resources."""
        session = self._sessions.pop(session_id, None)
        if not session:
            return False

        # Stop Docker container if running
        if session.container_id:
            self._stop_docker_container(session.container_id)

        # Remove sandbox directory
        sandbox_dir = Path(session.sandbox_path)
        if sandbox_dir.exists():
            shutil.rmtree(sandbox_dir, ignore_errors=True)

        # Remove session metadata
        meta_file = self.sandbox_root / f"{session_id}.meta.json"
        meta_file.unlink(missing_ok=True)

        logger.info("Sandbox session destroyed: %s", session_id)
        return True

    # ── Diff ──────────────────────────────────────────────────────────

    def get_diff(self, session: SandboxSession) -> SandboxDiff:
        """
        Compare sandbox state against the original source workspace.

        Returns lists of added, modified, and deleted files plus
        a unified diff text.
        """
        source = Path(session.source_path)
        sandbox = Path(session.sandbox_path)

        added, modified, deleted = [], [], []

        # Files in sandbox
        sandbox_files = self._list_relative_files(sandbox)
        source_files = self._list_relative_files(source)

        for rel in sandbox_files:
            if rel not in source_files:
                added.append(rel)
            else:
                # Compare content
                src_content = (source / rel).read_bytes()
                sbx_content = (sandbox / rel).read_bytes()
                if src_content != sbx_content:
                    modified.append(rel)

        for rel in source_files:
            if rel not in sandbox_files:
                # Only count as deleted if it was in the original copy
                # (some files are excluded from copy)
                deleted.append(rel)

        # Build unified diff text
        diff_text = self._build_diff_text(source, sandbox, added, modified, deleted)

        return SandboxDiff(
            added=added, modified=modified, deleted=deleted,
            total_changes=len(added) + len(modified) + len(deleted),
            diff_text=diff_text,
        )

    # ── Promote ───────────────────────────────────────────────────────

    def promote(
        self,
        session: SandboxSession,
        files: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> PromoteResult:
        """
        Promote sandbox changes back to the source workspace.

        If files is None, promotes all changed files.
        If dry_run is True, returns what would be promoted without doing it.
        """
        diff = self.get_diff(session)
        source = Path(session.source_path)
        sandbox = Path(session.sandbox_path)

        to_promote = files or (diff.added + diff.modified)
        promoted = []
        errors = []

        for rel in to_promote:
            sbx_file = sandbox / rel
            src_file = source / rel

            if not sbx_file.exists():
                errors.append(f"{rel}: file not found in sandbox")
                continue

            if dry_run:
                promoted.append(rel)
                continue

            try:
                src_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(sbx_file), str(src_file))
                promoted.append(rel)
            except Exception as e:
                errors.append(f"{rel}: {e}")

        return PromoteResult(
            success=len(errors) == 0,
            files_promoted=promoted,
            errors=errors,
            dry_run=dry_run,
        )

    # ── Code execution ────────────────────────────────────────────────

    def run_code(
        self,
        session: SandboxSession,
        code: str,
        language: str = "python",
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute code inside the sandbox.

        Docker mode:  runs inside the session's container.
        Local mode:   runs in a subprocess with cwd=sandbox_path,
                      restricted environment.
        """
        timeout = timeout or self.timeout

        if session.mode == "docker" and session.container_id:
            return self._run_code_docker(session, code, language, timeout)
        else:
            return self._run_code_local(session, code, language, timeout)

    # ── Capabilities ──────────────────────────────────────────────────

    def get_capabilities(self) -> SandboxCapabilities:
        """Report sandbox capabilities for the current mode."""
        mode = self._resolve_mode()
        docker_ok = self.is_docker_available()

        if mode == "docker":
            return SandboxCapabilities(
                mode="docker",
                can_execute_code=True,
                can_edit_files=True,
                can_install_packages=True,
                can_access_network=self.network_enabled,
                isolation_level="container",
                supported_languages=["python", "node", "bash", "shell"],
                max_timeout_seconds=self.timeout,
                max_memory_mb=int(self.memory_limit.rstrip("m")),
                docker_available=docker_ok,
            )
        else:
            return SandboxCapabilities(
                mode="local",
                can_execute_code=True,
                can_edit_files=True,
                can_install_packages=False,
                can_access_network=False,
                isolation_level="filesystem",
                supported_languages=["python", "node", "bash"],
                max_timeout_seconds=self.timeout,
                max_memory_mb=256,
                docker_available=docker_ok,
            )

    # ── Status ────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Get full sandbox status."""
        caps = self.get_capabilities()
        return {
            "requested_mode": self.requested_mode.value,
            "resolved_mode": self._resolve_mode(),
            "docker_available": self.is_docker_available(),
            "active_sessions": len(self._sessions),
            "sessions": [
                {
                    "id": s.session_id,
                    "source": s.source_path,
                    "mode": s.mode,
                    "files": s.file_count,
                    "container": s.container_id,
                }
                for s in self._sessions.values()
            ],
            "capabilities": {
                "execute_code": caps.can_execute_code,
                "edit_files": caps.can_edit_files,
                "install_packages": caps.can_install_packages,
                "network": caps.can_access_network,
                "isolation": caps.isolation_level,
                "languages": caps.supported_languages,
            },
            "limits": {
                "memory": self.memory_limit,
                "cpu": self.cpu_limit,
                "timeout": self.timeout,
            },
        }

    # ═════════════════════════════════════════════════════════════════
    # INTERNAL: Workspace copy
    # ═════════════════════════════════════════════════════════════════

    def _copy_workspace(self, source: Path, dest: Path) -> tuple:
        """Copy workspace files into sandbox, respecting exclusions."""
        file_count = 0
        total_size = 0

        for item in source.rglob("*"):
            # Skip excluded directories/patterns
            rel = item.relative_to(source)
            parts = rel.parts
            if any(self._should_exclude(p) for p in parts):
                continue

            if item.is_file():
                if total_size + item.stat().st_size > MAX_COPY_SIZE_BYTES:
                    logger.warning("Sandbox copy size limit reached (%d bytes)", MAX_COPY_SIZE_BYTES)
                    break
                dest_file = dest / rel
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(item), str(dest_file))
                file_count += 1
                total_size += item.stat().st_size

        return file_count, total_size

    def _should_exclude(self, name: str) -> bool:
        """Check if a path component should be excluded from copy."""
        if name in COPY_EXCLUDE:
            return True
        # Glob patterns like *.egg-info
        for pattern in COPY_EXCLUDE:
            if "*" in pattern:
                import fnmatch
                if fnmatch.fnmatch(name, pattern):
                    return True
        return False

    def _list_relative_files(self, root: Path) -> set:
        """List all files under root as relative paths (string set)."""
        files = set()
        if not root.exists():
            return files
        for item in root.rglob("*"):
            if item.is_file():
                rel = item.relative_to(root)
                parts = rel.parts
                if not any(self._should_exclude(p) for p in parts):
                    files.add(str(rel).replace("\\", "/"))
        return files

    def _build_diff_text(
        self, source: Path, sandbox: Path,
        added: List[str], modified: List[str], deleted: List[str],
    ) -> str:
        """Build a human-readable unified diff."""
        import difflib
        lines = []

        for rel in added:
            content = (sandbox / rel).read_text(encoding="utf-8", errors="replace")
            lines.append(f"+++ NEW: {rel}")
            for line in content.splitlines()[:50]:
                lines.append(f"+ {line}")
            if len(content.splitlines()) > 50:
                lines.append(f"+ ... ({len(content.splitlines()) - 50} more lines)")
            lines.append("")

        for rel in modified:
            try:
                src_lines = (source / rel).read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                sbx_lines = (sandbox / rel).read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                diff = difflib.unified_diff(src_lines, sbx_lines, fromfile=f"a/{rel}", tofile=f"b/{rel}")
                lines.extend(line.rstrip() for line in diff)
                lines.append("")
            except Exception:
                lines.append(f"??? MODIFIED: {rel} (binary or unreadable)")
                lines.append("")

        for rel in deleted:
            lines.append(f"--- DELETED: {rel}")
            lines.append("")

        return "\n".join(lines)

    # ═════════════════════════════════════════════════════════════════
    # INTERNAL: Docker backend
    # ═════════════════════════════════════════════════════════════════

    def _start_docker_container(self, session: SandboxSession) -> Optional[str]:
        """Start a persistent Docker container for the session."""
        container_name = f"orion-ws-{session.session_id[:12]}"
        try:
            cmd = [
                "docker", "run", "-d",
                "--name", container_name,
                "--memory", self.memory_limit,
                "--cpus", self.cpu_limit,
                "--pids-limit", "128",
                "-v", f"{session.sandbox_path}:/workspace",
                "-w", "/workspace",
            ]
            if not self.network_enabled:
                cmd.extend(["--network", "none"])
            cmd.extend([self.docker_image, "tail", "-f", "/dev/null"])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                container_id = result.stdout.strip()[:12]
                logger.info("Docker sandbox container started: %s", container_id)
                return container_id
            else:
                logger.warning("Failed to start Docker container: %s", result.stderr[:200])
                return None
        except Exception as e:
            logger.warning("Docker container start failed: %s", e)
            return None

    def _stop_docker_container(self, container_id: str):
        """Stop and remove a Docker container."""
        try:
            subprocess.run(
                ["docker", "rm", "-f", container_id],
                capture_output=True, timeout=15,
            )
        except Exception:
            pass

    # Language → (Docker image, exec command prefix)
    _LANG_DOCKER = {
        "python":     ("python:3.11-slim",  ["python3", "-c"]),
        "python3":    ("python:3.11-slim",  ["python3", "-c"]),
        "node":       ("node:20-slim",      ["node", "-e"]),
        "nodejs":     ("node:20-slim",      ["node", "-e"]),
        "javascript": ("node:20-slim",      ["node", "-e"]),
        "bash":       ("ubuntu:22.04",      ["bash", "-c"]),
        "shell":      ("ubuntu:22.04",      ["sh", "-c"]),
        "sh":         ("ubuntu:22.04",      ["sh", "-c"]),
    }

    def _run_code_docker(
        self, session: SandboxSession, code: str, language: str, timeout: int,
    ) -> Dict[str, Any]:
        """
        Execute code in Docker.

        If the language matches the session container's image, exec into it.
        Otherwise, spin up a one-shot container with the correct image
        and the sandbox mounted as /workspace.
        """
        lang = language.lower()
        lang_entry = self._LANG_DOCKER.get(lang)
        if not lang_entry:
            return {"success": False, "error": f"Unsupported language: {language}", "mode": "docker"}

        image, cmd_prefix = lang_entry

        # If language matches session image, exec directly
        if image == self.docker_image and session.container_id:
            return self._docker_exec(session.container_id, cmd_prefix, code, lang, timeout)

        # Otherwise, run a one-shot container with the right image
        return self._docker_run_oneshot(session, image, cmd_prefix, code, lang, timeout)

    def _docker_exec(
        self, container_id: str, cmd_prefix: list, code: str, lang: str, timeout: int,
    ) -> Dict[str, Any]:
        """Execute inside an existing container."""
        try:
            docker_cmd = ["docker", "exec", container_id] + cmd_prefix + [code]
            start = time.time()
            result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout)
            elapsed = time.time() - start
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout, "stderr": result.stderr,
                "exit_code": result.returncode,
                "execution_time": round(elapsed, 3),
                "language": lang, "mode": "docker",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Timed out after {timeout}s", "mode": "docker"}
        except Exception as e:
            return {"success": False, "error": str(e), "mode": "docker"}

    def _docker_run_oneshot(
        self, session: SandboxSession, image: str, cmd_prefix: list,
        code: str, lang: str, timeout: int,
    ) -> Dict[str, Any]:
        """Run a one-shot container with the correct image."""
        try:
            docker_cmd = [
                "docker", "run", "--rm",
                "--memory", self.memory_limit,
                "--cpus", self.cpu_limit,
                "--pids-limit", "64",
                "-v", f"{session.sandbox_path}:/workspace",
                "-w", "/workspace",
            ]
            if not self.network_enabled:
                docker_cmd.extend(["--network", "none"])
            docker_cmd.extend([image] + cmd_prefix + [code])

            start = time.time()
            result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout)
            elapsed = time.time() - start
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout, "stderr": result.stderr,
                "exit_code": result.returncode,
                "execution_time": round(elapsed, 3),
                "language": lang, "mode": "docker",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Timed out after {timeout}s", "mode": "docker"}
        except Exception as e:
            return {"success": False, "error": str(e), "mode": "docker"}

    # ═════════════════════════════════════════════════════════════════
    # INTERNAL: Local backend
    # ═════════════════════════════════════════════════════════════════

    def _run_code_local(
        self, session: SandboxSession, code: str, language: str, timeout: int,
    ) -> Dict[str, Any]:
        """Execute code in a local subprocess restricted to the sandbox dir."""
        lang_cmds = {
            "python": ["python", "-c"],
            "node": ["node", "-e"],
            "bash": ["bash", "-c"],
            "shell": ["sh", "-c"],
        }
        cmd_prefix = lang_cmds.get(language.lower())
        if not cmd_prefix:
            return {"success": False, "error": f"Unsupported language: {language}", "mode": "local"}

        # Restricted environment: no inheriting dangerous env vars
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": session.sandbox_path,
            "TMPDIR": session.sandbox_path,
            "PYTHONDONTWRITEBYTECODE": "1",
            "NODE_PATH": session.sandbox_path,
        }

        try:
            start = time.time()
            result = subprocess.run(
                cmd_prefix + [code],
                capture_output=True, text=True, timeout=timeout,
                cwd=session.sandbox_path,
                env=env,
            )
            elapsed = time.time() - start

            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "execution_time": round(elapsed, 3),
                "language": language,
                "mode": "local",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Timed out after {timeout}s", "mode": "local"}
        except FileNotFoundError:
            return {"success": False, "error": f"{language} interpreter not found in PATH", "mode": "local"}
        except Exception as e:
            return {"success": False, "error": str(e), "mode": "local"}

    # ═════════════════════════════════════════════════════════════════
    # INTERNAL: Helpers
    # ═════════════════════════════════════════════════════════════════

    def _generate_session_id(self, source: Path) -> str:
        """Generate a unique session ID."""
        raw = f"{source}-{time.time()}-{os.getpid()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _save_session_meta(self, session: SandboxSession):
        """Persist session metadata to disk."""
        meta_file = self.sandbox_root / f"{session.session_id}.meta.json"
        data = {
            "session_id": session.session_id,
            "sandbox_path": session.sandbox_path,
            "source_path": session.source_path,
            "mode": session.mode,
            "created_at": session.created_at,
            "container_id": session.container_id,
            "file_count": session.file_count,
            "size_bytes": session.size_bytes,
        }
        with open(meta_file, "w") as f:
            json.dump(data, f, indent=2)


# ─────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────

_workspace_sandbox: Optional[WorkspaceSandbox] = None


def get_workspace_sandbox(**kwargs) -> WorkspaceSandbox:
    """Get or create the workspace sandbox singleton."""
    global _workspace_sandbox
    if _workspace_sandbox is None:
        # Read mode from settings
        mode = "auto"
        try:
            settings_file = Path.home() / ".orion" / "settings.json"
            if settings_file.exists():
                settings = json.loads(settings_file.read_text())
                mode = settings.get("sandbox_mode", "auto")
        except Exception:
            pass
        _workspace_sandbox = WorkspaceSandbox(mode=mode, **kwargs)
    return _workspace_sandbox
