"""
SCORING V2 러너
- 원본 main_kbeauty_final_youtube.py를 수정하지 않음
- 점수 계산 함수만 V2로 덮어쓴 후 실행
"""
import math
from collections import Counter
from typing import Dict, List, Tuple

import main_kbeauty_final_youtube as m

# ============================================================
# SCORING V2 — 플랫폼 가중치 + EMA + Z-score + Novelty
# ============================================================

PLATFORM_WEIGHTS = {
    "tiktok": 1.5,     # 트렌드 선도 (가장 빠름)
    "instagram": 1.2,  # 확산 중
    "youtube": 1.0,    # 기준 (안정화)
    "amazon": 0.9,     # 실제 구매
    "google": 0.8,     # 검색 의도 (늦게 감지)
}


def _platform_weight(platform):
    p = (platform or "").lower()
    for key, w in PLATFORM_WEIGHTS.items():
        if key in p:
            return w
    return 1.0


def build_daily_keyword_counts(
    signals: List[Dict]
) -> Dict[Tuple[str, str, str], float]:
    """V2: 플랫폼 가중치가 적용된 독립 sample 수 (sample 내 반복은 중복 가산 안 함)."""
    counts = Counter()

    for signal in signals:
        platform = signal["platform"]
        region = signal["region"]
        weight = _platform_weight(platform)
        keyword_counts = m.count_keywords_in_text(signal["text"])

        for keyword in keyword_counts:
            counts[(keyword, platform, region)] += weight

    return counts


def calculate_velocity(
    today_mentions: float,
    history: List[Tuple[str, int]]
) -> Tuple[float, bool]:
    """
    V2 velocity ([-1, 1]):
      - EMA baseline(최근일 가중) 대비 Z-score → outlier 견고
      - 과거 언급 0 = NOVELTY → 볼륨 비례 보너스
    """
    values = [x for _, x in history]

    # 1) Novelty: 윈도우 내 첫 등장
    if not values or all(v <= 0 for v in values):
        if today_mentions <= 0:
            return 0.0, False
        volume01 = min(math.log1p(today_mentions) / math.log1p(30), 1.0)
        return 0.6 + 0.4 * volume01, True

    # 2) EMA baseline
    n = len(values)
    weights = [0.5 ** (n - 1 - i) for i in range(n)]
    ema = sum(w * v for w, v in zip(weights, values)) / sum(weights)

    # 3) Z-score 정규화
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    std = math.sqrt(var)

    if std < 1e-9:
        delta = (today_mentions - ema) / max(ema, 1.0)
        return max(-1.0, min(1.0, delta / 2.0)), True

    z = (today_mentions - ema) / std
    return max(-1.0, min(1.0, z / 3.0)), True


def calculate_persistence(
    history: List[Tuple[str, int]],
    window_days: int = 7
) -> float:
    """V2: 최근 가중 지속성 (어제/오늘 언급이 더 가치 있음)."""
    if not history:
        return 0.0

    n = len(history)
    weights = [0.5 ** (n - 1 - i) for i in range(n)]
    w_sum = sum(weights) or 1.0

    active_w = sum(w for w, (_, x) in zip(weights, history) if x > 0)
    return min(active_w / w_sum, 1.0)


def calculate_cross_platform(
    keyword: str,
    signal_date: str
) -> float:
    """V2: 가중 플랫폼 다양성 (TikTok+Insta+YouTube > Google 3개)."""
    conn = m.get_db()

    rows = conn.execute("""
        SELECT DISTINCT platform
        FROM keyword_daily
        WHERE keyword = ?
          AND signal_date = ?
          AND mentions > 0
    """, (keyword, signal_date)).fetchall()

    conn.close()

    weighted = sum(_platform_weight(r["platform"]) for r in rows)
    return min(weighted / 2.7, 1.0)


def calculate_volume_score(today_mentions: float) -> float:
    """V2: 로그 스케일, 포화 상한 완화."""
    if today_mentions <= 0:
        return 0.0
    return min(math.log1p(today_mentions) / math.log1p(50), 1.0)


# ============================================================
# 원본 모듈의 점수 함수를 V2로 덮어쓰기
# (원본 내부 호출도 모듈 globals를 거치므로 전부 V2로 동작)
# ============================================================
m.build_daily_keyword_counts = build_daily_keyword_counts
m.calculate_velocity = calculate_velocity
m.calculate_persistence = calculate_persistence
m.calculate_cross_platform = calculate_cross_platform
m.calculate_volume_score = calculate_volume_score

if __name__ == "__main__":
    m.main()
