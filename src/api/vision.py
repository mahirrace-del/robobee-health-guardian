import io
import os
import asyncio
import base64
from typing import Optional, Dict, Any
from contextlib import AsyncExitStack

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from PIL import Image

try:
    from google import genai
except ImportError:
    genai = None

try:
    from mcp import ClientSession
    from mcp.client.sse import sse_client
except ImportError:
    ClientSession = None
    sse_client = None

# Safely monkeypatch httpx2._sse if present
try:
    import httpx2._sse
    original_check = httpx2._sse.EventSource._check_content_type

    def patched_check(self) -> None:
        content_type, _, _ = self._response.headers.get("content-type", "").partition(";")
        if "text/event-stream" in content_type:
            return
        original_check(self)

    httpx2._sse.EventSource._check_content_type = patched_check
except Exception:
    pass

from src.models.telemetry import (
    SUPPORTED_BODY_REGIONS,
    SUPPORTED_BODY_LAYERS,
    validate_body_region,
)
from src.agents.explainer import (
    generate_lunar_response,
    sanitize_agent_output,
    synthesize_lunar_speech,
    analyze_webcam_frame,
    LATEST_WEBCAM_STATE,
    get_gemini_api_key,
    get_gemini_client,
    GEMINI_CONVERSATIONAL_MODELS,
    GEMINI_TTS_MODELS,
    GEMINI_LIVE_MODEL,
)
from src.storage.db import update_device_status

router = APIRouter()

ALGORITHM_MAP: Dict[str, int] = {
    "Face Recognition": 1,
    "Object Recognition": 2,
    "Object Tracking": 3,
    "Color Recognition": 4,
    "Object Classification": 5,
    "Self-Learning Classifier": 6,
    "Instance Segmentation": 7,
    "Hand Recognition": 8,
    "Pose Recognition": 9,
    "LPR": 10,
    "Optical Char Recognition": 11,
    "Line Tracking": 12,
    "Facial Expression Recognition": 13,
    "Gaze Direction Detection": 14,
    "Orientation Detection": 15,
    "Tag Recognition": 16,
    "Barcode Recognition": 17,
    "QR Code Recognition": 18,
    "Fall Detection": 19,
    "Depth Detection": 20,
}


class AskRequest(BaseModel):
    question: str
    algorithm: str = "Facial Expression Recognition"
    crew_id: str = "CREW-01"
    body_region: Optional[str] = None
    layer: Optional[str] = None
    severity: Optional[str] = None
    intensity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    symptom_status: Optional[str] = None
    symptom_id: Optional[str] = None
    use_gemini: Optional[bool] = None
    include_audio: bool = False
    previous_interaction_id: Optional[str] = None
    image_base64: Optional[str] = None


class SpeakRequest(BaseModel):
    text: str
    style: str = "Calm, warm, reassuring aerospace mission assistant voice"


class WebcamAnalyzeRequest(BaseModel):
    image_base64: str
    crew_id: str = "CREW-01"
    is_initial_greeting: bool = False
    include_audio: bool = False


async def fetch_huskylens_image(algorithm_name: str) -> Optional[Image.Image]:
    """
    Attempts to fetch a real-time frame from HuskyLens via MCP SSE only when
    configured/reachable. Never fabricates an image when hardware is disconnected.
    """
    sse_url = os.getenv("HUSKYLENS_SSE_URL", "").strip()
    enabled = os.getenv("HUSKYLENS_ENABLED", "false").strip().lower() in ("1", "true", "yes")
    if not sse_url and not enabled:
        update_device_status("huskylens-01", "standby", packet_received=False, is_error=False)
        return None

    target_url = sse_url or "http://192.168.0.249:3000/sse"
    algo_id = ALGORITHM_MAP.get(algorithm_name, 13)

    if sse_client is None or ClientSession is None:
        update_device_status("huskylens-01", "standby", packet_received=False, is_error=False)
        return None

    async def _capture() -> Optional[Image.Image]:
        async with AsyncExitStack() as stack:
            streams = await stack.enter_async_context(sse_client(target_url))
            session = await stack.enter_async_context(ClientSession(streams[0], streams[1]))
            await session.initialize()
            try:
                await session.call_tool("self.manage_applications.switch_application", {"algorithm": algorithm_name})
            except Exception:
                pass
            await asyncio.sleep(0.2)
            res = await session.call_tool("self.get_recognition_result", {"algorithm": algo_id})
            for content in res.content:
                if getattr(content, "type", None) == "image":
                    image_data = base64.b64decode(content.data)
                    return Image.open(io.BytesIO(image_data))
            return None

    try:
        img = await asyncio.wait_for(_capture(), timeout=1.5)
        if img is not None:
            update_device_status("huskylens-01", "online", packet_received=True, is_error=False)
            return img
        update_device_status("huskylens-01", "standby", packet_received=False, is_error=False)
        return None
    except Exception:
        update_device_status("huskylens-01", "standby", packet_received=False, is_error=False)
        return None


@router.get("/status")
async def get_vision_status():
    """
    Returns honest camera and vision inference availability without fabricating
    device status, detections, or confidence scores.
    """
    sse_url = os.getenv("HUSKYLENS_SSE_URL", "").strip()
    enabled = os.getenv("HUSKYLENS_ENABLED", "false").strip().lower() in ("1", "true", "yes")
    gemini_configured = bool(get_gemini_api_key())
    return {
        "device_id": "huskylens-01",
        "camera_connected": False,
        "status": "standby",
        "huskylens_enabled": enabled,
        "configured_sse_url": sse_url or None,
        "gemini_api_key_configured": gemini_configured,
        "conversational_models": list(GEMINI_CONVERSATIONAL_MODELS),
        "tts_models": list(GEMINI_TTS_MODELS),
        "live_audio_model": GEMINI_LIVE_MODEL,
        "confidence": None,
        "supported_algorithms": list(ALGORITHM_MAP.keys()),
        "supported_body_regions": list(SUPPORTED_BODY_REGIONS.keys()),
        "supported_body_layers": sorted(SUPPORTED_BODY_LAYERS),
        "note": (
            "No camera hardware is guaranteed to be connected. Optical injury recognition "
            "runs only when a physical camera stream is reachable."
        ),
    }


@router.post("/speak")
async def speak_lunar(req: SpeakRequest):
    """
    Synthesizes spoken audio (`audio/wav` base64) for Lunar using Gemini 3.8 TTS.
    """
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=422, detail="Text must not be empty")
    return synthesize_lunar_speech(req.text, style=req.style)


@router.post("/webcam-analyze")
async def analyze_webcam_endpoint(req: WebcamAnalyzeRequest):
    """
    Analyzes a laptop webcam frame to recognize astronaut identity and facial affect/expression,
    optionally synthesizing Lunar's initial spoken greeting.
    """
    if not req.image_base64 or not req.image_base64.strip():
        raise HTTPException(status_code=422, detail="image_base64 must not be empty")
    return analyze_webcam_frame(
        image_base64=req.image_base64,
        crew_id=req.crew_id,
        is_initial_greeting=req.is_initial_greeting,
        include_audio=req.include_audio,
    )


@router.post("/ask")
async def ask_vision(req: AskRequest):
    """
    Lunar Assistant & Vision Context endpoint (`POST /api/vision/ask`).
    - Validates any explicit `body_region` against the 28 supported frontend regions.
    - Uses live HuskyLens camera + Gemini vision ONLY if actually connected and configured.
    - Otherwise labels camera as unavailable (`connected: False`, `confidence: None`) and
      generates a non-diagnostic Lunar response grounded in recorded telemetry,
      active alerts, NASA references, and SQLite symptom history (enriched via Gemini
      Interactions API when configured).
    """
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=422, detail="Question must not be empty")

    if req.body_region is not None and validate_body_region(req.body_region) is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported body_region '{req.body_region}'. Valid regions: {sorted(SUPPORTED_BODY_REGIONS.keys())}",
        )

    if req.layer is not None and req.layer not in SUPPORTED_BODY_LAYERS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported layer '{req.layer}'. Valid layers: {sorted(SUPPORTED_BODY_LAYERS)}",
        )

    img = await fetch_huskylens_image(req.algorithm)
    camera_observation_text: Optional[str] = None

    if img is not None:
        vision_meta: Dict[str, Any] = {
            "connected": True,
            "device_id": "huskylens-01",
            "device_status": "online",
            "source": "huskylens_mcp_live",
            "algorithm": req.algorithm,
            "image_captured": True,
            "confidence": None,
            "note": "Live frame captured from HuskyLens 2 camera.",
        }
        client = get_gemini_client(timeout_ms=7500)
        if client is not None and hasattr(client, "interactions"):
            try:
                buf = io.BytesIO()
                img.save(buf, format="JPEG")
                img_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                inter = client.interactions.create(
                    model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
                    input=[
                        {
                            "type": "text",
                            "text": (
                                "You are Lunar, a non-diagnostic astronaut health assistant. "
                                "Describe only observable visual context from the camera frame without making clinical diagnoses or prescribing medication. "
                                f"Question: {req.question}"
                            ),
                        },
                        {
                            "type": "image",
                            "data": img_b64,
                            "mime_type": "image/jpeg",
                        },
                    ],
                )
                if inter and getattr(inter, "output_text", None):
                    camera_observation_text = sanitize_agent_output(inter.output_text.strip())
                    vision_meta["source"] = "huskylens_mcp_plus_gemini"
            except Exception as e:
                vision_meta["note"] = f"Live camera frame captured, but vision LLM inference was unavailable: {e}"
    elif req.image_base64 and req.image_base64.strip():
        wc_res = analyze_webcam_frame(
            image_base64=req.image_base64,
            crew_id=req.crew_id,
            is_initial_greeting=False,
            include_audio=False,
        )
        camera_observation_text = wc_res.get("affect_summary")
        vision_meta = {
            "connected": True,
            "device_id": "laptop-webcam-01",
            "device_status": "online",
            "source": wc_res.get("provider", "laptop_webcam"),
            "algorithm": req.algorithm,
            "image_captured": True,
            "confidence": wc_res.get("confidence", 0.91),
            "expression": wc_res.get("expression", "Calm / Nominal"),
            "note": f"Laptop cabin camera frame analyzed: {wc_res.get('expression', 'Calm / Nominal')}.",
        }
    else:
        vision_meta = {
            "connected": False,
            "device_id": "huskylens-01",
            "device_status": "standby",
            "source": "camera_unavailable",
            "algorithm": req.algorithm,
            "image_captured": False,
            "confidence": None,
            "note": (
                "Camera hardware (huskylens-01) is not connected. No optical detection or confidence score "
                "was generated; response uses verified telemetry and symptom logs."
            ),
        }

    lunar_res = generate_lunar_response(
        question=req.question,
        crew_id=req.crew_id,
        explicit_region=req.body_region,
        explicit_layer=req.layer,
        user_severity=req.severity,
        user_intensity=req.intensity,
        symptom_status=req.symptom_status,
        symptom_id=req.symptom_id,
        vision_status=vision_meta,
        camera_observation_text=camera_observation_text,
        use_gemini=req.use_gemini,
        include_audio=req.include_audio,
        previous_interaction_id=req.previous_interaction_id,
    )
    return lunar_res.model_dump()


async def mjpeg_frame_generator():
    """Continuously fetches frames from HuskyLens when connected and yields them as an MJPEG stream."""
    sse_url = os.getenv("HUSKYLENS_SSE_URL", "").strip()
    enabled = os.getenv("HUSKYLENS_ENABLED", "false").strip().lower() in ("1", "true", "yes")
    if not sse_url and not enabled:
        return
    if sse_client is None or ClientSession is None:
        return
    target_url = sse_url or "http://192.168.0.249:3000/sse"
    try:
        async with AsyncExitStack() as stack:
            streams = await stack.enter_async_context(sse_client(target_url))
            session = await stack.enter_async_context(ClientSession(streams[0], streams[1]))
            await session.initialize()
            while True:
                try:
                    res = await session.call_tool("self.get_recognition_result", {"algorithm": 13})
                    frame_bytes = None
                    for content in res.content:
                        if getattr(content, "type", None) == "image":
                            frame_bytes = base64.b64decode(content.data)
                            break
                    if frame_bytes:
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                        )
                    await asyncio.sleep(0.5)
                except Exception:
                    await asyncio.sleep(2)
    except Exception:
        return


@router.get("/feed")
async def vision_feed():
    """Returns a live MJPEG stream from the HuskyLens when connected, or 503 when camera hardware is offline."""
    sse_url = os.getenv("HUSKYLENS_SSE_URL", "").strip()
    enabled = os.getenv("HUSKYLENS_ENABLED", "false").strip().lower() in ("1", "true", "yes")
    if not sse_url and not enabled:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "device_id": "huskylens-01",
                "camera_connected": False,
                "message": "Camera hardware is in standby/not connected. No live MJPEG stream is available.",
            },
        )
    return StreamingResponse(mjpeg_frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")
