"""Socket.IO event handlers for PiKaraoke."""

import logging

from flask import request

from pikaraoke.lib.current_app import get_karaoke_instance

# Track connected splash screen clients and the elected master
splash_connections = set()
master_splash_id = None


def setup_socket_events(socketio):
    """Register Socket.IO event handlers.

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
        for sid in list(splash_connections):
            if not socketio.server.manager.is_connected(sid, "/"):
                splash_connections.discard(sid)
                logging.info(f"Dropping stale splash screen: {sid}")

    def assign_master(sid: str) -> None:
        """Give the master role to a splash screen."""
        global master_splash_id
        master_splash_id = sid
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
        sid = request.sid
        splash_connections.add(sid)
        logging.info(f"Splash screen registered: {sid}")

        drop_stale_connections()

        if master_splash_id in splash_connections and master_splash_id != sid:
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
        sid = request.sid
        if sid == master_splash_id:
            k = get_karaoke_instance()
            k.playback_controller.now_playing_position = position
            # Broadcast position to all other splash screens (slaves)
            socketio.emit("playback_position", position, include_self=False)

    @socketio.on("disconnect")
    def handle_disconnect() -> None:
        """Handle Socket.IO client disconnection and manage splash role handover."""
        global master_splash_id
        sid = request.sid
        if sid not in splash_connections:
            return

        splash_connections.discard(sid)
        logging.info(f"Splash screen disconnected: {sid}")

        if sid != master_splash_id:
            return

        master_splash_id = None
        logging.info("Master splash disconnected, electing new master")
        drop_stale_connections()
        if splash_connections:
            assign_master(next(iter(splash_connections)))
        else:
            logging.info("No splash screens connected, master role is open")
