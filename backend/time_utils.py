"""统一处理 UTC 写入，以及历史无时区时间的兼容读取。"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.types import String, TypeDecorator


UTC = timezone.utc
LEGACY_SERVER_TIMEZONE = ZoneInfo("America/Los_Angeles")


def utc_now() -> datetime:
    """返回带 UTC 时区信息的当前时间。"""
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """历史无时区值按原服务器时区解释；新值统一转换为 UTC。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=LEGACY_SERVER_TIMEZONE)
    return value.astimezone(UTC)


class UTCDateTime(TypeDecorator):
    """在 SQLite 中保存带 Z 的 ISO 8601，并兼容读取历史本地时间。"""

    impl = String(40)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            # 所有新写入点都使用 utc_now；此分支防止第三方调用重新引入本地时间。
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, datetime):
            parsed = value
        else:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return ensure_utc(parsed)
