from __future__ import annotations

from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Static trail segment data (no database for MVP)
SEGMENTS = [
    {
        "id": 1,
        "length_km": 14,
        "difficulty": "hard",
        "has_water": False,
        "shade_level": "low",
        "suitable_for_kids": False,
    },
    {
        "id": 2,
        "length_km": 9,
        "difficulty": "moderate",
        "has_water": True,
        "shade_level": "medium",
        "suitable_for_kids": True,
    },
    {
        "id": 3,
        "length_km": 6,
        "difficulty": "easy",
        "has_water": True,
        "shade_level": "high",
        "suitable_for_kids": True,
    },
    {
        "id": 4,
        "length_km": 11,
        "difficulty": "moderate",
        "has_water": False,
        "shade_level": "low",
        "suitable_for_kids": True,
    },
]

DIFFICULTY_ORDER = {"easy": 1, "moderate": 2, "hard": 3}


class RouteRequest(BaseModel):
    days: int = Field(..., ge=1, le=2)
    season: str = Field(..., pattern="^(summer|winter|spring|fall)$")
    withKids: bool
    difficulty: str = Field(..., pattern="^(easy|moderate|hard)$")


class SegmentRecommendation(BaseModel):
    segment: int
    reason: str


class RouteResponse(BaseModel):
    recommended_segments: List[SegmentRecommendation]
    warnings: List[str]
    checklist: List[str]


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


def score_segment(segment: dict, request: RouteRequest) -> int:
    """Score a segment based on deterministic rules (no AI)."""
    score = 0

    # Difficulty match or easier gets a higher score.
    segment_diff = DIFFICULTY_ORDER[segment["difficulty"]]
    request_diff = DIFFICULTY_ORDER[request.difficulty]
    if segment_diff == request_diff:
        score += 3
    elif segment_diff < request_diff:
        score += 1

    # Prefer shorter segments for MVP safety.
    if segment["length_km"] <= 6:
        score += 3
    elif segment["length_km"] <= 10:
        score += 2
    else:
        score += 0

    # Water availability is always a strong positive.
    if segment["has_water"]:
        score += 3

    # Shade preference for summer and overall comfort.
    shade_level = segment["shade_level"]
    if shade_level == "high":
        score += 3
    elif shade_level == "medium":
        score += 1

    # Kids suitability gets a bonus when relevant.
    if request.withKids and segment["suitable_for_kids"]:
        score += 2

    # Seasonal adjustments (summer prefers shade, penalize long segments).
    if request.season == "summer":
        if shade_level == "high":
            score += 2
        elif shade_level == "medium":
            score += 1
        if segment["length_km"] > 10:
            score -= 2

    # Single-day hikes should avoid long segments and favor water.
    if request.days == 1:
        if segment["length_km"] > 10:
            score -= 2
        if segment["has_water"]:
            score += 1

    return score


def build_reason(segment: dict, request: RouteRequest) -> str:
    """Create a human-readable reason for the recommendation."""
    reasons = []

    if segment["length_km"] <= 6:
        reasons.append("short distance")
    elif segment["length_km"] <= 10:
        reasons.append("manageable distance")
    else:
        reasons.append("longer route")

    if segment["has_water"]:
        reasons.append("water access")
    else:
        reasons.append("no water points")

    shade_level = segment["shade_level"]
    reasons.append(f"{shade_level} shade")

    if request.withKids and segment["suitable_for_kids"]:
        reasons.append("kid-friendly")

    return "Segment with " + ", ".join(reasons)


def build_warnings(segments: List[dict], request: RouteRequest) -> List[str]:
    """Generate warnings based on inputs and selected segments."""
    warnings = set()

    for segment in segments:
        if request.season == "summer" and segment["shade_level"] == "low":
            warnings.add("High heat exposure")
        if request.withKids and segment["length_km"] > 10:
            warnings.add("Long distance for children")
        if not segment["has_water"]:
            warnings.add("No water points along this segment")

    return sorted(warnings)


def build_checklist(request: RouteRequest) -> List[str]:
    """Build a checklist based on season and general safety needs."""
    checklist = ["Good hiking shoes"]

    if request.season == "summer":
        checklist.extend(
            [
                "At least 4 liters of water per person",
                "Hat",
                "Sun protection",
            ]
        )
    if request.season == "winter":
        checklist.append("Warm layers")

    return checklist


def filter_segments(request: RouteRequest) -> List[dict]:
    """Apply deterministic filtering rules before scoring."""
    filtered = []
    request_diff = DIFFICULTY_ORDER[request.difficulty]

    for segment in SEGMENTS:
        if request.withKids and not segment["suitable_for_kids"]:
            continue
        segment_diff = DIFFICULTY_ORDER[segment["difficulty"]]
        if segment_diff > request_diff:
            continue
        filtered.append(segment)

    return filtered


@app.post("/build-route", response_model=RouteResponse)
def build_route(request: RouteRequest) -> RouteResponse:
    segments = filter_segments(request)

    scored = [
        {"segment": segment, "score": score_segment(segment, request)}
        for segment in segments
    ]
    scored.sort(key=lambda item: item["score"], reverse=True)

    top_segments = [item["segment"] for item in scored[:3]]
    if len(top_segments) > 2:
        top_segments = top_segments[:3]
    else:
        top_segments = top_segments[:2] if len(top_segments) == 2 else top_segments

    recommendations = [
        SegmentRecommendation(
            segment=segment["id"],
            reason=build_reason(segment, request),
        )
        for segment in top_segments
    ]

    return RouteResponse(
        recommended_segments=recommendations,
        warnings=build_warnings(top_segments, request),
        checklist=build_checklist(request),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
