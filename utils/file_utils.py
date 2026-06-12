import os
import json


def ensure_dir(path):
    """
    确保文件所在目录存在。
    例如 data/user.txt，会自动创建 data 文件夹。
    """
    directory = os.path.dirname(path)

    if directory and not os.path.exists(directory):
        os.makedirs(directory)


def read_json(path):
    """
    读取 JSON 文件。
    如果文件不存在、为空或损坏，返回空列表。
    """
    if not os.path.exists(path):
        ensure_dir(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()

            if not content:
                return []

            return json.loads(content)
    except Exception:
        return []


def write_json(path, data):
    """
    写入 JSON 文件。
    """
    ensure_dir(path)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)