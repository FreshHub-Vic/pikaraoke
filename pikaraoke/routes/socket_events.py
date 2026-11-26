"""Socket.IO event handlers for PiKaraoke."""

import logging

from flask import request

from pikaraoke.lib.current_app import get_karaoke_instance


def setup_socket_events(socketio):
    """Register Socket.IO event handlers.

    Splash screen connections and the elected master live on the Karaoke
    instance so the run loop can hold the queue until a player is present.

    Args:
        socketio: The SocketIO instance.
    """

    def drop_stale_connections() -> None:
        """Forget splash screens that vanished without a disconnect event.

        A browser that is killed, sleeps, or loses the network may never fire
        disconnect. Those sids would otherwise keep the master role pinned to a
        client that can no longer report song endings, leaving every later
        splash screen a slave and the queue stuck.
        """
        k = get_karaoke_instance()
        for sid in list(k.splash_connections):
            if not socketio.server.manager.is_connected(sid, "/"):
                k.splash_connections.discard(sid)
                logging.info(f"Dropping stale splash screen: {sid}")

    def assign_master(sid: str) -> None:
        """Give the master role to a splash screen."""
        k = get_karaoke_instance()
        k.master_splash_id = sid
        socketio.emit("splash_role", "master", room=sid)
        logging.info(f"Master splash screen assigned: {sid}")

    @socketio.on("end_song")
    def end_song(reason: str) -> None:
        """Handle end_song WebSocket event from client.

        Args:
            reason: Reason for ending the song (e.g., 'complete', 'error').
        """
        k = get_karaoke_instance()
        k.playback_controller.end_song(reason)

    @socketio.on("start_song")
    def start_song() -> None:
        """Handle start_song WebSocket event when playback begins."""
        k = get_karaoke_instance()
        k.playback_controller.start_song()

    @socketio.on("clear_notification")
    def clear_notification() -> None:
        """Handle clear_notification WebSocket event to dismiss notifications."""
        k = get_karaoke_instance()
        k.reset_now_playing_notification()

    @socketio.on("register_splash")
    def register_splash() -> None:
        """Handle splash screen registration and assign master/slave roles."""
        k = get_karaoke_instance()
        sid = request.sid
        k.splash_connections.add(sid)
        logging.info(f"Splash screen registered: {sid}")

        drop_stale_connections()

        if k.master_splash_id in k.splash_connections and k.master_splash_id != sid:
            socketio.emit("splash_role", "slave", room=sid)
            logging.info(f"Slave splash screen assigned: {sid}")
        else:
            assign_master(sid)

    @socketio.on("playback_position")
    def handle_playback_position(position: float) -> None:
        """Handle playback_position WebSocket event from the master splash screen.

        Args:
            position: Current playback position in seconds.
        """
        k = get_karaoke_instance()
        if request.sid == k.master_splash_id:
            k.playback_controller.now_playing_position = position
            # Broadcast position to all other splash screens (slaves)
            socketio.emit("playback_position", position, include_self=False)

    @socketio.on("disconnect")
    def handle_disconnect() -> None:
        """Handle Socket.IO client disconnection and manage splash role handover."""
        k = get_karaoke_instance()
        sid = request.sid
        if sid not in k.splash_connections:
            return

        k.splash_connections.discard(sid)
        logging.info(f"Splash screen disconnected: {sid}")

        if sid != k.master_splash_id:
            return

        k.master_splash_id = None
        logging.info("Master splash disconnected, electing new master")
        drop_stale_connections()
        if k.splash_connections:
            assign_master(next(iter(k.splash_connections)))
        else:
            logging.info("No splash screens connected, master role is open")
