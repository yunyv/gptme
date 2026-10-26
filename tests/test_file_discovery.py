"""Real Git path discovery and the scout's line-delimited file tree."""

import os
import subprocess
from pathlib import Path

import pytest

from gptme.context.scout import _advertised_resolved, _build_file_tree
from gptme.context.selector.file_selector import get_workspace_files
from gptme.util.git_cmd import GIT_CMD


def _track_files(workspace: Path, names: list[str]) -> list[Path]:
    subprocess.run([GIT_CMD, "init", "-q", str(workspace)], check=True)
    paths = [workspace / name for name in names]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("pass\n", encoding="utf-8")
    subprocess.run([GIT_CMD, "add", "--", *names], cwd=workspace, check=True)
    return paths


@pytest.mark.parametrize("quote_path", ["true", "false"])
def test_discovers_tracked_paths_without_git_quoting(
    tmp_path: Path, quote_path: str
) -> None:
    names = ["plain.py", "café.py", "中文.py", ".hidden.py", "sub/spaced name.py"]
    paths = _track_files(tmp_path, names)
    subprocess.run(
        [GIT_CMD, "config", "core.quotePath", quote_path],
        cwd=tmp_path,
        check=True,
    )

    assert set(get_workspace_files(tmp_path)) == set(paths)
    assert _build_file_tree(tmp_path).splitlines() == sorted(names)


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only filename characters/bytes")
def test_preserves_quoted_characters_and_line_breaks(
    tmp_path: Path,
) -> None:
    names = [
        'quote".py',
        "back\\slash.py",
        "tab\t.py",
        "cr\r.py",
        "lf\n.py",
    ]
    paths = _track_files(tmp_path, names)

    assert set(get_workspace_files(tmp_path)) == set(paths)


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only filename bytes")
def test_non_utf8_filename_does_not_break_or_alias_other_paths(tmp_path: Path) -> None:
    paths = _track_files(
        tmp_path,
        ["plain.py", "café.py", "invalid-�.py", os.fsdecode(b"invalid-\xff.py")],
    )

    assert set(get_workspace_files(tmp_path)) == set(paths[:-1])
    assert _build_file_tree(tmp_path).splitlines() == sorted(p.name for p in paths[:-1])


def test_discovery_keeps_subdirectory_paths_and_skips_missing_files(
    tmp_path: Path,
) -> None:
    paths = _track_files(tmp_path, ["sub/café.py", "sub/missing.py", "outside.py"])
    paths[1].unlink()
    (tmp_path / "sub" / "untracked.py").write_text("pass\n", encoding="utf-8")

    assert get_workspace_files(tmp_path / "sub") == [paths[0]]


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only filename characters")
@pytest.mark.parametrize(
    "separator",
    [
        "\n",
        "\r",
        "\r\n",
        "\v",
        "\f",
        "\x1c",
        "\x1d",
        "\x1e",
        "\x85",
        "\u2028",
        "\u2029",
    ],
)
@pytest.mark.parametrize("suffix", ["plain.py", ""])
def test_scout_does_not_advertise_fragments_of_multiline_filenames(
    tmp_path: Path, separator: str, suffix: str
) -> None:
    _track_files(tmp_path, [f"00-untracked.py{separator}{suffix}", "plain.py"])
    (tmp_path / "00-untracked.py").write_text("not tracked\n", encoding="utf-8")

    tree = _build_file_tree(tmp_path, max_paths=1)

    assert tree == "plain.py"
    assert set(_advertised_resolved(tmp_path, tree)) == {"plain.py"}
