"""Named playlists of library songs, persisted to disk."""

import json
import logging
import os

from pikaraoke.lib.get_platform import get_data_directory

MAX_NAME_LENGTH = 80


class PlaylistManager:
    """Store and retrieve named playlists.

    Playlists are song file paths only. Titles and metadata are resolved from
    the library at load time, so renaming a song does not leave a playlist
    holding a stale title.
    """

    def __init__(self, playlists_file_path: str = "playlists.json") -> None:
        """Initialize with the playlist file path.

        Args:
            playlists_file_path: Path to the playlist file (relative paths go in
                the data directory, matching PreferenceManager).
        """
        if os.path.isabs(playlists_file_path):
            self.playlists_file_path = playlists_file_path
        else:
            self.playlists_file_path = os.path.join(get_data_directory(), playlists_file_path)

        self._playlists: dict[str, list[str]] = self._read()
        logging.debug(f"Using playlist file: {self.playlists_file_path}")

    def _read(self) -> dict[str, list[str]]:
        """Load playlists from disk, tolerating a missing or unreadable file."""
        if not os.path.exists(self.playlists_file_path):
            return {}

        try:
            with open(self.playlists_file_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            # A corrupt file should not stop the app from starting. Keep the file
            # on disk so the user can recover it by hand.
            logging.error(f"Could not read playlists from {self.playlists_file_path}: {e}")
            return {}

        if not isinstance(data, dict):
            logging.error(f"Ignoring malformed playlist file: {self.playlists_file_path}")
            return {}

        return {
            name: [song for song in songs if isinstance(song, str)]
            for name, songs in data.items()
            if isinstance(name, str) and isinstance(songs, list)
        }

    def _write(self) -> bool:
        """Persist playlists to disk. Returns False if the write failed."""
        try:
            os.makedirs(os.path.dirname(self.playlists_file_path), exist_ok=True)
            with open(self.playlists_file_path, "w", encoding="utf-8") as f:
                json.dump(self._playlists, f, indent=2, ensure_ascii=False)
            return True
        except OSError as e:
            logging.error(f"Could not write playlists to {self.playlists_file_path}: {e}")
            return False

    @property
    def playlists(self) -> dict[str, list[str]]:
        """All playlists, keyed by name."""
        return self._playlists

    def names(self) -> list[str]:
        """Playlist names, sorted case-insensitively for display."""
        return sorted(self._playlists, key=str.casefold)

    def get(self, name: str) -> list[str] | None:
        """Return a playlist's song paths, or None if no such playlist."""
        return self._playlists.get(name)

    def save(self, name: str, songs: list[str]) -> tuple[bool, str]:
        """Create or overwrite a playlist. Returns (success, message)."""
        name = name.strip()
        if not name:
            return False, "Playlist name cannot be empty"
        if len(name) > MAX_NAME_LENGTH:
            return False, f"Playlist name cannot be longer than {MAX_NAME_LENGTH} characters"
        if not songs:
            return False, "Cannot save a playlist with no songs"

        # Preserve order while dropping duplicates, so a playlist built from the
        # queue matches what was queued.
        unique_songs = list(dict.fromkeys(songs))

        existed = name in self._playlists
        self._playlists[name] = unique_songs

        if not self._write():
            return False, "Could not save the playlist to disk"

        logging.info(
            f"{'Updated' if existed else 'Created'} playlist '{name}' with {len(unique_songs)} song(s)"
        )
        return True, f"{'Updated' if existed else 'Saved'} playlist '{name}'"

    def delete(self, name: str) -> tuple[bool, str]:
        """Delete a playlist. Returns (success, message)."""
        if name not in self._playlists:
            return False, f"No playlist named '{name}'"

        del self._playlists[name]
        if not self._write():
            return False, "Could not update the playlist file on disk"

        logging.info(f"Deleted playlist '{name}'")
        return True, f"Deleted playlist '{name}'"
