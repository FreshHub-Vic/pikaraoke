"""Saved playlist routes."""

from __future__ import annotations

import os

import flask_babel
from flask import flash, redirect, render_template, request, url_for
from flask_smorest import Blueprint
from marshmallow import Schema, fields

from pikaraoke.lib.current_app import (
    broadcast_event,
    get_karaoke_instance,
    get_site_name,
    is_admin,
)

_ = flask_babel.gettext

playlists_bp = Blueprint("playlists", __name__)


class SavePlaylistForm(Schema):
    name = fields.String(required=True, metadata={"description": "Name of the playlist"})
    songs = fields.List(
        fields.String(),
        load_default=None,
        metadata={"description": "Song paths. Omit to save the current queue."},
    )


class LoadPlaylistQuery(Schema):
    mode = fields.String(
        load_default="append",
        metadata={"description": "'append' to add to the queue, 'replace' to swap it out"},
    )


def _playlist_songs_with_titles(k, song_paths: list[str]) -> list[dict]:
    """Pair song paths with display titles, flagging any missing from the library."""
    return [
        {
            "file": path,
            "title": k.song_manager.filename_from_path(path, remove_youtube_id=True),
            "missing": not os.path.exists(path),
        }
        for path in song_paths
    ]


@playlists_bp.route("/playlists")
def playlists():
    """Playlist page: saved playlists and the playlist editor."""
    k = get_karaoke_instance()
    saved = {
        name: _playlist_songs_with_titles(k, songs)
        for name, songs in (
            (n, k.playlist_manager.get(n) or []) for n in k.playlist_manager.names()
        )
    }
    library = [
        {"file": path, "title": k.song_manager.filename_from_path(path, remove_youtube_id=True)}
        for path in k.song_manager.songs
    ]
    library.sort(key=lambda song: song["title"].casefold())

    return render_template(
        "playlists.html",
        site_title=get_site_name(),
        title=_("Playlists"),
        playlists=saved,
        library=library,
        admin=is_admin(),
    )


@playlists_bp.route("/playlists/save", methods=["POST"])
@playlists_bp.arguments(SavePlaylistForm, location="form")
def save_playlist(form):
    """Save a playlist, either from an explicit song list or from the current queue."""
    k = get_karaoke_instance()
    songs = form.get("songs")

    if not songs:
        # Saving from the queue page, where the songs are whatever is queued now
        songs = [item["file"] for item in k.queue_manager.queue]
        if not songs:
            # MSG: Message shown when trying to save an empty queue as a playlist
            flash(_("The queue is empty, nothing to save"), "is-warning")
            return redirect(url_for("queue.queue"))

    success, message = k.playlist_manager.save(form["name"], songs)
    flash(message, "is-success" if success else "is-danger")
    return redirect(url_for("playlists.playlists"))


@playlists_bp.route("/playlists/load/<name>", methods=["GET"])
@playlists_bp.arguments(LoadPlaylistQuery, location="query")
def load_playlist(query, name):
    """Add a playlist's songs to the queue, appending or replacing what is queued."""
    k = get_karaoke_instance()
    songs = k.playlist_manager.get(name)

    if songs is None:
        # MSG: Message shown when loading a playlist that no longer exists
        flash(_("No playlist named %s") % name, "is-danger")
        return redirect(url_for("playlists.playlists"))

    replace = query["mode"] == "replace"
    if replace:
        if not is_admin():
            # MSG: Message shown when a non-admin tries to replace the queue
            flash(_("You don't have permission to replace the queue"), "is-danger")
            return redirect(url_for("playlists.playlists"))
        k.queue_manager.queue_clear()
        broadcast_event("skip", "clear queue")

    user = request.cookies.get("user") or "Playlist"
    added = 0
    skipped = 0
    for song in songs:
        # A song can disappear from the library after a playlist is saved
        if not os.path.exists(song):
            skipped += 1
            continue
        success, _message = k.queue_manager.enqueue(song, user)
        if success:
            added += 1
        else:
            skipped += 1

    broadcast_event("queue_update")

    if added:
        # MSG: Message shown after queueing a playlist. First value is a count, second a playlist name.
        flash(
            _("Added %(count)s song(s) from %(name)s") % {"count": added, "name": name},
            "is-success",
        )
    if skipped:
        # MSG: Message shown when songs in a playlist could not be queued
        flash(_("Skipped %s song(s) that are missing or already queued") % skipped, "is-warning")

    return redirect(url_for("queue.queue"))


@playlists_bp.route("/playlists/delete/<name>", methods=["POST"])
def delete_playlist(name):
    """Delete a saved playlist (admin only)."""
    if not is_admin():
        # MSG: Message shown when a non-admin tries to delete a playlist
        flash(_("You don't have permission to delete playlists"), "is-danger")
        return redirect(url_for("playlists.playlists"))

    k = get_karaoke_instance()
    success, message = k.playlist_manager.delete(name)
    flash(message, "is-success" if success else "is-danger")
    return redirect(url_for("playlists.playlists"))
