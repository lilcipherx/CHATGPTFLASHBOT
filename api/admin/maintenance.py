"""Admin: Maintenance Center — бэкап, состояние системы, обслуживание БД, медиа,
кэш и логи (ТЗ §8).

Read-only телеметрия (роль admin) — дёшево и без миграций, из реальных источников:
* ``GET /maintenance/overview``  — снимок: движок/размер/фрагментация БД (PRAGMA),
  диск (shutil), Redis (INFO), ключевые счётчики, аптайм процесса, состояние лога.
* ``GET /maintenance/database``  — построчная статистика по таблицам + постраничные
  метрики SQLite.
* ``GET /maintenance/storage``   — объёмы медиа по категориям (локальный режим).
* ``GET /maintenance/cache``     — статистика Redis + число ключей перестраиваемого
  app-кэша.
* ``GET /maintenance/logs?limit=N`` — последние N строк лог-файла. Путь берётся
  ТОЛЬКО из конфига (защита от path traversal).

Безопасные действия (роль superadmin, всё в аудите):
* ``GET  /maintenance/backup``   — консистентный снимок SQLite через ``VACUUM INTO``
  (на Postgres — 501, делать ``pg_dump`` на стороне инфраструктуры).
* ``POST /maintenance/database/{op}`` — VACUUM/ANALYZE/REINDEX/OPTIMIZE/Integrity
  из фиксированного allowlist (произвольный SQL невозможен); SQLite-only.
* ``POST /maintenance/cache/flush`` — сброс ТОЛЬКО перестраиваемых кэшей приложения
  по безопасным префиксам (никогда не FLUSHALL — FSM/контекст/лимиты не трогаются).
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from api.admin.audit import audit
from api.admin.deps import require_role
from core.config import settings
from core.db import engine, get_session
from core.models import AdminAuditLog, AdminUser, Base, GenerationJob, Transaction, User
from core.redis_client import redis_client
from core.services import storage

router = APIRouter(prefix="/maintenance", tags=["admin-maintenance"])

# Жёсткий потолок на число читаемых строк лога — защита от выгрузки гигабайтных
# файлов в память по запросу с огромным limit.
_LOGS_MAX_LIMIT = 5000
# Запасной путь к логу, если в конфиге не задан settings.log_file. Лежит рядом с
# проектом, а не по пути от пользователя — path traversal невозможен.
_DEFAULT_LOG_PATH = "logs/app.log"

# Процесс стартовал — для аптайма (монотонно растёт, без psutil).
_PROCESS_STARTED = time.time()

# Разрешённый набор обслуживающих операций над БД. Имя → (SQL, требует ли отдельного
# соединения вне транзакции). Только этот фиксированный список — произвольный SQL не
# выполняется (защита от инъекций).
_DB_OPS: dict[str, tuple[str, bool]] = {
    "vacuum": ("VACUUM", True),            # дефрагментация + сжатие, вне транзакции
    "analyze": ("ANALYZE", False),         # пересбор статистики планировщика
    "reindex": ("REINDEX", True),          # перестроение индексов
    "optimize": ("PRAGMA optimize", False),  # авто-ANALYZE по эвристике SQLite
    "integrity_check": ("PRAGMA integrity_check", False),  # проверка целостности
}
# Безопасные для сброса префиксы кэша — это перестраиваемые кэши приложения, а не
# рабочие данные (FSM/контекст/лимиты). НИКОГДА не используем FLUSHALL.
_CACHE_PREFIXES = ("cache:", "admin:dashboard:")


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _engine_kind() -> str:
    return "sqlite" if _is_sqlite() else "postgres"


async def _sqlite_db_stats(session: AsyncSession) -> dict:
    """Размер, постраничная статистика и фрагментация SQLite через PRAGMA —
    дёшево, без чтения данных."""
    page_size = int(await session.scalar(text("PRAGMA page_size")) or 0)
    page_count = int(await session.scalar(text("PRAGMA page_count")) or 0)
    freelist = int(await session.scalar(text("PRAGMA freelist_count")) or 0)
    src = _sqlite_db_path()
    file_bytes = os.path.getsize(src) if src and os.path.isfile(src) else page_size * page_count
    logical = page_size * page_count
    frag = round(freelist / page_count * 100, 1) if page_count else 0.0
    return {
        "size_bytes": file_bytes,
        "logical_bytes": logical,
        "page_size": page_size,
        "page_count": page_count,
        "freelist_pages": freelist,
        "free_bytes": freelist * page_size,
        "fragmentation_pct": frag,
        "path": src,
    }


async def _redis_stats() -> dict:
    """Память/попадания/ключи Redis из INFO — best-effort, никогда не падает."""
    try:
        info = await redis_client.info()
        hits = int(info.get("keyspace_hits", 0) or 0)
        misses = int(info.get("keyspace_misses", 0) or 0)
        keys = 0
        for k, v in info.items():
            if k.startswith("db") and isinstance(v, dict):
                keys += int(v.get("keys", 0) or 0)
        total = hits + misses
        return {
            "ok": True,
            "used_memory_bytes": int(info.get("used_memory", 0) or 0),
            "keys": keys,
            "hits": hits,
            "misses": misses,
            "hit_rate_pct": round(hits / total * 100, 1) if total else None,
            "uptime_seconds": int(info.get("uptime_in_seconds", 0) or 0),
            "version": str(info.get("redis_version", "")),
        }
    except Exception:  # noqa: BLE001 — мониторинг кэша не должен ронять страницу
        return {"ok": False}


def _disk_stats() -> dict:
    """Использование тома, где лежит БД/проект — через стандартный shutil (без psutil)."""
    if _is_sqlite():
        try:
            target = os.path.dirname(os.path.abspath(_sqlite_db_path())) or "."
        except HTTPException:
            target = "."
    else:
        target = "."
    try:
        total, used, free = shutil.disk_usage(target)
        return {
            "total_bytes": total, "used_bytes": used, "free_bytes": free,
            "percent": round(used / total * 100, 1) if total else 0.0,
            "path": os.path.abspath(target),
        }
    except OSError:
        return {"total_bytes": 0, "used_bytes": 0, "free_bytes": 0, "percent": 0.0, "path": ""}


def _is_sqlite() -> bool:
    """Определяем СУБД по префиксу database_url (sqlite vs postgres)."""
    return settings.database_url.startswith("sqlite")


def _sqlite_db_path() -> str:
    """Путь к файлу SQLite из database_url вида
    ``sqlite+aiosqlite:///./app.db`` → ``./app.db``."""
    url = settings.database_url
    # Отрезаем схему до первого '///'. Поддерживаем как абсолютные
    # (////abs/path), так и относительные (///rel/path) формы.
    marker = ":///"
    idx = url.find(marker)
    if idx == -1:
        raise HTTPException(status_code=500, detail="cannot parse sqlite path")
    return url[idx + len(marker):]


def _log_path() -> Path:
    """Единственный разрешённый путь к лог-файлу — из конфига (или дефолт).
    Пользователь НЕ влияет на путь, поэтому path traversal исключён."""
    configured = (getattr(settings, "log_file", "") or "").strip()
    return Path(configured or _DEFAULT_LOG_PATH)


def _tail(path: Path, limit: int) -> list[str]:
    """Последние ``limit`` строк файла без чтения его целиком в память."""
    if not path.is_file():
        return []
    tail: deque[str] = deque(maxlen=limit)
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            tail.append(line.rstrip("\n"))
    return list(tail)


@router.get("/overview")
async def maintenance_overview(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Снимок состояния системы для дашборда Maintenance Center: движок и размер БД,
    фрагментация, диск, Redis, ключевые счётчики, состояние лога и аптайм процесса.
    Всё — дёшево и из реальных источников (PRAGMA / shutil / Redis INFO / COUNT)."""
    kind = _engine_kind()
    db: dict = {"engine": kind}
    if kind == "sqlite":
        try:
            db.update(await _sqlite_db_stats(session))
        except Exception:  # noqa: BLE001 — снимок не должен падать
            db["size_bytes"] = 0
    else:
        try:
            db["size_bytes"] = int(await session.scalar(
                text("SELECT pg_database_size(current_database())")
            ) or 0)
        except Exception:  # noqa: BLE001
            db["size_bytes"] = 0

    # Ключевые счётчики (по индексам/быстрым агрегатам).
    job_rows = (await session.execute(
        select(GenerationJob.status, func.count()).group_by(GenerationJob.status)
    )).all()
    jobs_by_status = {s: int(n) for s, n in job_rows}
    counts = {
        "users": int(await session.scalar(select(func.count()).select_from(User)) or 0),
        "jobs_total": int(sum(jobs_by_status.values())),
        "jobs_by_status": jobs_by_status,
        "transactions": int(await session.scalar(
            select(func.count()).select_from(Transaction)) or 0),
        "audit_entries": int(await session.scalar(
            select(func.count()).select_from(AdminAuditLog)) or 0),
    }

    # Лог-файл (размер/наличие — для Log Center).
    log_path = _log_path()
    log_info = {
        "path": str(log_path),
        "exists": log_path.is_file(),
        "size_bytes": log_path.stat().st_size if log_path.is_file() else 0,
    }

    last_backup = await session.scalar(
        select(func.max(AdminAuditLog.created_at)).where(
            AdminAuditLog.action == "maintenance.backup")
    )

    return {
        "engine": kind,
        "db": db,
        "disk": _disk_stats(),
        "redis": await _redis_stats(),
        "counts": counts,
        "log": log_info,
        "storage_backend": "s3" if storage.s3_enabled() else "local",
        "backup": {
            "supported": kind == "sqlite",
            "last_backup_at": last_backup.isoformat() if last_backup else None,
            "note": "SQLite: снимок через VACUUM INTO. Postgres: pg_dump на стороне инфры.",
        },
        "uptime_seconds": int(time.time() - _PROCESS_STARTED),
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.get("/database")
async def database_stats(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Построчная статистика по таблицам (COUNT на таблицу) + постраничные метрики
    SQLite. Имена таблиц берутся из метаданных моделей — не из ввода пользователя."""
    tables: list[dict] = []
    for tbl in Base.metadata.sorted_tables:
        try:
            n = int(await session.scalar(select(func.count()).select_from(tbl)) or 0)
        except Exception:  # noqa: BLE001 — недоступная таблица не должна ронять отчёт
            n = -1
        tables.append({"name": tbl.name, "rows": n, "indexes": len(tbl.indexes)})
    tables.sort(key=lambda t: t["rows"], reverse=True)

    out: dict = {"engine": _engine_kind(), "tables": tables,
                 "total_rows": sum(t["rows"] for t in tables if t["rows"] > 0)}
    if _is_sqlite():
        try:
            out["page"] = await _sqlite_db_stats(session)
        except Exception as exc:  # noqa: BLE001
            import structlog
            structlog.get_logger().warning(
                'api.admin.maintenance.database_stats_failed', error=str(exc))
            # FIX: AUDIT12-L1 - was silent except: pass
    return out


@router.post("/database/{op}")
async def run_db_maintenance(
    op: str, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Выполнить обслуживающую операцию над БД (только superadmin, только из
    фиксированного списка _DB_OPS). На Postgres — 501 с указанием делать это
    средствами инфраструктуры."""
    if op not in _DB_OPS:
        raise HTTPException(status_code=400, detail=f"unknown op; allowed: {','.join(_DB_OPS)}")
    if not _is_sqlite():
        raise HTTPException(
            status_code=501,
            detail="DB maintenance via API is SQLite-only; run it on Postgres server-side",
        )

    sql, needs_autocommit = _DB_OPS[op]
    size_before = 0
    try:
        stats = await _sqlite_db_stats(session)
        size_before = stats["size_bytes"]
    except Exception as exc:  # noqa: BLE001 — FIX: L10 - log so failures are observable
        import structlog
        structlog.get_logger().warning("maintenance.exception", error=str(exc))

    started = time.perf_counter()
    result_text = "ok"
    if needs_autocommit:
        # VACUUM/REINDEX нельзя выполнять внутри открытой транзакции — отдельное
        # соединение в режиме AUTOCOMMIT.
        async with engine.connect() as conn:
            ac = await conn.execution_options(isolation_level="AUTOCOMMIT")
            await ac.execute(text(sql))
    else:
        res = await session.execute(text(sql))
        if op == "integrity_check":
            rows = res.fetchall()
            result_text = "; ".join(str(r[0]) for r in rows[:20]) or "ok"
        await session.commit()

    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    size_after = size_before
    try:
        size_after = (await _sqlite_db_stats(session))["size_bytes"]
    except Exception as exc:  # noqa: BLE001 — FIX: L10 - log so failures are observable
        import structlog
        structlog.get_logger().warning("maintenance.exception", error=str(exc))

    await audit(
        session, admin_id=admin.id, action=f"maintenance.db.{op}",
        target_type="database", target_id="sqlite",
        after={"op": op, "duration_ms": duration_ms,
               "reclaimed_bytes": max(0, size_before - size_after)}, ip=_ip(request),
    )
    return {
        "ok": True, "op": op, "result": result_text, "duration_ms": duration_ms,
        "size_before": size_before, "size_after": size_after,
        "reclaimed_bytes": max(0, size_before - size_after),
    }


@router.get("/storage")
async def storage_stats(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Размер и число файлов по категориям медиа-хранилища (локальный режим).
    Категория = верхний каталог в media/. На S3/MinIO размеры в API не считаются —
    честно сообщаем об этом (см. бакет в конфиге S3)."""
    if storage.s3_enabled():
        return {"backend": "s3", "bucket": settings.s3_bucket, "categories": [],
                "note": "Хранилище в S3/MinIO — размеры считаются на стороне стора, не через API."}
    root = Path(storage._MEDIA_ROOT)
    categories: list[dict] = []
    total_bytes = total_files = 0
    if root.is_dir():
        for entry in sorted(root.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            cat_bytes = cat_files = 0
            for dirpath, _dirs, files in os.walk(entry):
                for f in files:
                    try:
                        cat_bytes += os.path.getsize(os.path.join(dirpath, f))
                        cat_files += 1
                    except OSError:
                        continue
            categories.append({"name": entry.name, "bytes": cat_bytes, "files": cat_files})
            total_bytes += cat_bytes
            total_files += cat_files
        # Файлы в корне media/ (без подкаталога).
        loose_bytes = loose_files = 0
        for f in root.iterdir():
            if f.is_file():
                try:
                    loose_bytes += f.stat().st_size
                    loose_files += 1
                except OSError:
                    continue
        if loose_files:
            categories.append({"name": "(root)", "bytes": loose_bytes, "files": loose_files})
            total_bytes += loose_bytes
            total_files += loose_files
    categories.sort(key=lambda c: c["bytes"], reverse=True)
    return {"backend": "local", "path": str(root), "categories": categories,
            "total_bytes": total_bytes, "total_files": total_files,
            "exists": root.is_dir()}


@router.get("/cache")
async def cache_stats(
    admin: AdminUser = Depends(require_role("admin")),
) -> dict:
    """Состояние Redis-кэша + сколько ключей приходится на перестраиваемые кэши
    приложения (по безопасным префиксам)."""
    stats = await _redis_stats()
    app_cache_keys = 0
    try:
        for prefix in _CACHE_PREFIXES:
            async for _ in redis_client.scan_iter(match=f"{prefix}*", count=200):
                app_cache_keys += 1
    except Exception:  # noqa: BLE001
        app_cache_keys = -1
    return {"redis": stats, "app_cache_keys": app_cache_keys,
            "prefixes": list(_CACHE_PREFIXES)}


@router.post("/cache/flush")
async def cache_flush(
    request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Сбросить ТОЛЬКО перестраиваемые кэши приложения (cache:* / admin:dashboard:*).
    Это безопасно — данные восстанавливаются из БД при следующем запросе. Никогда не
    выполняет FLUSHALL (FSM/контекст/лимиты не трогаются). Только superadmin."""
    deleted = 0
    try:
        for prefix in _CACHE_PREFIXES:
            keys = [k async for k in redis_client.scan_iter(match=f"{prefix}*", count=200)]
            if keys:
                deleted += int(await redis_client.delete(*keys) or 0)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"redis unavailable: {exc}") from exc
    await audit(
        session, admin_id=admin.id, action="maintenance.cache.flush",
        target_type="cache", target_id="app",
        after={"deleted": deleted, "prefixes": list(_CACHE_PREFIXES)}, ip=_ip(request),
    )
    return {"ok": True, "deleted": deleted}


@router.get("/backup")
async def download_backup(
    request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    """Скачать снимок БД (только superadmin).

    SQLite (dev): консистентный снимок через ``VACUUM INTO`` во временный файл,
    который отдаётся как вложение и удаляется после отправки. Postgres: 501 —
    бэкап выполняется средствами инфраструктуры (``pg_dump``)."""
    if not _is_sqlite():
        # Дамп Postgres силами приложения небезопасен/неполон — честный 501.
        raise HTTPException(
            status_code=501,
            detail="backup not supported for postgres via API; use pg_dump",
        )

    src = _sqlite_db_path()
    if not src or not os.path.isfile(src):
        raise HTTPException(status_code=404, detail="database file not found")

    # VACUUM INTO даёт согласованную копию БД даже при активных записях, в
    # отличие от простого копирования файла на лету.
    fd, tmp_path = tempfile.mkstemp(prefix="backup_", suffix=".sqlite")
    os.close(fd)
    os.unlink(tmp_path)  # VACUUM INTO требует, чтобы целевой файл не существовал
    # Экранируем апострофы в пути для безопасной подстановки в SQL-литерал.
    safe = tmp_path.replace("'", "''")
    await session.execute(text(f"VACUUM INTO '{safe}'"))

    await audit(
        session, admin_id=admin.id, action="maintenance.backup",
        target_type="database", target_id="sqlite",
        after={"bytes": os.path.getsize(tmp_path)}, ip=_ip(request),
    )
    return FileResponse(
        tmp_path,
        media_type="application/octet-stream",
        filename="backup.sqlite",
        background=BackgroundTask(lambda: os.path.exists(tmp_path) and os.unlink(tmp_path)),
    )


@router.get("/logs")
async def view_logs(
    request: Request,
    limit: int = 200,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Последние ``limit`` строк лог-файла приложения (только superadmin).

    Путь к логу фиксирован конфигом — пользователь его не задаёт. Если файла
    нет, возвращается пустой список (без ошибки)."""
    limit = max(1, min(limit, _LOGS_MAX_LIMIT))
    path = _log_path()
    lines = _tail(path, limit)
    await audit(
        session, admin_id=admin.id, action="maintenance.logs",
        target_type="log", target_id=str(path),
        after={"lines": len(lines), "limit": limit}, ip=_ip(request),
    )
    return {"path": str(path), "lines": lines, "count": len(lines)}
