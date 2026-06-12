import os
from decimal import Decimal
from utils.file_utils import ensure_dir

FILE = "data/user.txt"

DEFAULT_USER = "admin"
DEFAULT_PASS = "123456"
DEFAULT_X = "1000000"
DEFAULT_Y = "1000000"
DEFAULT_LP = "0"


def load_users():
    users = {}

    if not os.path.exists(FILE):
        return users

    with open(FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            parts = line.split(",")

            if len(parts) == 4:
                u, p, x, y = parts
                lp = "0"

            elif len(parts) == 5:
                u, p, x, y, lp = parts

            else:
                continue

            try:
                users[u] = {
                    "password": p,
                    "x": Decimal(x),
                    "y": Decimal(y),
                    "lp": Decimal(lp)
                }
            except Exception:
                continue

    return users


def save_users(users):
    ensure_dir(FILE)

    with open(FILE, "w", encoding="utf-8") as f:
        for u, d in users.items():
            f.write(f"{u},{d['password']},{d['x']},{d['y']},{d['lp']}\n")


def register(username, password):
    users = load_users()

    if username in users:
        return False

    users[username] = {
        "password": password,
        "x": Decimal(DEFAULT_X),
        "y": Decimal(DEFAULT_Y),
        "lp": Decimal(DEFAULT_LP)
    }

    save_users(users)
    return True


def login(username, password):
    users = load_users()

    if username in users and users[username]["password"] == password:
        return True

    return False


def init_default_user():
    users = load_users()

    if DEFAULT_USER not in users:
        users[DEFAULT_USER] = {
            "password": DEFAULT_PASS,
            "x": Decimal(DEFAULT_X),
            "y": Decimal(DEFAULT_Y),
            "lp": Decimal(DEFAULT_LP)
        }

        save_users(users)