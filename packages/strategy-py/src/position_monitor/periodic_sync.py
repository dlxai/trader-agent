"""
Layer 2: 定时链上持仓同步系统
每 60 秒批量查询链上持仓，检测并修正持仓漂移

主要组件:
1. PositionStore - SQLite 持仓存储
2. ChainPositionSync - 链上同步器
3. PositionEvent - 持仓事件类型
"""

import asyncio
import logging
import sqlite3
import json
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
import threading

from web3 import Web3
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import settings


logger = logging.getLogger(__name__)


class PositionEventType(Enum):
    """持仓事件类型"""
    POSITION_CREATED = "position_created"      # 新增持仓
    POSITION_UPDATED = "position_updated"        # 持仓更新
    POSITION_CLOSED = "position_closed"          # 持仓平仓
    POSITION_DRIFT_DETECTED = "position_drift"   # 检测到持仓漂移
    SYNC_COMPLETED = "sync_completed"            # 同步完成
    SYNC_FAILED = "sync_failed"                  # 同步失败
    CHAIN_ERROR = "chain_error"                  # 链上查询错误


@dataclass
class PositionEvent:
    """持仓事件"""
    event_type: PositionEventType
    position_id: Optional[str] = None
    token_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None


@dataclass
class PositionRecord:
    """持仓记录 - 数据库存储格式"""
    position_id: str
    token_id: str
    market_id: str
    side: str  # "BUY" or "SELL"
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    status: str  # "open", "closed", "partial"
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None
    chain_synced_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChainPosition:
    """
    链上持仓数据

    从 Polymarket API 查询得到的原始持仓数据
    """
    token_id: str
    balance: float
    last_updated: datetime
    market_id: Optional[str] = None
    condition_id: Optional[str] = None
    outcome: Optional[str] = None
    avg_entry_price: Optional[float] = None
    current_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None
    raw_data: Optional[Dict[str, Any]] = field(default_factory=dict)


@dataclass
class SyncResult:
    """同步结果"""
    position_id: str
    token_id: str
    local_size: float
    chain_size: float
    drift: float
    action: str  # "sync", "exit", "warning", "none"
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class PositionStore:
    """
    持仓数据库存储

    功能：
    1. SQLite 数据库存储持仓数据
    2. 支持持仓的 CRUD 操作
    3. 持仓历史记录查询
    4. 链上同步状态追踪
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        初始化持仓存储

        Args:
            db_path: 数据库文件路径，默认使用配置中的路径
        """
        if db_path is None:
            db_path = settings.database.get("url", "sqlite:///data/trader.db")
            if db_path.startswith("sqlite:///"):
                db_path = db_path[10:]

        self.db_path = db_path
        self._lock = threading.RLock()

        # 确保目录存在
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # 初始化数据库
        self._init_db()

        logger.info(f"PositionStore initialized with database: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化数据库表结构"""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()

                # 持仓主表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS positions (
                        position_id TEXT PRIMARY KEY,
                        token_id TEXT NOT NULL,
                        market_id TEXT NOT NULL,
                        side TEXT NOT NULL,
                        size REAL NOT NULL,
                        entry_price REAL NOT NULL,
                        current_price REAL DEFAULT 0,
                        unrealized_pnl REAL DEFAULT 0,
                        realized_pnl REAL DEFAULT 0,
                        status TEXT DEFAULT 'open',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        closed_at TIMESTAMP,
                        chain_synced_at TIMESTAMP,
                        metadata TEXT
                    )
                """)

                # 持仓历史记录表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS position_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        position_id TEXT NOT NULL,
                        token_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        old_size REAL,
                        new_size REAL,
                        old_price REAL,
                        new_price REAL,
                        pnl REAL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        metadata TEXT,
                        FOREIGN KEY (position_id) REFERENCES positions(position_id)
                    )
                """)

                # 链上同步记录表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS chain_sync_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sync_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        positions_synced INTEGER DEFAULT 0,
                        drifts_found INTEGER DEFAULT 0,
                        exits_triggered INTEGER DEFAULT 0,
                        errors INTEGER DEFAULT 0,
                        elapsed_ms REAL,
                        metadata TEXT
                    )
                """)

                # 创建索引
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_positions_token_id ON positions(token_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_position_history_position_id ON position_history(position_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_chain_sync_time ON chain_sync_log(sync_time)
                """)

                conn.commit()
                logger.info("Database tables initialized successfully")

            finally:
                conn.close()

    def save_position(self, position: PositionRecord) -> bool:
        """
        保存持仓记录

        Args:
            position: 持仓记录

        Returns:
            是否保存成功
        """
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()

                metadata_json = json.dumps(position.metadata) if position.metadata else "{}"

                cursor.execute("""
                    INSERT OR REPLACE INTO positions (
                        position_id, token_id, market_id, side, size,
                        entry_price, current_price, unrealized_pnl, realized_pnl,
                        status, created_at, updated_at, closed_at, chain_synced_at, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    position.position_id, position.token_id, position.market_id,
                    position.side, position.size, position.entry_price,
                    position.current_price, position.unrealized_pnl, position.realized_pnl,
                    position.status, position.created_at, position.updated_at,
                    position.closed_at, position.chain_synced_at, metadata_json
                ))

                conn.commit()

                # 记录历史
                self._record_history(
                    position.position_id, position.token_id, "save",
                    position.size, position.size, position.entry_price, position.current_price
                )

                logger.debug(f"Position saved: {position.position_id}")
                return True

            except Exception as e:
                conn.rollback()
                logger.error(f"Error saving position: {e}")
                return False
            finally:
                conn.close()

    def get_position(self, position_id: str) -> Optional[PositionRecord]:
        """
        获取持仓记录

        Args:
            position_id: 持仓ID

        Returns:
            持仓记录，如果不存在则返回 None
        """
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT * FROM positions WHERE position_id = ?
                """, (position_id,))

                row = cursor.fetchone()

                if row:
                    return self._row_to_position_record(row)
                return None

            except Exception as e:
                logger.error(f"Error getting position: {e}")
                return None
            finally:
                conn.close()

    def get_all_positions(self, status: Optional[str] = None) -> List[PositionRecord]:
        """
        获取所有持仓记录

        Args:
            status: 按状态过滤（可选）

        Returns:
            持仓记录列表
        """
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()

                if status:
                    cursor.execute("""
                        SELECT * FROM positions WHERE status = ? ORDER BY created_at DESC
                    """, (status,))
                else:
                    cursor.execute("""
                        SELECT * FROM positions ORDER BY created_at DESC
                    """)

                rows = cursor.fetchall()

                return [self._row_to_position_record(row) for row in rows]

            except Exception as e:
                logger.error(f"Error getting all positions: {e}")
                return []
            finally:
                conn.close()

    def update_position_size(
        self,
        position_id: str,
        new_size: float,
        new_price: float,
        pnl: float = 0
    ) -> bool:
        """
        更新持仓数量

        Args:
            position_id: 持仓ID
            new_size: 新数量
            new_price: 当前价格
            pnl: 盈亏

        Returns:
            是否更新成功
        """
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()

                # 获取当前持仓
                cursor.execute("""
                    SELECT size, current_price FROM positions WHERE position_id = ?
                """, (position_id,))

                row = cursor.fetchone()
                if not row:
                    logger.warning(f"Position not found: {position_id}")
                    return False

                old_size = row[0]
                old_price = row[1]

                # 确定状态
                status = "open"
                closed_at = None
                if new_size <= 0:
                    status = "closed"
                    closed_at = datetime.now()
                elif new_size < old_size:
                    status = "partial"

                cursor.execute("""
                    UPDATE positions
                    SET size = ?, current_price = ?, status = ?,
                        updated_at = ?, closed_at = ?,
                        realized_pnl = realized_pnl + ?
                    WHERE position_id = ?
                """, (
                    new_size, new_price, status,
                    datetime.now(), closed_at,
                    pnl, position_id
                ))

                conn.commit()

                # 记录历史
                self._record_history(
                    position_id, "", "size_update",
                    old_size, new_size, old_price, new_price, pnl
                )

                logger.debug(f"Position size updated: {position_id}, new_size={new_size}")
                return True

            except Exception as e:
                conn.rollback()
                logger.error(f"Error updating position size: {e}")
                return False
            finally:
                conn.close()

    def record_chain_sync(
        self,
        positions_synced: int,
        drifts_found: int,
        exits_triggered: int,
        errors: int,
        elapsed_ms: float,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        记录链上同步日志

        Args:
            positions_synced: 同步的持仓数量
            drifts_found: 发现的漂移数量
            exits_triggered: 触发的退出数量
            errors: 错误数量
            elapsed_ms: 耗时（毫秒）
            metadata: 额外元数据

        Returns:
            是否记录成功
        """
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()

                metadata_json = json.dumps(metadata) if metadata else None

                cursor.execute("""
                    INSERT INTO chain_sync_log (
                        sync_time, positions_synced, drifts_found,
                        exits_triggered, errors, elapsed_ms, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now(), positions_synced, drifts_found,
                    exits_triggered, errors, elapsed_ms, metadata_json
                ))

                conn.commit()
                return True

            except Exception as e:
                conn.rollback()
                logger.error(f"Error recording chain sync: {e}")
                return False
            finally:
                conn.close()

    def _record_history(
        self,
        position_id: str,
        token_id: str,
        event_type: str,
        old_size: float,
        new_size: float,
        old_price: float,
        new_price: float,
        pnl: float = 0
    ):
        """记录持仓历史"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO position_history (
                    position_id, token_id, event_type,
                    old_size, new_size, old_price, new_price,
                    pnl, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                position_id, token_id, event_type,
                old_size, new_size, old_price, new_price,
                pnl, datetime.now()
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"Error recording history: {e}")
        finally:
            conn.close()

    def _row_to_position_record(self, row: sqlite3.Row) -> PositionRecord:
        """将数据库行转换为 PositionRecord"""
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except:
                pass

        return PositionRecord(
            position_id=row["position_id"],
            token_id=row["token_id"],
            market_id=row["market_id"],
            side=row["side"],
            size=row["size"],
            entry_price=row["entry_price"],
            current_price=row["current_price"],
            unrealized_pnl=row["unrealized_pnl"],
            realized_pnl=row["realized_pnl"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            closed_at=datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None,
            chain_synced_at=datetime.fromisoformat(row["chain_synced_at"]) if row["chain_synced_at"] else None,
            metadata=metadata
        )


class ChainPositionSync:
    """
    链上持仓同步器

    职责：
    1. 定期（每60秒）从链上同步实际持仓
    2. 与本地缓存持仓对比
    3. 检测差异并触发告警
    4. 更新本地数据库

    事件回调：
    - on_position_event: 持仓事件回调
    - on_sync_complete: 同步完成回调
    - on_error: 错误回调
    """

    def __init__(
        self,
        position_store: PositionStore,
        config: Optional[Dict[str, Any]] = None,
        on_position_event: Optional[Callable[[PositionEvent], None]] = None,
        on_sync_complete: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ):
        """
        初始化链上持仓同步器

        Args:
            position_store: 持仓存储实例
            config: 配置参数
            on_position_event: 持仓事件回调
            on_sync_complete: 同步完成回调
            on_error: 错误回调
        """
        self.position_store = position_store
        self.config = config or {}

        # 回调函数
        self.on_position_event = on_position_event
        self.on_sync_complete = on_sync_complete
        self.on_error = on_error

        # 同步配置
        self.sync_interval_sec = self.config.get("sync_interval_sec", 60)
        self.drift_threshold = self.config.get("drift_threshold", 0.0001)
        self.auto_correct_drift = self.config.get("auto_correct_drift", True)
        self.max_retry_attempts = self.config.get("max_retry_attempts", 3)

        # 运行状态
        self._running = False
        self._sync_task: Optional[asyncio.Task] = None
        self._last_sync_time: Optional[datetime] = None
        self._sync_count = 0
        self._error_count = 0

        # 本地持仓缓存
        self._local_positions: Dict[str, PositionRecord] = {}

        # 统计信息
        self._stats = {
            "total_syncs": 0,
            "successful_syncs": 0,
            "failed_syncs": 0,
            "total_drifts": 0,
            "total_exits": 0,
        }

        logger.info("ChainPositionSync initialized")

    async def start(self):
        """启动同步服务"""
        if self._running:
            logger.warning("ChainPositionSync is already running")
            return

        self._running = True
        logger.info(f"Starting ChainPositionSync (interval: {self.sync_interval_sec}s)")

        # 立即执行一次同步
        await self._perform_sync()

        # 启动定时任务
        self._sync_task = asyncio.create_task(self._sync_loop())

    async def stop(self):
        """停止同步服务"""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping ChainPositionSync...")

        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

        logger.info("ChainPositionSync stopped")

    async def _sync_loop(self):
        """同步主循环"""
        while self._running:
            try:
                await asyncio.sleep(self.sync_interval_sec)

                if not self._running:
                    break

                await self._perform_sync()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._error_count += 1
                logger.error(f"Error in sync loop: {e}")
                if self.on_error:
                    try:
                        self.on_error(e)
                    except:
                        pass

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def _perform_sync(self):
        """
        执行一次同步

        1. 从数据库加载本地持仓
        2. 从链上查询实际持仓
        3. 对比并检测漂移
        4. 触发相应事件
        5. 更新数据库
        """
        start_time = datetime.now()
        self._last_sync_time = start_time
        self._sync_count += 1

        logger.info(f"Starting sync #{self._sync_count}")

        try:
            # 1. 加载本地持仓
            await self._load_local_positions()

            # 2. 查询链上持仓
            chain_positions = await self._fetch_chain_positions()

            # 3. 对比并检测漂移
            sync_results = await self._compare_positions(chain_positions)

            # 4. 更新数据库
            await self._update_database(sync_results, chain_positions)

            # 5. 触发事件
            await self._emit_sync_events(sync_results)

            # 6. 记录同步日志
            elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
            self._record_sync_log(sync_results, elapsed_ms)

            # 更新统计
            self._stats["total_syncs"] += 1
            self._stats["successful_syncs"] += 1
            self._stats["total_drifts"] += len([r for r in sync_results if abs(r.drift) > self.drift_threshold])
            self._stats["total_exits"] += len([r for r in sync_results if r.action == "exit"])

            # 回调
            if self.on_sync_complete:
                try:
                    self.on_sync_complete({
                        "sync_id": self._sync_count,
                        "timestamp": start_time,
                        "elapsed_ms": elapsed_ms,
                        "positions_synced": len(self._local_positions),
                        "chain_positions_found": len(chain_positions),
                        "drifts_detected": len(sync_results),
                        "results": [self._sync_result_to_dict(r) for r in sync_results],
                    })
                except Exception as e:
                    logger.error(f"Error in on_sync_complete callback: {e}")

            logger.info(
                f"Sync #{self._sync_count} completed in {elapsed_ms:.2f}ms: "
                f"{len(self._local_positions)} local, {len(chain_positions)} chain, "
                f"{len(sync_results)} drifts"
            )

        except Exception as e:
            self._error_count += 1
            self._stats["failed_syncs"] += 1
            logger.error(f"Sync #{self._sync_count} failed: {e}")

            # 触发错误事件
            await self._emit_event(PositionEvent(
                event_type=PositionEventType.SYNC_FAILED,
                data={"sync_id": self._sync_count, "error": str(e)},
                error=str(e)
            ))

            # 错误回调
            if self.on_error:
                try:
                    self.on_error(e)
                except:
                    pass

            raise

    async def _load_local_positions(self):
        """加载本地持仓"""
        positions = self.position_store.get_all_positions(status="open")
        self._local_positions = {p.position_id: p for p in positions}
        logger.debug(f"Loaded {len(self._local_positions)} local positions")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def _fetch_chain_positions(self) -> Dict[str, ChainPosition]:
        """
        从 Polymarket API 获取链上持仓

        Returns:
            Dict[str, ChainPosition]: key 为 token_id
        """
        try:
            # 使用 PolymarketClient 获取持仓
            from ..polymarket.client import PolymarketClient

            client = PolymarketClient(settings.polymarket)

            connected = await client.connect()
            if not connected:
                raise ConnectionError("Failed to connect to Polymarket API")

            try:
                positions = await client.get_positions()

                chain_positions = {}

                for position in positions:
                    try:
                        token_id = position.token_id
                        balance = position.size

                        if not token_id or balance <= 0.0001:
                            continue

                        chain_pos = ChainPosition(
                            token_id=token_id,
                            balance=balance,
                            last_updated=datetime.now(),
                            current_price=position.avg_entry_price if hasattr(position, 'avg_entry_price') else None,
                            unrealized_pnl=position.unrealized_pnl if hasattr(position, 'unrealized_pnl') else None,
                            realized_pnl=position.realized_pnl if hasattr(position, 'realized_pnl') else None
                        )

                        chain_positions[token_id] = chain_pos

                    except Exception as e:
                        logger.error(f"Error parsing position: {e}")
                        continue

                logger.info(f"Fetched {len(chain_positions)} positions from chain")
                return chain_positions

            finally:
                await client.disconnect()

        except Exception as e:
            logger.error(f"Error fetching chain positions: {e}")
            raise

    async def _compare_positions(
        self,
        chain_positions: Dict[str, ChainPosition]
    ) -> List[SyncResult]:
        """
        对比本地持仓和链上持仓

        Args:
            chain_positions: 链上持仓

        Returns:
            同步结果列表
        """
        results = []

        # 检查现有持仓
        for position in self._local_positions.values():
            chain_pos = chain_positions.get(position.token_id)

            if not chain_pos:
                # 链上无此持仓，可能已平仓
                result = SyncResult(
                    position_id=position.position_id,
                    token_id=position.token_id,
                    local_size=position.size,
                    chain_size=0.0,
                    drift=-position.size,
                    action="exit",
                    details={"reason": "position_not_on_chain", "recommendation": "close_local"}
                )
                results.append(result)
                continue

            # 计算漂移
            drift = chain_pos.balance - position.size

            if abs(drift) <= self.drift_threshold:
                # 无显著漂移
                continue

            # 确定操作
            action = "sync"
            details = {}

            if chain_pos.balance <= 0.0001:
                action = "exit"
                details = {"reason": "chain_position_zero"}
            elif chain_pos.balance < position.size:
                reduction_pct = (position.size - chain_pos.balance) / position.size
                action = "sync"
                details = {
                    "reason": "partial_fill_detected",
                    "reduction_pct": reduction_pct,
                    "new_size": chain_pos.balance
                }
            elif chain_pos.balance > position.size:
                increase_pct = (chain_pos.balance - position.size) / position.size
                action = "warning"
                details = {
                    "reason": "unexpected_increase",
                    "increase_pct": increase_pct
                }

            result = SyncResult(
                position_id=position.position_id,
                token_id=position.token_id,
                local_size=position.size,
                chain_size=chain_pos.balance,
                drift=drift,
                action=action,
                details=details
            )
            results.append(result)

        # 检查新增持仓（链上有但本地没有）
        local_token_ids = {p.token_id for p in self._local_positions.values()}
        for token_id, chain_pos in chain_positions.items():
            if token_id not in local_token_ids and chain_pos.balance > 0.0001:
                result = SyncResult(
                    position_id="",
                    token_id=token_id,
                    local_size=0.0,
                    chain_size=chain_pos.balance,
                    drift=chain_pos.balance,
                    action="warning",
                    details={
                        "reason": "new_position_on_chain",
                        "message": "Found new position on chain not in local database"
                    }
                )
                results.append(result)

        return results

    async def _update_database(
        self,
        sync_results: List[SyncResult],
        chain_positions: Dict[str, ChainPosition]
    ):
        """
        更新数据库

        Args:
            sync_results: 同步结果列表
            chain_positions: 链上持仓
        """
        for result in sync_results:
            try:
                # 查找对应的本地持仓
                local_pos = None
                for pos in self._local_positions.values():
                    if pos.token_id == result.token_id:
                        local_pos = pos
                        break

                if not local_pos and result.action != "exit":
                    continue

                # 获取链上数据
                chain_pos = chain_positions.get(result.token_id)

                if result.action == "exit":
                    # 更新持仓为已关闭
                    if local_pos:
                        closed_position = PositionRecord(
                            position_id=local_pos.position_id,
                            token_id=local_pos.token_id,
                            market_id=local_pos.market_id,
                            side=local_pos.side,
                            size=0.0,
                            entry_price=local_pos.entry_price,
                            current_price=local_pos.current_price,
                            unrealized_pnl=0.0,
                            realized_pnl=local_pos.realized_pnl + (result.local_size * local_pos.current_price if local_pos else 0),
                            status="closed",
                            created_at=local_pos.created_at,
                            updated_at=datetime.now(),
                            closed_at=datetime.now(),
                            chain_synced_at=datetime.now()
                        )
                        self.position_store.save_position(closed_position)

                elif result.action == "sync":
                    # 同步持仓数量
                    if local_pos and chain_pos:
                        updated_position = PositionRecord(
                            position_id=local_pos.position_id,
                            token_id=local_pos.token_id,
                            market_id=local_pos.market_id,
                            side=local_pos.side,
                            size=chain_pos.balance,
                            entry_price=local_pos.entry_price,
                            current_price=chain_pos.current_price or local_pos.current_price,
                            unrealized_pnl=chain_pos.unrealized_pnl or local_pos.unrealized_pnl,
                            realized_pnl=local_pos.realized_pnl,
                            status="open" if chain_pos.balance > 0.0001 else "closed",
                            created_at=local_pos.created_at,
                            updated_at=datetime.now(),
                            chain_synced_at=datetime.now()
                        )
                        self.position_store.save_position(updated_position)

                # 更新最后同步时间
                if local_pos:
                    local_pos.chain_synced_at = datetime.now()

            except Exception as e:
                logger.error(f"Error updating database for result {result}: {e}")

    async def _emit_sync_events(self, sync_results: List[SyncResult]):
        """
        触发同步事件

        Args:
            sync_results: 同步结果列表
        """
        for result in sync_results:
            try:
                if result.action == "exit":
                    await self._emit_event(PositionEvent(
                        event_type=PositionEventType.POSITION_CLOSED,
                        position_id=result.position_id,
                        token_id=result.token_id,
                        data={
                            "reason": "chain_sync_exit",
                            "local_size": result.local_size,
                            "chain_size": result.chain_size,
                            "drift": result.drift,
                            "details": result.details
                        }
                    ))

                elif result.action == "sync":
                    await self._emit_event(PositionEvent(
                        event_type=PositionEventType.POSITION_DRIFT_DETECTED,
                        position_id=result.position_id,
                        token_id=result.token_id,
                        data={
                            "local_size": result.local_size,
                            "chain_size": result.chain_size,
                            "drift": result.drift,
                            "details": result.details
                        }
                    ))

                elif result.action == "warning":
                    await self._emit_event(PositionEvent(
                        event_type=PositionEventType.POSITION_DRIFT_DETECTED,
                        position_id=result.position_id,
                        token_id=result.token_id,
                        data={
                            "local_size": result.local_size,
                            "chain_size": result.chain_size,
                            "drift": result.drift,
                            "details": result.details,
                            "warning": True
                        }
                    ))

            except Exception as e:
                logger.error(f"Error emitting event for result {result}: {e}")

    async def _emit_event(self, event: PositionEvent):
        """
        触发事件

        Args:
            event: 持仓事件
        """
        logger.debug(f"Emitting event: {event.event_type.value} for {event.position_id}")

        if self.on_position_event:
            try:
                if asyncio.iscoroutinefunction(self.on_position_event):
                    await self.on_position_event(event)
                else:
                    self.on_position_event(event)
            except Exception as e:
                logger.error(f"Error in position event callback: {e}")

    def _record_sync_log(self, sync_results: List[SyncResult], elapsed_ms: float):
        """
        记录同步日志

        Args:
            sync_results: 同步结果列表
            elapsed_ms: 耗时（毫秒）
        """
        try:
            drifts = len([r for r in sync_results if abs(r.drift) > self.drift_threshold])
            exits = len([r for r in sync_results if r.action == "exit"])
            errors = len([r for r in sync_results if r.action == "error"])

            self.position_store.record_chain_sync(
                positions_synced=len(self._local_positions),
                drifts_found=drifts,
                exits_triggered=exits,
                errors=errors,
                elapsed_ms=elapsed_ms,
                metadata={
                    "sync_id": self._sync_count,
                    "total_results": len(sync_results)
                }
            )
        except Exception as e:
            logger.error(f"Error recording sync log: {e}")

    def _sync_result_to_dict(self, result: SyncResult) -> Dict[str, Any]:
        """转换同步结果为字典"""
        return {
            "position_id": result.position_id,
            "token_id": result.token_id,
            "local_size": result.local_size,
            "chain_size": result.chain_size,
            "drift": result.drift,
            "action": result.action,
            "details": result.details,
            "timestamp": result.timestamp.isoformat() if result.timestamp else None
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "sync_count": self._sync_count,
            "error_count": self._error_count,
            "last_sync_time": self._last_sync_time.isoformat() if self._last_sync_time else None,
            "is_running": self._running
        }


# 为了保持向后兼容性，保留原有的类名和接口
class PeriodicSync(ChainPositionSync):
    """
    向后兼容的 PeriodicSync 类

    继承自 ChainPositionSync，提供相同的接口
    """

    def __init__(
        self,
        config: Dict[str, Any],
        on_sync: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_exit_signal: Optional[Callable[[Any], None]] = None
    ):
        """
        初始化（向后兼容）

        Args:
            config: 配置参数
            on_sync: 同步完成回调
            on_exit_signal: 退出信号回调
        """
        # 创建临时的 position store
        db_path = config.get("db_path", "data/position_sync.db")
        position_store = PositionStore(db_path)

        super().__init__(
            position_store=position_store,
            config=config,
            on_position_event=None,
            on_sync_complete=on_sync,
            on_error=None
        )

        self._on_exit_signal = on_exit_signal
        self._config = config

    async def _emit_sync_events(self, sync_results: List[SyncResult]):
        """重写事件触发，支持退出信号回调"""
        await super()._emit_sync_events(sync_results)

        # 触发退出信号
        if self._on_exit_signal:
            for result in sync_results:
                if result.action == "exit":
                    try:
                        exit_signal = self._create_exit_signal(result)
                        if asyncio.iscoroutinefunction(self._on_exit_signal):
                            await self._on_exit_signal(exit_signal)
                        else:
                            self._on_exit_signal(exit_signal)
                    except Exception as e:
                        logger.error(f"Error in exit signal callback: {e}")

    def _create_exit_signal(self, result: SyncResult) -> Any:
        """创建退出信号（向后兼容）"""
        from .position_monitor import ExitSignal

        return ExitSignal(
            position_id=result.position_id,
            action="exit",
            reason="chain_sync_forced_exit",
            exit_ratio=1.0,
            metadata={
                "sync_result": result.action,
                "chain_size": result.chain_size,
                "local_size": result.local_size,
                "drift": result.drift,
                "details": result.details,
            }
        )

    def set_positions_reference(self, positions: Dict[str, Any]):
        """设置持仓引用（向后兼容）"""
        pass

    async def check_position(self, position: Any, sync_data: Dict[str, Any]) -> Optional[Any]:
        """检查单个持仓（向后兼容）"""
        return None


__all__ = [
    "PositionStore",
    "ChainPositionSync",
    "PeriodicSync",
    "PositionRecord",
    "ChainPosition",
    "SyncResult",
    "PositionEvent",
    "PositionEventType",
]