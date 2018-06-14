import json
from typing import Any, List, Optional, TypeVar

import redis as redislib

from . import configuration
from .container import Container
from .serialization import extra_serializer


def init() -> Optional[redislib.Redis]:
    if not configuration.get_bool('redis_enabled'):
        return None
    instance = redislib.Redis(
        host=configuration.get_str('redis_host'),
        port=configuration.get_int('redis_port'),
        db=configuration.get_int('redis_db'),
        )
    try:
        instance.ping()
    except redislib.exceptions.ConnectionError:
        return None
    return instance

REDIS = init()

def get_str(key: str, ex: Optional[int] = None) -> Optional[str]:
    try:
        if REDIS is not None:
            blob = REDIS.get(key)
            if blob is not None:
                if ex is not None:
                    REDIS.set(key, blob, ex=ex)
                return blob
    except redislib.exceptions.BusyLoadingError:
        pass
    except redislib.exceptions.ConnectionError:
        pass
    return None

def get_container(key: str) -> Optional[Container]:
    if REDIS is not None:
        blob = get_str(key)
        if blob is not None:
            val = json.loads(blob)
            if val is not None:
                return Container(val)
    return None

def get_list(key: str) -> Optional[List[str]]:
    if REDIS is not None:
        blob = get_str(key)
        if blob is not None:
            val = json.loads(blob)
            return val
    return None

T = TypeVar('T', dict, list, str, covariant=True)

def store(key: str, val: T, **kwargs: Any) -> T:
    if REDIS is not None:
        try:
            REDIS.set(key, json.dumps(val, default=extra_serializer), **kwargs)
        except redislib.exceptions.BusyLoadingError:
            pass
        except redislib.exceptions.ConnectionError:
            pass
    return val

def clear(*keys: str) -> None:
    if REDIS is not None:
        REDIS.delete(*keys)
