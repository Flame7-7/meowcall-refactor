from enum import Enum

class MessageType(Enum):
    # Control Plane - Orchestrator -> Bot
    RESHARD = 'RESHARD'
    DRAIN = 'DRAIN'
    RESTART = 'RESTART'
    CONFIG_UPDATE = 'CONFIG_UPDATE'
    CACHE_INVALIDATE = 'CACHE_INVALIDATE'

    # Control Plane - Bot -> Orchestrator
    STATUS = 'STATUS'
    HEALTH = 'HEALTH'
    SHARD_READY = 'SHARD_READY'
    SHARD_CLOSED = 'SHARD_CLOSED'
    METRICS = 'METRICS'
    ERROR = 'ERROR'

    # Handshake
    IDENTIFY = 'IDENTIFY'
    HELLO = 'HELLO'