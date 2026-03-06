#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _to_slug(text: str) -> str:
    lowered = text.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "_", lowered)
    lowered = re.sub(r"_+", "_", lowered).strip("_")
    return lowered or "melody"


def _to_title(slug: str) -> str:
    words = [part for part in re.split(r"[_\-\s]+", slug) if part]
    return " ".join(word.capitalize() for word in words) or "Melody"


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


def _derive_defaults(file_name: str, instrument_name: str) -> tuple[str, str]:
    stem = Path(file_name).stem
    normalized = stem.lower()
    prefix = f"builtin_{instrument_name}_"
    if normalized.startswith(prefix):
        raw_slug = normalized[len(prefix) :]
    else:
        raw_slug = normalized
    slug = _to_slug(raw_slug)
    return f"builtin:{instrument_name}:{slug}", _to_title(slug)


def _normalize_existing_entry(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(entry)
    if isinstance(normalized.get("sourceTempoBpm"), float):
        normalized["sourceTempoBpm"] = int(round(normalized["sourceTempoBpm"]))
    return normalized


def build_manifest(midi_dir: Path, now_iso: str) -> dict[str, Any]:
    manifest_path = midi_dir / "manifest.json"
    existing_manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Failed to parse existing manifest.json: {exc}") from exc

    existing_entries: dict[str, dict[str, Any]] = {}
    for raw in existing_manifest.get("melodies", []):
        if not isinstance(raw, dict):
            continue
        file_name = raw.get("fileName")
        if not isinstance(file_name, str) or not file_name.strip():
            continue
        existing_entries[file_name.strip().lower()] = _normalize_existing_entry(raw)

    midi_files = sorted(
        [path for path in midi_dir.rglob("*.mid") if path.is_file()],
        key=lambda file_path: file_path.as_posix().lower(),
    )

    entries: list[dict[str, Any]] = []
    for midi_file in midi_files:
        file_name = midi_file.name
        existing = existing_entries.get(file_name.lower())
        if existing:
            entry = dict(existing)
            entry["fileName"] = file_name
        else:
            instrument_name = _infer_instrument(midi_file.relative_to(midi_dir))
            entry_id, entry_name = _derive_defaults(file_name, instrument_name)
            entry = {
                "id": entry_id,
                "name": entry_name,
                "instrumentName": instrument_name,
                "fileName": file_name,
            }

        instrument_name = str(entry.get("instrumentName") or "").strip().lower()
        if instrument_name not in {"guitar", "ukulele"}:
            instrument_name = _infer_instrument(midi_file.relative_to(midi_dir))

        entry_id = str(entry.get("id") or "").strip()
        entry_name = str(entry.get("name") or "").strip()
        if not entry_id or not entry_id.startswith("builtin:"):
            inferred_id, _ = _derive_defaults(file_name, instrument_name)
            entry_id = inferred_id
        if not entry_name:
            _, inferred_name = _derive_defaults(file_name, instrument_name)
            entry_name = inferred_name

        normalized: dict[str, Any] = {
            "id": entry_id,
            "name": entry_name,
            "instrumentName": instrument_name,
            "fileName": file_name,
        }

        if isinstance(entry.get("sourceTempoBpm"), (int, float)):
            normalized["sourceTempoBpm"] = int(round(float(entry["sourceTempoBpm"])))
        if isinstance(entry.get("sourceTimeSignature"), str) and entry["sourceTimeSignature"].strip():
            normalized["sourceTimeSignature"] = entry["sourceTimeSignature"].strip()
        if isinstance(entry.get("tabText"), str) and entry["tabText"].strip():
            normalized["tabText"] = entry["tabText"]

        entries.append(normalized)

    entries.sort(key=lambda item: str(item.get("id", "")).lower())

    version = existing_manifest.get("version")
    normalized_version = int(version) if isinstance(version, int) and version > 0 else 1

    return {
        "version": normalized_version,
        "generatedAtIso": now_iso,
        "melodies": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate MIDI/manifest.json for the filestorage repo.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root path (defaults to script parent parent).",
    )
    args = parser.parse_args()

    repo_root: Path = args.repo_root.resolve()
    midi_dir = repo_root / "MIDI"
    if not midi_dir.exists() or not midi_dir.is_dir():
        raise RuntimeError(f'MIDI directory was not found at "{midi_dir}".')

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    manifest = build_manifest(midi_dir, now_iso)
    manifest_path = midi_dir / "manifest.json"
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    manifest_path.write_text(payload, encoding="utf-8")

    print(f"Generated {manifest_path} with {len(manifest['melodies'])} entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
