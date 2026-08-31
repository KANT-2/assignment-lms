"""
apps/tutor/models.py — 튜터팀

GradingPolicy: 학생 성적 집계에 쓰는 상수 모음 (싱글턴). apps.tutor.grading 이 이 값으로 계산한다.
수정은 당분간 Django admin 에서만 (전용 튜터 UI 는 후속). 항상 1행만 존재.
"""
from django.db import models


class GradingPolicy(models.Model):
    # 대분류 비중 (합 1 로 정규화해서 사용)
    achievement_weight = models.FloatField(default=0.70, help_text="과제 성취도 비중")
    sincerity_weight = models.FloatField(default=0.30, help_text="성실성(제출률) 비중")

    # 성취도 내부 — 개인:팀, 선택:필수 (각 쌍을 합 1 로 정규화해서 사용)
    individual_ratio = models.FloatField(default=0.70, help_text="성취도 내 개인 과제 비중")
    team_ratio = models.FloatField(default=0.30, help_text="성취도 내 팀 과제 비중")
    optional_ratio = models.FloatField(default=0.60, help_text="성취도 내 선택 과제 비중")
    required_ratio = models.FloatField(default=0.40, help_text="성취도 내 필수 과제 비중")

    # 과제별 점수 규칙
    required_floor = models.PositiveSmallIntegerField(
        default=40, help_text="필수 과제 제출 시 최저 보장 점수"
    )
    optional_floor = models.PositiveSmallIntegerField(
        default=20, help_text="선택 과제 제출 시 최저 보장 점수"
    )
    required_miss_penalty = models.PositiveSmallIntegerField(
        default=10, help_text="필수 과제 미제출 시 부여 점수"
    )

    # 중요도(weight_tier) 배수
    weight_high = models.FloatField(default=1.5)
    weight_mid = models.FloatField(default=1.0)
    weight_low = models.FloatField(default=0.5)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "grading_policy"
        verbose_name = "성적 집계 정책"
        verbose_name_plural = "성적 집계 정책"

    def __str__(self):
        return "성적 집계 정책"

    @classmethod
    def get_solo(cls) -> "GradingPolicy":
        """싱글턴 — id 최소 행 고정 (없으면 기본값으로 생성)."""
        obj = cls.objects.order_by("id").first()
        if obj is None:
            obj = cls.objects.create()
        return obj

    # --- 정규화된 비중 ---
    @staticmethod
    def _norm(a: float, b: float) -> tuple[float, float]:
        total = a + b
        return (0.5, 0.5) if total <= 0 else (a / total, b / total)

    @property
    def major_weights(self) -> tuple[float, float]:
        """(성취도, 성실성)"""
        return self._norm(self.achievement_weight, self.sincerity_weight)

    @property
    def individual_team_weights(self) -> tuple[float, float]:
        return self._norm(self.individual_ratio, self.team_ratio)

    @property
    def optional_required_weights(self) -> tuple[float, float]:
        return self._norm(self.optional_ratio, self.required_ratio)

    def tier_multiplier(self, weight_tier: str) -> float:
        return {
            "HIGH": self.weight_high,
            "MID": self.weight_mid,
            "LOW": self.weight_low,
        }.get(weight_tier, self.weight_mid)

    def floor_for(self, is_required: bool) -> int:
        return self.required_floor if is_required else self.optional_floor
