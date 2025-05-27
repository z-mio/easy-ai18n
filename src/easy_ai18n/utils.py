import hashlib
from pathlib import Path


def gen_id(text) -> str:
    """
    生成唯一ID
    :param text: 输入字符串
    :return: 32位的十六进制字符串
    """
    text = str(text).encode("utf-8")
    return hashlib.md5(text).hexdigest()[:12]


def singleton(cls):
    instances = {}

    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return get_instance


def to_list(obj):
    if isinstance(obj, list):
        return obj
    elif obj is None:
        return []
    else:
        return [obj]


def to_path(path):
    if isinstance(path, str):
        return Path(path)
    elif path is None:
        return None
    elif isinstance(path, Path):
        return path
    else:
        return path
