from __future__ import annotations

import asyncio
import json
import os
from typing import TYPE_CHECKING

import psutil
import websockets

from data.orchestrator import MessageType
from utils import logger

if TYPE_CHECKING:
    from websockets.asyncio.server import ServerConnection

    from core.bot import Bot

# Does not inherit from baseService
class OrchestratorService:
    def __init__(
        self,
        bot: Bot,
        ws_url: str,
        cluster_id: str
    ) -> None:
        self._bot = bot
        self._ws_url = ws_url
        self._ws: ServerConnection | None = None
        self._task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._connected: bool = False
        self._cluster_id = cluster_id
        self._ready_shards: set[int] = set()
        self._identified = False
    
    async def connect(self) -> None:
        self._task = asyncio.create_task(
            self._connection_loop(),
            name='orchestrator-ws'
        )
    
    async def close(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        if self._ws:
            await self._ws.close()
        
    async def _connection_loop(self) -> None:
        backoff = 1
        while True:
            try:
                async with websockets.connect(self._ws_url) as ws:
                    self._ws = ws
                    self._connected = True
                    backoff = 1 # reset on successful connect
                    # reset identification and readiness on reconnect
                    self._identified = False
                    self._ready_shards.clear()

                    # The orchestrator expects IDENTIFY immediately after the
                    # websocket is established. Shard-ready events are sent
                    # afterwards as shards come online.
                    await self._identify()

                    await self._listen(ws)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._connected = False
                logger.warning(f'Orchestrator WS disconnected: {e} - attempting reconnect in {backoff}s')
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
    
    async def _identify(self) -> None:
        if self._identified:
            return

        shard_ids = list(self._bot.shard_ids or [])

        await self._send({
            'type': MessageType.IDENTIFY.value,
            'cluster_id': self._cluster_id,
            'shard_ids': shard_ids
        })

        self._identified = True

        logger.info(
            f'Identified with orchestrator as '
            f'{self._cluster_id} (shards={shard_ids})'
        )

        # Start heartbeat only after successful identification
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(),
            name='orchestrator-heartbeat'
        )
    
    async def _listen(self, ws) -> None:
        async for raw in ws:
            try:
                message = json.loads(raw)
                message_type = MessageType(message.get('type'))
            except (json.JSONDecodeError, ValueError):
                logger.warning('Unknown message from orchestrator {raw[:100]}')
                continue

            await self._handle(message_type, message)

    async def mark_shard_ready(self, shard_id: int) -> None:
        self._ready_shards.add(shard_id)

        expected = set(self._bot.shard_ids or [])

        logger.debug(
            f'Shard ready for {self._cluster_id}: '
            f'{sorted(self._ready_shards)}/{sorted(expected)}'
        )

        if expected and expected.issubset(self._ready_shards):
            logger.info(
                f'All assigned shards ready for {self._cluster_id}'
            )

            await self._identify()
    
    async def _handle(self, message_type: MessageType, message: dict) -> None:
        match message_type:
            case MessageType.HELLO:
                logger.info('Orchestrator acknowledged connection')
            
            case MessageType.RESHARD:
                await self._handle_reshard(message)
            
            case MessageType.DRAIN:
                await self._handle_drain()
            
            case MessageType.RESTART:
                await self._handle_restart()
            
            case MessageType.CACHE_INVALIDATE:
                await self._handle_cache_invalidate(message)
            
            case _:
                logger.debug(f'Unhandled message received: {message_type}')
    
    async def _handle_reshard(self, message: dict) -> None:
        logger.warning(f'Reshard requested: {message}')
        await self.send_status('draining')
        await self._bot.close()
    
    async def _handle_drain(self) -> None:
        logger.warning('Drain requested by orchestrator')
        await self.send_status('draining')
        # Give the bot a chance to publish per-shard handoff events so
        # replacements holding gates closed can open them promptly.
        try:
            from core.lifespan import release_shards_on_shutdown

            await release_shards_on_shutdown(self._bot)
        except Exception:
            # If the helper is not present or fails, proceed to close anyway.
            pass

        await self._bot.close()
    
    async def _handle_restart(self) -> None:
        logger.warning("Restart requested by orchestrator")
        await self._bot.close()
    
    async def _handle_cache_invalidate(self, message: dict) -> None:
        payload = message.get("payload", {})
        cache_type = payload.get("type")
        logger.debug(f"Cache invalidation: {cache_type}")

    
    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(10)
                await self._send({
                    'type': MessageType.HEALTH.value,
                    'cluster_id': self._cluster_id,
                    'sent_at': asyncio.get_event_loop().time()
                })
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f'Heartbeat failed: {e}')
                break
    
    async def _send(self, payload: dict) -> None:
        if not self._ws:
            return
        try:
            await self._ws.send(json.dumps(payload))
        except Exception as e:
            logger.warning(f'Failed to send to orchestrator: {e}')
        
    async def send_status(self, status: str) -> None:
        await self._send({
            'type': MessageType.STATUS.value,
            'cluster_id': self._cluster_id,
            'status': status,
        })
    
    async def send_shard_ready(self, shard_id: int) -> None:
        await self._send({
            'type': MessageType.SHARD_READY.value,
            'cluster_id': self._cluster_id,
            'shard_id': shard_id
        })

    async def send_shard_closed(
        self,
        shard_id: int,
        code: int,
        session_id: str | None = None,
        resume_url: str | None = None,
        sequence: int | None = None,
    ) -> None:
        await self._send({
            'type': MessageType.SHARD_CLOSED.value,
            'cluster_id': self._cluster_id,
            'shard_id': shard_id,
            'code': code,
            'session_id': session_id,
            'resume_url': resume_url,
            'sequence': sequence
        })
    
    async def send_metrics(self) -> None:
        process = psutil.Process(os.getpid())

        await self._send({
            'type': MessageType.METRICS.value,
            'cluster_id': self._cluster_id,
            'guild_count': len(self._bot.guilds),
            'user_count': sum(guild.member_count or 0 for guild in self._bot.guilds),
            'latency_ms': self._bot.latency * 1000,
            'memory_mb': process.memory_info().rss / 1024 / 1024,
        })

    async def send_error(self, error: str) -> None:
        await self._send({
            'type': MessageType.ERROR.value,
            'cluster_id': self._cluster_id,
            'error': error,
        })
        