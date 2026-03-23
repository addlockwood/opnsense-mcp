from __future__ import annotations

import json
import os
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from opnsense_mcp.config import AppConfig
from opnsense_mcp.errors import WorkspaceError
from opnsense_mcp.models import ChangeRecordMetadata, ManagedState, SnapshotResult

RECORD_BEGIN = "<!-- opnsense-mcp-record-begin"
RECORD_END = "opnsense-mcp-record-end -->"


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path
    history_dir: Path
    snapshots_dir: Path
    current_snapshot: Path


class WorkspaceManager:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        root = config.workspace_path
        self.paths = WorkspacePaths(
            root=root,
            history_dir=root / "history",
            snapshots_dir=root / "snapshots",
            current_snapshot=root / "snapshots" / "current-config.xml",
        )

    def ensure_layout(self) -> None:
        self.paths.root.mkdir(parents=True, exist_ok=True)
        self.paths.history_dir.mkdir(parents=True, exist_ok=True)
        self.paths.snapshots_dir.mkdir(parents=True, exist_ok=True)

    def capture_snapshot(self, xml_text: str) -> SnapshotResult:
        self.ensure_layout()
        ET.fromstring(xml_text)
        encoded = xml_text.encode("utf-8")
        self.paths.current_snapshot.write_bytes(encoded)
        return SnapshotResult(
            path=str(self.paths.current_snapshot),
            valid_xml=True,
            bytes_written=len(encoded),
        )

    def write_history_record(self, metadata: ChangeRecordMetadata) -> Path:
        self.ensure_layout()
        slug = _slugify(metadata.summary)
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        path = self.paths.history_dir / f"{timestamp}-{slug}.md"
        json_blob = metadata.model_dump(mode="json")
        rendered = "\n".join(
            [
                RECORD_BEGIN,
                json.dumps(json_blob, indent=2, sort_keys=True),
                RECORD_END,
                f"# {metadata.summary}",
                "",
                f"- Applied at: {metadata.applied_at}",
                f"- Approved by: {metadata.approved_by}",
                f"- Snapshot: `{metadata.snapshot_path}`",
                f"- Rollback target: `{metadata.rollback_target or 'none'}`",
                "",
                "## Requested Change",
                "",
                metadata.requested_change,
                "",
                "## Validation",
                "",
                *[
                    f"- {'PASS' if result.ok else 'FAIL'}: {result.message}"
                    for result in metadata.validation_results
                ],
            ]
        )
        path.write_text(rendered + "\n", encoding="utf-8")
        return path

    def collect_managed_state(
        self,
        records: dict[str, dict[str, list[dict[str, str]]]],
    ) -> ManagedState:
        return ManagedState(records=records)

    def read_latest_record_from_ref(self, git_ref: str) -> ChangeRecordMetadata:
        names = self._git(
            "ls-tree",
            "-r",
            "--name-only",
            git_ref,
            "history",
        ).splitlines()
        history_files = sorted(name for name in names if name.endswith(".md"))
        if not history_files:
            raise WorkspaceError(f"No history records found at git ref '{git_ref}'")
        latest = history_files[-1]
        content = self._git("show", f"{git_ref}:{latest}")
        return parse_history_record(content)

    def current_head(self) -> str | None:
        try:
            return self._git("rev-parse", "HEAD").strip()
        except WorkspaceError:
            return None

    def commit_files(self, files: Iterable[Path], message: str) -> str:
        self.ensure_layout()
        env = {
            "GIT_AUTHOR_NAME": self._config.git_author_name,
            "GIT_AUTHOR_EMAIL": self._config.git_author_email,
            "GIT_COMMITTER_NAME": self._config.git_author_name,
            "GIT_COMMITTER_EMAIL": self._config.git_author_email,
        }
        if not (self.paths.root / ".git").exists():
            self._run_git("init", env=env)
        for path in files:
            relative = path.relative_to(self.paths.root)
            self._run_git("add", str(relative), env=env)
        self._run_git("commit", "-m", message, env=env)
        return self._git("rev-parse", "HEAD")

    def _git(self, *args: str) -> str:
        return self._run_git(*args)

    def _run_git(self, *args: str, env: dict[str, str] | None = None) -> str:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        result = subprocess.run(
            ["git", *args],
            cwd=self.paths.root,
            env=merged_env,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise WorkspaceError(message or f"git {' '.join(args)} failed")
        return result.stdout.strip()


def parse_history_record(content: str) -> ChangeRecordMetadata:
    try:
        start = content.index(RECORD_BEGIN) + len(RECORD_BEGIN)
        end = content.index(RECORD_END, start)
    except ValueError as exc:
        raise WorkspaceError("Could not parse history metadata block") from exc
    json_text = content[start:end].strip()
    return ChangeRecordMetadata.model_validate_json(json_text)


def _slugify(value: str) -> str:
    pieces = []
    for char in value.lower():
        if char.isalnum():
            pieces.append(char)
        elif pieces and pieces[-1] != "-":
            pieces.append("-")
    return "".join(pieces).strip("-") or "change"
