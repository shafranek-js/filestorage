#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SUPPORTED_SCALE_SUFFIXES: dict[str, str] = {
    ".gp": "gp",
    ".gp3": "gp3",
    ".gp4": "gp4",
    ".gp5": "gp5",
    ".gpx": "gpx",
    ".gp7": "gp7",
}


def _to_slug(text: str) -> str:
    lowered = text.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "_", lowered)
    lowered = re.sub(r"_+", "_", lowered).strip("_")
    return lowered or "exercise"


def _infer_instrument(path: Path) -> str:
    parent_parts = [part.lower() for part in path.parts]
    if "ukulele" in parent_parts:
        return "ukulele"
    if "guitar" in parent_parts:
        return "guitar"

    stem = path.stem.lower()
    if "ukulele" in stem:
        return "ukulele"
    if "guitar" in stem:
        return "guitar"
    return "guitar"


def _strip_date_suffix(text: str) -> str:
    return re.sub(r"-\d{2}-\d{2}-\d{4}$", "", text, flags=re.IGNORECASE).strip()


def _normalize_display_name(file_name: str) -> str:
    stem = Path(file_name).stem.strip()
    stem = re.sub(r"^misc\.\s*scales-", "", stem, flags=re.IGNORECASE).strip()
    stem = _strip_date_suffix(stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem or Path(file_name).stem.strip() or "Exercise"


def _derive_defaults(relative_path: Path) -> tuple[str, str, str]:
    instrument_name = _infer_instrument(relative_path)
    display_name = _normalize_display_name(relative_path.name)
    slug = _to_slug(display_name)
    return f"builtin-exercise:{instrument_name}:{slug}", display_name, instrument_name


def _normalize_existing_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return dict(entry)


def _resolve_source_format(path: Path) -> str:
    return SUPPORTED_SCALE_SUFFIXES.get(path.suffix.lower(), "gp")


def build_manifest(scales_dir: Path, now_iso: str) -> dict[str, Any]:
    manifest_path = scales_dir / "manifest.json"
    existing_manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Failed to parse existing scales manifest.json: {exc}") from exc

    existing_entries: dict[str, dict[str, Any]] = {}
    for raw in existing_manifest.get("exercises", []):
        if not isinstance(raw, dict):
            continue
        relative_path = raw.get("relativePath")
        file_name = raw.get("fileName")
        if isinstance(relative_path, str) and relative_path.strip():
            existing_entries[relative_path.strip().lower()] = _normalize_existing_entry(raw)
            continue
        if isinstance(file_name, str) and file_name.strip():
            existing_entries[file_name.strip().lower()] = _normalize_existing_entry(raw)

    scale_files = sorted(
        [
            path
            for path in scales_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_SCALE_SUFFIXES
        ],
        key=lambda file_path: file_path.as_posix().lower(),
    )

    entries: list[dict[str, Any]] = []
    for scale_file in scale_files:
        relative_path = scale_file.relative_to(scales_dir)
        relative_path_text = relative_path.as_posix()
        existing = existing_entries.get(relative_path_text.lower()) or existing_entries.get(scale_file.name.lower())
        inferred_source_format = _resolve_source_format(scale_file)

        if existing:
            entry = dict(existing)
            entry["fileName"] = scale_file.name
            entry["relativePath"] = relative_path_text
        else:
            entry_id, entry_name, instrument_name = _derive_defaults(relative_path)
            entry = {
                "id": entry_id,
                "name": entry_name,
                "instrumentName": instrument_name,
                "fileName": scale_file.name,
                "relativePath": relative_path_text,
                "sourceFormat": inferred_source_format,
            }

        instrument_name = str(entry.get("instrumentName") or "").strip().lower()
        if instrument_name not in {"guitar", "ukulele"}:
            instrument_name = _infer_instrument(relative_path)

        entry_id = str(entry.get("id") or "").strip()
        entry_name = str(entry.get("name") or "").strip()
        if not entry_id or not entry_id.startswith("builtin-exercise:"):
            inferred_id, _, _ = _derive_defaults(relative_path)
            entry_id = inferred_id
        if not entry_name:
            _, inferred_name, _ = _derive_defaults(relative_path)
            entry_name = inferred_name
        source_format = str(entry.get("sourceFormat") or "").strip().lower()
        if source_format not in set(SUPPORTED_SCALE_SUFFIXES.values()):
            source_format = inferred_source_format

        normalized: dict[str, Any] = {
            "id": entry_id,
            "name": entry_name,
            "instrumentName": instrument_name,
            "fileName": scale_file.name,
            "relativePath": relative_path_text,
            "sourceFormat": source_format,
        }
        entries.append(normalized)

    entries.sort(key=lambda item: str(item.get("id", "")).lower())

    version = existing_manifest.get("version")
    normalized_version = int(version) if isinstance(version, int) and version > 0 else 1

    return {
        "version": normalized_version,
        "generatedAtIso": now_iso,
        "exercises": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate MIDI/Scales/manifest.json for the filestorage repo.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root path (defaults to script parent parent).",
    )
    args = parser.parse_args()

    repo_root: Path = args.repo_root.resolve()
    scales_dir = repo_root / "MIDI" / "Scales"
    if not scales_dir.exists() or not scales_dir.is_dir():
        raise RuntimeError(f'Scales directory was not found at "{scales_dir}".')

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    manifest = build_manifest(scales_dir, now_iso)
    manifest_path = scales_dir / "manifest.json"
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    manifest_path.write_text(payload, encoding="utf-8")

    print(f"Generated {manifest_path} with {len(manifest['exercises'])} entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
