"""
Automated Tests — WebSocket Streaming Pipeline & Envelopes
"""

import pytest
from fastapi.testclient import TestClient
from src.api.stream import app

client = TestClient(app)


def test_websocket_connection_and_handshake():
    with client.websocket_connect("/ws/telemetry") as websocket:
        # Initial connection handshake
        data = websocket.receive_json()
        assert data["type"] == "connection"
        assert data["status"] == "connected"
        assert "server_time" in data
        assert "source_mode" in data

        # Send heartbeat ping
        websocket.send_json({"type": "ping"})
        pong = websocket.receive_json()
        
        # Verify pong or next broadcast
        assert pong["type"] in ["pong", "telemetry"]
