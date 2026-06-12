from utils.file_utils import read_json, write_json
from datetime import datetime
import uuid

FILE = "data/history.json"


def load_history():
    data = read_json(FILE)

    if data is None:
        return []

    return data


def save_history(data):
    write_json(FILE, data)


def add_record(user, type_, amount, result, price, **extra):
    """
    添加历史记录。

    基础字段：
    user   : 用户名
    type_  : 操作类型
    amount : 支付数量
    result : 获得数量 / 或流动性操作中的对应结果
    price  : 操作后价格

    extra  : 扩展字段，例如：
             slippage
             fee
             k_after
             lp_minted
             lp_removed
             cancel_of
    """
    data = load_history()

    record = {
        "id": str(uuid.uuid4()),
        "user": user,
        "type": type_,
        "amount": float(amount),
        "result": float(result),
        "price": float(price),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "canceled": False
    }

    for key, value in extra.items():
        try:
            record[key] = float(value)
        except Exception:
            record[key] = value

    data.append(record)
    write_json(FILE, data)

    return record["id"]


def find_record_by_id(record_id):
    """
    根据交易 id 查找记录。
    找不到返回 None。
    """
    data = load_history()

    for record in data:
        if record.get("id") == record_id:
            return record

    return None


def mark_record_canceled(record_id, cancel_info=None):
    """
    将某条历史记录标记为已撤回。
    """
    if not record_id:
        return False

    data = load_history()

    for record in data:
        if record.get("id") == record_id:
            record["canceled"] = True
            record["cancel_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if cancel_info:
                for key, value in cancel_info.items():
                    try:
                        record[key] = float(value)
                    except Exception:
                        record[key] = value

            write_json(FILE, data)
            return True

    return False