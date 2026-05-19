import hashlib
from collections.abc import Callable
from pathlib import Path


def gen_id(text: object) -> str:
    """
    生成唯一ID
    :param text: 输入字符串
    :return: 32位的十六进制字符串
    """
    text = str(text).encode("utf-8")
    return hashlib.md5(text).hexdigest()[:12]


def singleton[T, **P](cls: Callable[P, T]) -> Callable[P, T]:
    instances: dict[Callable[P, T], T] = {}

    def get_instance(*args: P.args, **kwargs: P.kwargs) -> T:
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return get_instance


def to_list[T](obj: T | list[T] | None) -> list[T]:
    if isinstance(obj, list):
        return obj
    elif obj is None:
        return []
    else:
        return [obj]


def to_path(path: str | Path | None) -> Path | None:
    if isinstance(path, str):
        return Path(path)
    elif path is None:
        return None
    elif isinstance(path, Path):
        return path
    else:
        return Path(str(path))
