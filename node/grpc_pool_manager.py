# grpc_pool_manager.py
import asyncio
import grpc
from grpc.aio import insecure_channel
from contextlib import asynccontextmanager
from collections import defaultdict
import traceback
import logging

logger = logging.getLogger(__name__)


class GlobalGrpcPool:
    _instance = None  # Singleton instance

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(GlobalGrpcPool, cls).__new__(cls)
        return cls._instance

    def __init__(self, max_channels=50, buffer_size=5, channel_options=None):
        if hasattr(self, "_initialized") and self._initialized:
            return  # Prevent re-initialization
        self.max_channels = max_channels
        self.buffer_size = buffer_size
        self.available_queue = asyncio.Queue(maxsize=self.buffer_size)
        self.semaphore = asyncio.Semaphore(self.max_channels - self.buffer_size)
        self.channel_options = channel_options or [
            ("grpc.max_send_message_length", 100 * 1024 * 1024),  # 100 MB
            ("grpc.max_receive_message_length", 100 * 1024 * 1024),  # 100 MB
            ("grpc.keepalive_timeout_ms", 3600000),  # 1 hour
            ("grpc.keepalive_timeout_ms", 50 * 1000),  # 50 seconds
            ("grpc.http2.max_pings_without_data", 0),
            ("grpc.http2.min_time_between_pings_ms", 10 * 1000),  # 10 seconds
            ("grpc.max_connection_idle_ms", 60 * 60 * 1000),  # 1 hour
            ("grpc.max_connection_age_ms", 2 * 60 * 60 * 1000),  # 2 hours
        ]
        # Initialize statistics
        self.channel_stats = defaultdict(
            lambda: {"acquired": 0, "released": 0, "total_channels": 0}
        )
        self._initialized = True
        logger.info(
            f"GlobalGrpcPool initialized with max_channels={self.max_channels} and buffer_size={self.buffer_size}"
        )

    async def get_channel(self, target: str):
        logger.info(f"Attempting to acquire channel for {target}")
        await self.semaphore.acquire()
        channel = None
        try:
            if not self.available_queue.empty():
                channel = await self.available_queue.get()
                logger.info(f"Reusing channel from buffer for {target}.")
            else:
                channel = insecure_channel(target, options=self.channel_options)
                self.channel_stats[target]["total_channels"] += 1
                logger.info(
                    f"New channel created for {target}. Total channels: {self.channel_stats[target]['total_channels']}"
                )
            self.channel_stats[target]["acquired"] += 1
            return channel
        except Exception as e:
            logger.error(f"Error acquiring channel for {target}: {e}")
            self.semaphore.release()
            raise

    async def release_channel(self, target: str, channel):
        logger.info(
            f"Attempting to release channel for {target} (Channel ID: {id(channel)})"
        )
        if channel is None:
            logger.warning(
                f"Attempted to release a None channel for {target}. Ignoring."
            )
            self.semaphore.release()
            return  # Don't try to release a None channel

        try:
            connectivity = channel.get_state(True)
            if connectivity == grpc.ChannelConnectivity.SHUTDOWN:
                logger.warning(f"Attempted to release a closed channel for {target}.")
                self.channel_stats[target]["total_channels"] -= 1
                self.channel_stats[target]["released"] += 1
                self.semaphore.release()
                return

            try:
                self.available_queue.put_nowait(channel)
                self.channel_stats[target]["released"] += 1
                logger.info(f"Channel released back to buffer for {target}.")
            except asyncio.QueueFull:
                logger.warning(f"Buffer full for {target}. Closing channel.")
                await channel.close()
                self.channel_stats[target]["total_channels"] -= 1
                self.channel_stats[target]["released"] += 1
        except Exception as e:
            logger.error(f"Error releasing channel for {target}: {e}")
            logger.error(traceback.format_exc())
        finally:
            self.semaphore.release()
            logger.debug(f"Semaphore released for {target}.")

    async def close_all(self):
        logger.info("Closing all channels in the pool.")
        # Close channels in the buffer
        while not self.available_queue.empty():
            channel = await self.available_queue.get()
            await channel.close()
            # Update statistics
            for target, stats in self.channel_stats.items():
                if stats["total_channels"] > 0:
                    stats["total_channels"] -= 1
                    stats["released"] += 1
                    break  # Assuming channel belongs to one target
        logger.info("All buffered channels have been closed.")

    def print_stats(self):
        for target, stats in self.channel_stats.items():
            logger.info(
                f"Stats for {target}: Acquired={stats['acquired']}, Released={stats['released']}, Total Channels={stats['total_channels']}"
            )

    @asynccontextmanager
    async def channel_context(self, target: str):
        channel = await self.get_channel(target)
        try:
            yield channel
        finally:
            await self.release_channel(target, channel)

    async def monitor_pool(self, interval: int = 60):
        """
        Periodically logs the pool statistics.
        """
        while True:
            await asyncio.sleep(interval)
            self.print_stats()


# Singleton accessor functions
_pool_instance = None


def get_grpc_pool_instance(
    max_channels=50, buffer_size=5, channel_options=None
) -> GlobalGrpcPool:
    global _pool_instance
    if _pool_instance is None:
        _pool_instance = GlobalGrpcPool(
            max_channels=max_channels,
            buffer_size=buffer_size,
            channel_options=channel_options,
        )
        logger.info("GlobalGrpcPool instance created.")
    return _pool_instance


async def close_grpc_pool():
    global _pool_instance
    if _pool_instance:
        await _pool_instance.close_all()
        _pool_instance = None
        logger.info("GlobalGrpcPool instance closed and cleared.")
