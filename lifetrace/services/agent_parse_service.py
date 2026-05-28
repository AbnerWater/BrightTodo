"""BrightToDo 自然语言待办解析服务"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from lifetrace.schemas.agent import AgentParseTaskResponse
from lifetrace.schemas.todo import TodoPriority
from lifetrace.util.time_utils import get_utc_now

PARSE_VERSION = "brighttodo-s1-rule-1.0"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_DUE_TIME = time(23, 59)
NOON_HOUR = 12
MIDDAY_START_HOUR = 11
MAX_HOUR = 23
MAX_MINUTE = 59

CN_NUMBERS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

WEEKDAY_MAP = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}

TASK_VERBS = (
    "完成",
    "提交",
    "交",
    "复习",
    "背",
    "回复",
    "整理",
    "准备",
    "做",
    "打扫",
    "买",
    "写",
    "看",
)


@dataclass(frozen=True)
class DateMatch:
    due_date: date
    matched_text: str


@dataclass(frozen=True)
class TimeMatch:
    due_time: time
    matched_text: str


class AgentParseService:
    """解析中文自然语言任务描述。

    该服务用于课程 Sprint 1 演示链路，优先保证确定性和可测试性，不依赖外部 LLM。
    """

    def parse_task(
        self, text: str, reference_time: datetime | None = None
    ) -> AgentParseTaskResponse:
        raw_text = text.strip()
        reference = self._normalize_reference_time(reference_time)
        date_match = self._extract_due_date(raw_text, reference)
        time_match = self._extract_due_time(raw_text)
        due = self._build_due_datetime(date_match, time_match, reference)
        priority = self._extract_priority(raw_text)
        duration = self._extract_duration(raw_text)
        title = self._extract_title(raw_text)
        confidence = self._calculate_confidence(title, due, duration, priority)

        return AgentParseTaskResponse(
            task_title=title,
            priority=priority,
            due=due,
            duration=duration,
            description=self._build_description(raw_text, duration),
            confidence=confidence,
            raw_text=raw_text,
            parse_version=PARSE_VERSION,
        )

    def _normalize_reference_time(self, reference_time: datetime | None) -> datetime:
        if reference_time is None:
            return get_utc_now().astimezone(LOCAL_TZ)
        if reference_time.tzinfo is None:
            return reference_time.replace(tzinfo=LOCAL_TZ)
        return reference_time.astimezone(LOCAL_TZ)

    def _parse_number(self, value: str) -> int | None:
        value = value.strip()
        result: int | None
        if not value:
            result = None
        elif value.isdigit():
            result = int(value)
        elif value == "半":
            result = 0
        elif "十" in value:
            left, _, right = value.partition("十")
            tens = CN_NUMBERS.get(left, 1) if left else 1
            ones = CN_NUMBERS.get(right, 0) if right else 0
            result = tens * 10 + ones
        elif len(value) == 1:
            result = CN_NUMBERS.get(value)
        else:
            total = 0
            for char in value:
                number = CN_NUMBERS.get(char)
                if number is None:
                    result = None
                    break
                total = total * 10 + number
            else:
                result = total
        return result

    def _extract_due_date(self, text: str, reference: datetime) -> DateMatch | None:
        explicit = self._extract_explicit_month_day(text, reference)
        if explicit:
            return explicit

        relative = self._extract_relative_date(text, reference)
        if relative:
            return relative

        weekday = self._extract_weekday_date(text, reference)
        if weekday:
            return weekday

        if re.search(r"(本周|这周|本星期|这个星期)内", text):
            return DateMatch(reference.date() + timedelta(days=6), "本周内")

        return None

    def _extract_explicit_month_day(self, text: str, reference: datetime) -> DateMatch | None:
        pattern = r"(?P<month>\d{1,2}|[一二三四五六七八九十]{1,3})月(?P<day>\d{1,2}|[一二三四五六七八九十]{1,3})(?:号|日)?"
        match = re.search(pattern, text)
        if not match:
            return None
        month = self._parse_number(match.group("month"))
        day = self._parse_number(match.group("day"))
        if month is None or day is None:
            return None
        year = reference.year
        try:
            target = date(year, month, day)
        except ValueError:
            return None
        if target < reference.date():
            target = date(year + 1, month, day)
        return DateMatch(target, match.group(0))

    def _extract_relative_date(self, text: str, reference: datetime) -> DateMatch | None:
        fixed_offsets = [
            ("大后天", 3),
            ("后天", 2),
            ("明天", 1),
            ("今天", 0),
            ("今晚", 0),
        ]
        for keyword, offset in fixed_offsets:
            if keyword in text:
                return DateMatch(reference.date() + timedelta(days=offset), keyword)

        day_match = re.search(r"(?P<num>\d+|[一二两三四五六七八九十]+)天后", text)
        if day_match:
            days = self._parse_number(day_match.group("num"))
            if days is not None:
                return DateMatch(reference.date() + timedelta(days=days), day_match.group(0))

        week_match = re.search(r"(?P<num>\d+|[一二两三四五六七八九十]*)周后", text)
        if week_match:
            raw_num = week_match.group("num")
            weeks = self._parse_number(raw_num) if raw_num else 1
            if weeks is not None:
                return DateMatch(reference.date() + timedelta(days=weeks * 7), week_match.group(0))

        return None

    def _extract_weekday_date(self, text: str, reference: datetime) -> DateMatch | None:
        match = re.search(r"(?P<prefix>下下周|下周|本周|这周|周|星期)(?P<weekday>[一二三四五六日天])", text)
        if not match:
            return None
        weekday = WEEKDAY_MAP[match.group("weekday")]
        prefix = match.group("prefix")
        current_week_start = reference.date() - timedelta(days=reference.weekday())
        if prefix == "下下周":
            week_offset = 2
        elif prefix == "下周":
            week_offset = 1
        else:
            week_offset = 0
        target = current_week_start + timedelta(days=week_offset * 7 + weekday)
        if prefix in {"周", "星期"} and target < reference.date():
            target += timedelta(days=7)
        return DateMatch(target, match.group(0))

    def _extract_due_time(self, text: str) -> TimeMatch | None:
        for extractor in (
            self._extract_noon_deadline_time,
            self._extract_colon_time,
            self._extract_early_hour_time,
            self._extract_named_time,
        ):
            result = extractor(text)
            if result:
                return result
        return None

    def _extract_noon_deadline_time(self, text: str) -> TimeMatch | None:
        noon_deadline = re.search(r"中午(?:之前|前)", text)
        if noon_deadline:
            return TimeMatch(time(12, 0), noon_deadline.group(0))
        return None

    def _extract_colon_time(self, text: str) -> TimeMatch | None:
        colon_match = re.search(r"(?P<hour>\d{1,2})[:：](?P<minute>\d{2})", text)
        if colon_match:
            hour = int(colon_match.group("hour"))
            minute = int(colon_match.group("minute"))
            if self._is_valid_time(hour, minute):
                return TimeMatch(time(hour, minute), colon_match.group(0))
        return None

    def _extract_early_hour_time(self, text: str) -> TimeMatch | None:
        early_match = re.search(r"早(?P<hour>\d{1,2}|[一二三四五六七八九十])", text)
        if early_match:
            hour = self._parse_number(early_match.group("hour"))
            if hour is not None and self._is_valid_time(hour, 0):
                return TimeMatch(time(hour, 0), early_match.group(0))
        return None

    def _extract_named_time(self, text: str) -> TimeMatch | None:
        pattern = (
            r"(?P<period>凌晨|早上|上午|中午|下午|傍晚|晚上|今晚)?"
            r"(?P<hour>\d{1,2}|[一二两三四五六七八九十]{1,3})"
            r"(?:点|时)"
            r"(?P<half>半)?"
            r"(?:(?P<minute>\d{1,2}|[一二三四五六七八九十]{1,3})分?)?"
        )
        match = re.search(pattern, text)
        if not match:
            return None
        hour = self._parse_number(match.group("hour"))
        if hour is None:
            return None
        minute = 30 if match.group("half") else 0
        minute_text = match.group("minute")
        if minute_text:
            parsed_minute = self._parse_number(minute_text)
            if parsed_minute is not None:
                minute = parsed_minute

        period = match.group("period") or ""
        hour = self._apply_period(hour, period)
        if self._is_valid_time(hour, minute):
            return TimeMatch(time(hour, minute), match.group(0))
        return None

    def _apply_period(self, hour: int, period: str) -> int:
        if period in {"下午", "傍晚", "晚上", "今晚"} and hour < NOON_HOUR:
            return hour + NOON_HOUR
        if period == "中午" and hour < MIDDAY_START_HOUR:
            return hour + NOON_HOUR
        if period in {"凌晨", "早上", "上午"} and hour == NOON_HOUR:
            return 0
        return hour

    def _is_valid_time(self, hour: int, minute: int) -> bool:
        return 0 <= hour <= MAX_HOUR and 0 <= minute <= MAX_MINUTE

    def _build_due_datetime(
        self,
        date_match: DateMatch | None,
        time_match: TimeMatch | None,
        reference: datetime,
    ) -> datetime | None:
        if not date_match and not time_match:
            return None
        due_date = date_match.due_date if date_match else reference.date()
        due_time = time_match.due_time if time_match else DEFAULT_DUE_TIME
        return datetime.combine(due_date, due_time, tzinfo=LOCAL_TZ)

    def _extract_priority(self, text: str) -> TodoPriority:
        if re.search(r"不急|不着急|低优先级|低优先|有空", text):
            return TodoPriority.LOW
        if re.search(r"非常紧急|很紧急|比较紧急|紧急|高优先级|高优先|重要|马上", text):
            return TodoPriority.HIGH
        if re.search(r"中等优先级|中优先级|中等|普通优先级|一般优先级", text):
            return TodoPriority.MEDIUM
        if re.search(r"线代|线性代数", text):
            return TodoPriority.MEDIUM
        return TodoPriority.NONE

    def _extract_duration(self, text: str) -> str | None:
        half_hour = re.search(r"半小时", text)
        if half_hour:
            return "PT30M"

        hour_match = re.search(
            r"(?:需要|预计|大概需要|大概要|要)?(?P<num>\d+(?:\.\d+)?|[一二两三四五六七八九十]+)(?:个)?(?:半)?小时",
            text,
        )
        if hour_match:
            raw_num = hour_match.group("num")
            hours = float(raw_num) if re.match(r"\d+(?:\.\d+)?", raw_num) else self._parse_number(raw_num)
            if hours is None:
                return None
            if "半小时" not in hour_match.group(0) and "半" in hour_match.group(0):
                hours = float(hours) + 0.5
            minutes = int(float(hours) * 60)
            return self._format_duration(minutes)

        minute_match = re.search(r"(?P<num>\d+|[一二两三四五六七八九十]+)分钟", text)
        if minute_match:
            minutes = self._parse_number(minute_match.group("num"))
            if minutes:
                return self._format_duration(minutes)
        return None

    def _format_duration(self, minutes: int) -> str:
        if minutes % 60 == 0:
            return f"PT{minutes // 60}H"
        return f"PT{minutes}M"

    def _extract_title(self, text: str) -> str:
        cleaned = text.strip()
        cleanup_patterns = [
            r"紧急[:：]\s*",
            r"截止日期是",
            r"(?:大概需要|预计|大概要|需要|要)?\d+(?:\.\d+)?(?:个)?(?:半)?小时",
            r"(?:大概需要|预计|大概要|需要|要)?[一二两三四五六七八九十]+(?:个)?(?:半)?小时",
            r"\d+分钟",
            r"[一二两三四五六七八九十]+分钟",
            r"半小时",
            r"非常紧急|很紧急|比较紧急|紧急|高优先级|中等优先级|中优先级|低优先级|不急|不着急|低优先|高优先",
            r"\d{1,2}[:：]\d{2}",
            r"(?:凌晨|早上|上午|中午|下午|傍晚|晚上|今晚)?[一二两三四五六七八九十\d]{1,3}(?:点|时)(?:半)?(?:[一二三四五六七八九十\d]{1,3}分?)?",
            r"(今天|明天|后天|大后天|今晚)(?:凌晨|早上|上午|中午|下午|傍晚|晚上)?(?:[一二两三四五六七八九十\d]{1,3}(?:点|时)(?:半)?(?:[一二三四五六七八九十\d]{1,3}分?)?)?",
            r"[一二两三四五六七八九十\d]+天后",
            r"[一二两三四五六七八九十\d]*周后",
            r"(下下周|下周|本周|这周|周|星期)[一二三四五六日天]?",
            r"[一二三四五六七八九十\d]{1,3}月[一二三四五六七八九十\d]{1,3}(?:号|日)?",
            r"早[一二三四五六七八九十\d]{1,2}",
            r"之前|前|以内|内",
        ]
        for pattern in cleanup_patterns:
            cleaned = re.sub(pattern, "", cleaned)
        cleaned = re.sub(r"[，,。；;、!！]+", "，", cleaned)
        cleaned = cleaned.strip(" ，,。；;、!！")

        segments = [segment.strip(" ，,。；;、") for segment in re.split(r"[，,；;]", cleaned)]
        segments = [segment for segment in segments if segment]
        if not segments:
            return text.strip()[:60]
        return max(segments, key=self._title_score)[:80]

    def _title_score(self, segment: str) -> tuple[int, int]:
        verb_score = sum(1 for verb in TASK_VERBS if verb in segment)
        return verb_score, len(segment)

    def _build_description(self, raw_text: str, duration: str | None) -> str:
        parts = [f"来源自然语言：{raw_text}"]
        if duration:
            parts.append(f"预估时长：{duration}")
        return "\n".join(parts)

    def _calculate_confidence(
        self,
        title: str,
        due: datetime | None,
        duration: str | None,
        priority: TodoPriority,
    ) -> float:
        confidence = 0.72 if title else 0.45
        if due:
            confidence += 0.1
        if duration:
            confidence += 0.05
        if priority != TodoPriority.NONE:
            confidence += 0.05
        return min(round(confidence, 2), 0.95)
