from pathlib import Path
from subprocess import CompletedProcess

from danmaku_meme_finder import publication


def test_publish_curated_data_stages_only_requested_files(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    memes = tmp_path / "data" / "memes.json"
    catalog = tmp_path / "data" / "catalog.json"
    memes.parent.mkdir()
    memes.write_text("{}", encoding="utf-8")
    catalog.write_text("{}", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command[1:4] == ["diff", "--cached", "--quiet"]:
            return CompletedProcess(command, 1, "", "")
        if command[1:3] == ["branch", "--show-current"]:
            return CompletedProcess(command, 0, "main\n", "")
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(publication.subprocess, "run", fake_run)
    message = publication.publish_curated_data(tmp_path, [memes, catalog], 2)

    assert message == "Curate 2 meme candidates"
    assert ["git", "add", "--", "data\\memes.json", "data\\catalog.json"] in calls
    assert ["git", "push", "origin", "main"] in calls
