"""
Automated Tests — WebSocket Streaming Pipeline, Live VAD Config, and Self-Echo Guard
"""

import asyncio
import base64
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.stream import (
    app,
    LunarLiveEchoGuard,
    build_lunar_live_config,
    normalize_transcript_tokens,
)

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


def test_build_lunar_live_config_vad_and_mldev_serialization():
    from google import genai
    from google.genai import types as genai_types
    from google.genai import _live_converters as lc
    from google.genai import _common

    cfg = build_lunar_live_config(
        genai_types_mod=genai_types,
        system_prompt="Test prompt",
        voice_name="Aoede",
    )
    assert cfg.realtime_input_config is not None
    aad = cfg.realtime_input_config.automatic_activity_detection
    assert aad is not None
    assert aad.disabled is False
    assert aad.start_of_speech_sensitivity == genai_types.StartSensitivity.START_SENSITIVITY_LOW
    assert aad.end_of_speech_sensitivity == genai_types.EndSensitivity.END_SENSITIVITY_HIGH
    assert aad.prefix_padding_ms == 160
    assert aad.silence_duration_ms == 450
    assert cfg.realtime_input_config.activity_handling == genai_types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS
    assert cfg.realtime_input_config.turn_coverage == genai_types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY
    assert cfg.explicit_vad_signal is None
    assert cfg.proactivity is None

    # Must serialize cleanly in Gemini Developer API (mldev) mode without ValueError
    fake_client = genai.Client(api_key="test-key-only")
    params = genai_types.LiveConnectParameters(
        model="models/gemini-2.5-flash-native-audio-latest",
        config=cfg,
    ).model_dump(exclude_none=True)
    wire = _common.convert_to_dict(
        lc._LiveConnectParameters_to_mldev(api_client=fake_client._api_client, from_object=params)
    )
    assert "realtimeInputConfig" in wire["setup"]
    assert "explicitVadSignal" not in wire["setup"]


def test_normalize_transcript_tokens_expands_contractions():
    tokens = normalize_transcript_tokens("I'm right here—don't worry, it's steady!")
    assert tokens == ["i", "am", "right", "here", "do", "not", "worry", "it", "is", "steady"]


def test_echo_guard_suppresses_pure_self_echo_chunks_during_playback_and_tail():
    clock_now = [100.0]
    guard = LunarLiveEchoGuard(clock=lambda: clock_now[0])

    # Lunar emits 2.0 seconds of 24kHz mono 16-bit PCM (96,000 bytes) + output text
    guard.note_output_audio(96000, mime_type="audio/pcm;rate=24000")
    guard.note_output_transcript("Hey Mahir, I'm right here. Your heart rate looks steady at 72 beats per minute.")
    clock_now[0] = 100.3
    guard.note_turn_complete()

    # Streaming partial echo chunks while speaker audio is still playing (t=101.0 < 102.0)
    clock_now[0] = 101.0
    assert guard.handle_input_transcript("Your heart ", False) == []
    assert guard.handle_input_transcript("rate looks ", False) == []
    assert guard.handle_input_transcript("steady.", True) == []

    # Contraction variation echo during tail (t=102.5)
    clock_now[0] = 102.5
    assert guard.handle_input_transcript("I am right here", True) == []


def test_echo_guard_preserves_genuine_followup_and_short_commands():
    clock_now = [200.0]
    guard = LunarLiveEchoGuard(clock=lambda: clock_now[0])

    guard.note_output_audio(48000, mime_type="audio/pcm;rate=24000")  # 1.0s audio -> until 201.0
    guard.note_output_transcript("Would you like me to check your heart rate or oxygen levels?")
    guard.note_turn_complete()

    # Protected wake/ack phrases must never be dropped even immediately
    clock_now[0] = 200.4
    assert guard.handle_input_transcript("Hey Lunar", True) == [
        {"type": "input_transcript", "text": "Hey Lunar", "finished": True}
    ]
    assert guard.handle_input_transcript("Yes", True) == [
        {"type": "input_transcript", "text": "Yes", "finished": True}
    ]

    # Genuine follow-up reusing some words ("Check my heart rate" vs "...check your heart rate")
    clock_now[0] = 201.2
    assert guard.handle_input_transcript("Check my heart rate", True) == [
        {"type": "input_transcript", "text": "Check my heart rate", "finished": True}
    ]

    # Ambiguous prefix that diverges into genuine user sentence must flush completely
    clock_now[0] = 200.5
    assert guard.handle_input_transcript("Your ", False) == []
    out = guard.handle_input_transcript("monitor screen froze", False)
    assert out == [{"type": "input_transcript", "text": "Your monitor screen froze", "finished": False}]
    assert guard.handle_input_transcript("", True) == [
        {"type": "input_transcript", "text": "", "finished": True}
    ]

    # Client entered gate with audio_end, then resumed audio after playback ended -> 2-word reply passes
    clock_now[0] = 200.1
    guard.note_client_audio_end()
    clock_now[0] = 201.9
    guard.note_client_audio_chunk()
    assert guard.handle_input_transcript("Heart rate", True) == [
        {"type": "input_transcript", "text": "Heart rate", "finished": True}
    ]


def test_echo_guard_interrupted_clamps_playback_and_allows_barge_in():
    clock_now = [300.0]
    guard = LunarLiveEchoGuard(clock=lambda: clock_now[0])

    guard.note_output_audio(240000, mime_type="audio/pcm;rate=24000")  # 5.0s queued -> 305.0
    guard.note_output_transcript("Starting long telemetry summary for cabin sensors and radiation.")

    clock_now[0] = 300.6
    guard.note_interrupted()
    assert guard.output_active is False
    assert guard.estimated_playback_until <= 300.96

    # Genuine barge-in utterance passes immediately
    assert guard.handle_input_transcript("Stop, check my oxygen.", True) == [
        {"type": "input_transcript", "text": "Stop, check my oxygen.", "finished": True}
    ]


def test_lunar_live_ws_audio_end_and_multiturn_self_echo_suppression(monkeypatch):
    import google.genai as genai_pkg

    turn2_ready = None

    class FakeSession:
        def __init__(self):
            self.realtime_inputs = []
            self.client_contents = []
            self._receive_calls = 0

        async def send_realtime_input(self, **kwargs):
            self.realtime_inputs.append(kwargs)
            if kwargs.get("audio") is not None and turn2_ready is not None:
                turn2_ready.set()

        async def send_client_content(self, **kwargs):
            self.client_contents.append(kwargs)

        async def send_tool_response(self, **kwargs):
            pass

        async def receive(self):
            nonlocal turn2_ready
            self._receive_calls += 1
            if self._receive_calls == 1:
                # Turn 1: Lunar greets + speaker echo fragment arrives before turn_complete
                yield SimpleNamespace(
                    tool_call=None,
                    server_content=SimpleNamespace(
                        model_turn=SimpleNamespace(
                            parts=[
                                SimpleNamespace(
                                    inline_data=SimpleNamespace(
                                        data=b"\x01\x00" * 24000,  # 1.0s of 24kHz PCM
                                        mime_type="audio/pcm;rate=24000",
                                    )
                                )
                            ]
                        ),
                        output_transcription=SimpleNamespace(
                            text="Hey Mahir, I'm right here—how can I help?"
                        ),
                        input_transcription=None,
                        interrupted=False,
                        turn_complete=False,
                    ),
                )
                yield SimpleNamespace(
                    tool_call=None,
                    server_content=SimpleNamespace(
                        model_turn=None,
                        output_transcription=None,
                        input_transcription=SimpleNamespace(
                            text="I'm right here—how can I help?",
                            finished=True,
                        ),
                        interrupted=False,
                        turn_complete=True,
                    ),
                )
                return

            if self._receive_calls == 2:
                await turn2_ready.wait()
                # Turn 2: Genuine user follow-up after client resumes audio
                yield SimpleNamespace(
                    tool_call=None,
                    server_content=SimpleNamespace(
                        model_turn=None,
                        output_transcription=None,
                        input_transcription=SimpleNamespace(
                            text="Check my blood pressure.",
                            finished=True,
                        ),
                        interrupted=False,
                        turn_complete=False,
                    ),
                )
                yield SimpleNamespace(
                    tool_call=None,
                    server_content=SimpleNamespace(
                        model_turn=SimpleNamespace(
                            parts=[
                                SimpleNamespace(
                                    inline_data=SimpleNamespace(
                                        data=b"\x02\x00" * 12000,
                                        mime_type="audio/pcm;rate=24000",
                                    )
                                )
                            ]
                        ),
                        output_transcription=SimpleNamespace(
                            text="Your blood pressure looks steady."
                        ),
                        input_transcription=None,
                        interrupted=False,
                        turn_complete=True,
                    ),
                )
                return

            # Call 3: empty iterator should exit cleanly without CPU spin
            return
            yield  # pragma: no cover

    fake_session = FakeSession()

    class FakeConnectCM:
        async def __aenter__(self):
            nonlocal turn2_ready
            turn2_ready = asyncio.Event()
            return fake_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeClient:
        def __init__(self, api_key=None):
            self.aio = SimpleNamespace(
                live=SimpleNamespace(connect=lambda **kwargs: FakeConnectCM())
            )

    monkeypatch.setattr("src.api.stream.get_gemini_api_key", lambda: "fake-api-key")
    monkeypatch.setattr(genai_pkg, "Client", FakeClient)

    received_messages = []
    with client.websocket_connect("/ws/lunar/live") as ws:
        # 1. session_ready
        msg0 = ws.receive_json()
        assert msg0["type"] == "session_ready"

        # 2. Client sends audio_end (echo gate engaged) and audio_stream_end
        ws.send_json({"type": "audio_end"})
        ws.send_json({"type": "audio_stream_end"})

        # Collect Turn 1 messages until turn_complete
        while True:
            ev = ws.receive_json()
            received_messages.append(ev)
            if ev["type"] == "turn_complete":
                break

        # Pure self-echo must NOT have been forwarded during Turn 1
        assert not any(m["type"] == "input_transcript" for m in received_messages)
        assert any(m["type"] == "output_transcript" for m in received_messages)
        assert any(m["type"] == "audio" for m in received_messages)

        # 3. Client resumes audio for Turn 2
        pcm_b64 = base64.b64encode(b"\x10\x00" * 160).decode("ascii")
        ws.send_json({"type": "audio", "data": pcm_b64, "mime_type": "audio/pcm;rate=16000"})

        turn2_messages = []
        while True:
            ev = ws.receive_json()
            turn2_messages.append(ev)
            if ev["type"] == "turn_complete":
                break

        user_msgs = [m for m in turn2_messages if m["type"] == "input_transcript"]
        assert user_msgs == [
            {"type": "input_transcript", "text": "Check my blood pressure.", "finished": True}
        ]
        assert any(
            m["type"] == "turn_complete" and m["text"] == "Your blood pressure looks steady."
            for m in turn2_messages
        )

    # Verify both audio_end and audio_stream_end forwarded audio_stream_end=True, plus audio Blob
    audio_end_calls = [c for c in fake_session.realtime_inputs if c.get("audio_stream_end") is True]
    assert len(audio_end_calls) == 2
    audio_calls = [c for c in fake_session.realtime_inputs if c.get("audio") is not None]
    assert len(audio_calls) == 1
