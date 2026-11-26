"""Tests for the PlaylistManager."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from pikaraoke.lib.playlist_manager import MAX_NAME_LENGTH, PlaylistManager


@pytest.fixture
def temp_playlist_file():
    """Create a path for a playlist file that does not exist yet."""
    directory = tempfile.mkdtemp()
    path = os.path.join(directory, "playlists.json")
    yield path
    if os.path.exists(path):
        os.remove(path)
    os.rmdir(directory)


def test_starts_empty_when_file_missing(temp_playlist_file):
    """A fresh install has no playlists and no file on disk."""
    manager = PlaylistManager(temp_playlist_file)
    assert manager.names() == []
    assert not os.path.exists(temp_playlist_file)


def test_save_and_get(temp_playlist_file):
    manager = PlaylistManager(temp_playlist_file)
    success, message = manager.save("Party", ["/songs/a.mp4", "/songs/b.mp4"])

    assert success is True
    assert "Party" in message
    assert manager.get("Party") == ["/songs/a.mp4", "/songs/b.mp4"]


def test_save_persists_across_instances(temp_playlist_file):
    """Playlists survive a restart."""
    PlaylistManager(temp_playlist_file).save("Party", ["/songs/a.mp4"])

    reloaded = PlaylistManager(temp_playlist_file)
    assert reloaded.get("Party") == ["/songs/a.mp4"]


def test_save_overwrites_existing_playlist(temp_playlist_file):
    manager = PlaylistManager(temp_playlist_file)
    manager.save("Party", ["/songs/a.mp4"])
    success, message = manager.save("Party", ["/songs/b.mp4"])

    assert success is True
    assert "Updated" in message
    assert manager.get("Party") == ["/songs/b.mp4"]
    assert manager.names() == ["Party"]


def test_save_strips_whitespace_from_name(temp_playlist_file):
    manager = PlaylistManager(temp_playlist_file)
    manager.save("  Party  ", ["/songs/a.mp4"])

    assert manager.get("Party") == ["/songs/a.mp4"]


def test_save_removes_duplicates_but_keeps_order(temp_playlist_file):
    manager = PlaylistManager(temp_playlist_file)
    manager.save("Party", ["/songs/b.mp4", "/songs/a.mp4", "/songs/b.mp4"])

    assert manager.get("Party") == ["/songs/b.mp4", "/songs/a.mp4"]


@pytest.mark.parametrize("name", ["", "   "])
def test_save_rejects_empty_name(temp_playlist_file, name):
    manager = PlaylistManager(temp_playlist_file)
    success, message = manager.save(name, ["/songs/a.mp4"])

    assert success is False
    assert "empty" in message.lower()
    assert manager.names() == []


def test_save_rejects_overlong_name(temp_playlist_file):
    manager = PlaylistManager(temp_playlist_file)
    success, _message = manager.save("x" * (MAX_NAME_LENGTH + 1), ["/songs/a.mp4"])

    assert success is False
    assert manager.names() == []


def test_save_rejects_empty_song_list(temp_playlist_file):
    manager = PlaylistManager(temp_playlist_file)
    success, message = manager.save("Party", [])

    assert success is False
    assert "no songs" in message.lower()


def test_get_unknown_playlist_returns_none(temp_playlist_file):
    assert PlaylistManager(temp_playlist_file).get("Nope") is None


def test_delete(temp_playlist_file):
    manager = PlaylistManager(temp_playlist_file)
    manager.save("Party", ["/songs/a.mp4"])

    success, message = manager.delete("Party")

    assert success is True
    assert "Party" in message
    assert manager.get("Party") is None
    assert PlaylistManager(temp_playlist_file).names() == []


def test_delete_unknown_playlist_fails(temp_playlist_file):
    manager = PlaylistManager(temp_playlist_file)
    success, message = manager.delete("Nope")

    assert success is False
    assert "Nope" in message


def test_names_are_sorted_case_insensitively(temp_playlist_file):
    manager = PlaylistManager(temp_playlist_file)
    for name in ("zebra", "Apple", "banana"):
        manager.save(name, ["/songs/a.mp4"])

    assert manager.names() == ["Apple", "banana", "zebra"]


def test_corrupt_file_does_not_raise(temp_playlist_file):
    """A damaged playlist file must not stop the app from starting."""
    with open(temp_playlist_file, "w", encoding="utf-8") as f:
        f.write("{not valid json")

    manager = PlaylistManager(temp_playlist_file)
    assert manager.names() == []


def test_malformed_entries_are_ignored(temp_playlist_file):
    """Entries that are not name -> list of paths are dropped on read."""
    with open(temp_playlist_file, "w", encoding="utf-8") as f:
        json.dump({"good": ["/songs/a.mp4", 5], "bad": "not-a-list"}, f)

    manager = PlaylistManager(temp_playlist_file)
    assert manager.names() == ["good"]
    assert manager.get("good") == ["/songs/a.mp4"]


def test_non_dict_file_is_ignored(temp_playlist_file):
    with open(temp_playlist_file, "w", encoding="utf-8") as f:
        json.dump(["not", "a", "dict"], f)

    assert PlaylistManager(temp_playlist_file).names() == []


def test_unicode_names_and_paths_round_trip(temp_playlist_file):
    manager = PlaylistManager(temp_playlist_file)
    manager.save("Fiesta 🎤", ["/songs/Héroes del Silencio - Maldito duende.mp4"])

    reloaded = PlaylistManager(temp_playlist_file)
    assert reloaded.get("Fiesta 🎤") == ["/songs/Héroes del Silencio - Maldito duende.mp4"]
