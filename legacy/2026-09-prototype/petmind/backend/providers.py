"""Provider-neutral care recommendation interface.

The default provider is deterministic and works without an external API key.
Future Gemini, OpenAI, or Claude adapters only need to implement ``suggest``.
"""
import json
from typing import Protocol

import requests

from schemas import CareActionType, CareSeverity, CareSuggestionDraft, PetContext
from settings import settings


class LLMProvider(Protocol):
    name: str

    def suggest(self, context: PetContext) -> CareSuggestionDraft:
        ...


class RuleBasedProvider:
    name = "rule"

    def suggest(self, context: PetContext) -> CareSuggestionDraft:
        reasons: list[str] = []
        actions: list[CareActionType] = []
        severity = CareSeverity.info
        state = "normal"
        music_style = None
        feeding_amount_g = None

        stress_signal = context.observed_behavior in {"anxious", "alert"}
        repeated_barking = context.bark_detected and context.bark_count >= 3
        environment_warning = (
            (context.temperature is not None and context.temperature >= 28)
            or (context.humidity is not None and context.humidity >= 70)
        )

        if stress_signal:
            reasons.append(f"시각 분류 신호가 {context.observed_behavior} 상태입니다.")
        if repeated_barking:
            reasons.append(f"최근 구간에서 짖음이 {context.bark_count}회 감지됐습니다.")
        if environment_warning:
            reasons.append("온도 또는 습도가 권장 범위를 벗어났습니다.")

        if stress_signal and repeated_barking:
            state = "possible_stress"
            severity = CareSeverity.warning
            actions.append(CareActionType.music)
            music_style = "calm_piano"
        elif stress_signal or repeated_barking or environment_warning:
            state = "needs_attention"
            severity = CareSeverity.attention
            if stress_signal or repeated_barking:
                actions.append(CareActionType.music)
                music_style = "nature_sounds"

        if (
            settings.feeding_enabled
            and context.feeding_due
            and (context.feed_remaining_g or 0) >= 30
        ):
            reasons.append("최근 급식 이후 충분한 시간이 지났고 사료 잔량이 있습니다.")
            actions.append(CareActionType.feeding)
            feeding_amount_g = 50.0
            if severity == CareSeverity.info:
                state = "feeding_due"
                severity = CareSeverity.attention

        if not reasons:
            reasons.append("최근 관찰 구간에서 주의가 필요한 복합 신호가 확인되지 않았습니다.")

        if state == "possible_stress":
            summary = "불안 가능성이 있어 보호자의 확인과 진정 음악 재생을 권장합니다."
        elif state == "needs_attention":
            summary = "주의가 필요한 신호가 감지됐습니다. 상태를 확인해 주세요."
        elif state == "feeding_due":
            summary = "급식 예정 시간이 지난 것으로 판단됩니다. 급식 여부를 확인해 주세요."
        else:
            summary = "현재 관찰 구간은 안정적으로 보이며 즉시 실행할 케어는 없습니다."

        return CareSuggestionDraft(
            state=state,
            summary=summary,
            reasons=reasons,
            recommended_actions=list(dict.fromkeys(actions)),
            music_style=music_style,
            feeding_amount_g=feeding_amount_g,
            severity=severity,
        )


class GeminiProvider:
    """Gemini REST adapter that only receives aggregated, non-media context."""

    def __init__(self):
        self.model = settings.gemini_model
        self.name = f"gemini:{self.model}"

    def suggest(self, context: PetContext) -> CareSuggestionDraft:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")

        prompt = (
            "당신은 반려견의 관찰 신호를 보호자가 이해하기 쉬운 한국어 케어 피드백으로 "
            "정리하는 보조 시스템입니다. 의료 진단이나 확정적인 감정 표현을 하지 마세요. "
            "입력은 실제 영상이나 음성이 아닌 최근 15~30초의 집계값입니다. "
            "시각 신호와 반복 짖음이 함께 있을 때만 주의 수준을 높이고, 음악이 도움이 될 "
            "가능성이 있을 때만 music 액션을 선택하세요. 정상적인 휴식에는 액션을 추천하지 "
            "마세요. 급식은 현재 시스템 범위가 아니므로 추천하지 마세요. 보호자가 바로 할 수 "
            "있는 확인 방법을 summary에 포함하세요.\n\n"
            f"PetContext:\n{context.model_dump_json(exclude_none=True)}"
        )
        schema = {
            "type": "OBJECT",
            "properties": {
                "state": {"type": "STRING"},
                "summary": {"type": "STRING"},
                "reasons": {"type": "ARRAY", "items": {"type": "STRING"}},
                "recommended_actions": {
                    "type": "ARRAY",
                    "items": {"type": "STRING", "enum": ["music"]},
                    "maxItems": 1,
                },
                "music_style": {
                    "type": "STRING",
                    "enum": ["none", "calm_piano", "nature_sounds", "white_noise"],
                },
                "severity": {
                    "type": "STRING",
                    "enum": ["info", "attention", "warning", "urgent"],
                },
            },
            "required": [
                "state",
                "summary",
                "reasons",
                "recommended_actions",
                "music_style",
                "severity",
            ],
        }
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/{self.model}:generateContent",
            headers={
                "x-goog-api-key": settings.gemini_api_key,
                "Content-Type": "application/json",
            },
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": schema,
                    "temperature": 0.2,
                    "maxOutputTokens": 500,
                },
            },
            timeout=settings.gemini_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(text)
        if data.get("music_style") == "none":
            data["music_style"] = None
        return CareSuggestionDraft.model_validate(data)


def get_provider() -> LLMProvider:
    # Provider selection is intentionally conservative until the team chooses
    # an external vendor. Unknown settings fall back safely to local rules.
    if settings.provider == "gemini":
        return GeminiProvider()
    if settings.provider != "rule":
        print(f"[Care] 미지원 제공자 '{settings.provider}', 규칙 기반으로 폴백합니다.")
    return RuleBasedProvider()
