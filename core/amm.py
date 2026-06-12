from decimal import Decimal, getcontext, DivisionByZero
import os
import json
from utils.file_utils import ensure_dir

getcontext().prec = 32

POOL_STATE_FILE = "data/pool_state.json"


class AMM:
    def __init__(self, x, y, fee=0.003):
        self.x = Decimal(str(x))
        self.y = Decimal(str(y))
        self.fee = Decimal(str(fee))

        self.init_x = self.x
        self.init_y = self.y

        self.total_lp = Decimal("0")

        self.price_history = []
        self.slippage_history = []
        self.k_history = []

        self.fee_x_collected = Decimal("0")
        self.fee_y_collected = Decimal("0")

    def price(self):
        """返回 1 X = ? Y"""
        return float(self.y / self.x) if self.x != 0 else 0

    def price_x_per_y(self):
        """返回 1 Y = ? X"""
        return float(self.x / self.y) if self.y != 0 else 0

    def k(self):
        """返回当前恒定乘积 K = x * y"""
        return self.x * self.y

    def record_state(self, slippage=0.0):
        """记录池子状态：价格、滑点、K 值"""
        self.price_history.append(self.price())
        self.slippage_history.append(float(slippage))
        self.k_history.append(float(self.k()))

    def update_last_state(self, slippage=0.0):
        """
        更新最后一次状态记录。
        撤回交易时，swap 后又额外扣除撤回手续费，
        池子状态会再次变化，所以需要刷新最后一次记录。
        """
        if self.price_history:
            self.price_history[-1] = self.price()
        else:
            self.price_history.append(self.price())

        if self.slippage_history:
            self.slippage_history[-1] = float(slippage)
        else:
            self.slippage_history.append(float(slippage))

        if self.k_history:
            self.k_history[-1] = float(self.k())
        else:
            self.k_history.append(float(self.k()))

    # ---------- 交易预估 ----------
    def quote_x_for_y(self, dx):
        """
        预估用 dx 个 X 可以换出多少 Y。
        不修改池子状态。
        返回：(dy, slippage)
        """
        dx = Decimal(str(dx))

        if dx <= 0:
            return 0.0, 0.0

        fee_amount = dx * self.fee
        dx_eff = dx - fee_amount

        new_x = self.x + dx_eff
        if new_x == 0:
            return 0.0, 0.0

        new_y = (self.x * self.y) / new_x
        dy = self.y - new_y

        if dy <= 0:
            return 0.0, 0.0

        actual_price = float(dy / dx)
        price_before = self.price()
        slippage = abs(actual_price - price_before) / price_before if price_before != 0 else 0

        return float(dy), slippage

    def quote_y_for_x(self, dy):
        """
        预估用 dy 个 Y 可以换出多少 X。
        不修改池子状态。
        返回：(dx, slippage)
        """
        dy = Decimal(str(dy))

        if dy <= 0:
            return 0.0, 0.0

        fee_amount = dy * self.fee
        dy_eff = dy - fee_amount

        new_y = self.y + dy_eff
        if new_y == 0:
            return 0.0, 0.0

        new_x = (self.x * self.y) / new_y
        dx = self.x - new_x

        if dx <= 0:
            return 0.0, 0.0

        actual_price = float(dx / dy)
        price_before = self.price_x_per_y()
        slippage = abs(actual_price - price_before) / price_before if price_before != 0 else 0

        return float(dx), slippage

    # ---------- 交易 ----------
    def swap_x_for_y(self, dx):
        dx = Decimal(str(dx))

        if dx <= 0:
            raise ValueError("交易金额必须为正数")

        fee_amount = dx * self.fee
        dx_eff = dx - fee_amount

        new_x = self.x + dx_eff

        if new_x == 0:
            raise DivisionByZero("池中 X 不能为零")

        new_y = (self.x * self.y) / new_x
        dy = self.y - new_y

        if dy <= 0:
            raise ValueError("计算得到的 Y 非正")

        actual_price = float(dy / dx)
        price_before = self.price()
        slippage = abs(actual_price - price_before) / price_before if price_before != 0 else 0

        self.fee_x_collected += fee_amount

        self.x += dx
        self.y -= dy

        self.record_state(slippage)

        return float(dy), slippage

    def swap_y_for_x(self, dy):
        dy = Decimal(str(dy))

        if dy <= 0:
            raise ValueError("交易金额必须为正数")

        fee_amount = dy * self.fee
        dy_eff = dy - fee_amount

        new_y = self.y + dy_eff

        if new_y == 0:
            raise DivisionByZero("池中 Y 不能为零")

        new_x = (self.x * self.y) / new_y
        dx = self.x - new_x

        if dx <= 0:
            raise ValueError("计算得到的 X 非正")

        actual_price = float(dx / dy)
        price_before = self.price_x_per_y()
        slippage = abs(actual_price - price_before) / price_before if price_before != 0 else 0

        self.fee_y_collected += fee_amount

        self.y += dy
        self.x -= dx

        self.record_state(slippage)

        return float(dx), slippage

    # ---------- 流动性操作 ----------
    def add_liquidity(self, dx, dy):
        """注入流动性，返回铸造的 LP 份额"""
        dx = Decimal(str(dx))
        dy = Decimal(str(dy))

        if dx <= 0 or dy <= 0:
            raise ValueError("注入金额必须为正数")

        if self.x <= 0 or self.y <= 0:
            raise ValueError("池子储备异常")

        expected_dy = dx * self.y / self.x

        if expected_dy == 0:
            raise ValueError("池子比例异常")

        if abs(dy - expected_dy) / expected_dy > Decimal("0.001"):
            raise ValueError("两种代币比例与池子不一致")

        if self.total_lp == 0:
            lp_minted = dx
        else:
            lp_minted = (dx / self.x) * self.total_lp

        self.x += dx
        self.y += dy
        self.total_lp += lp_minted

        self.record_state(0.0)

        return float(lp_minted)

    def remove_liquidity(self, share):
        """销毁 share 份 LP，返回 (dx, dy)"""
        share = Decimal(str(share))

        if share <= 0:
            raise ValueError("份额必须为正数")

        if self.total_lp <= 0:
            raise ValueError("当前没有可移除的流动性")

        if share > self.total_lp:
            raise ValueError("份额不足")

        fraction = share / self.total_lp

        dx = self.x * fraction
        dy = self.y * fraction

        self.x -= dx
        self.y -= dy
        self.total_lp -= share

        self.record_state(0.0)

        return float(dx), float(dy)

    # ---------- LP 估值 ----------
    def lp_share_value(self, share):
        """
        查询某个 LP 份额当前可以取回多少 X 和 Y。
        不修改池子状态。
        """
        share = Decimal(str(share))

        if share <= 0:
            return 0.0, 0.0

        if self.total_lp <= 0:
            return 0.0, 0.0

        if share > self.total_lp:
            return 0.0, 0.0

        fraction = share / self.total_lp

        dx = self.x * fraction
        dy = self.y * fraction

        return float(dx), float(dy)

    # ---------- 风险分析 ----------
    @staticmethod
    def impermanent_loss(r):
        """
        计算无常损失。
        r = P_new / P_old
        返回百分比，例如 -5.72 表示损失 5.72%
        """
        r = Decimal(str(r))

        if r <= 0:
            raise ValueError("价格比率必须为正数")

        sqrt_r = r.sqrt()
        il = (Decimal("2") * sqrt_r / (Decimal("1") + r) - Decimal("1")) * Decimal("100")

        return float(il)

    # ---------- 持久化 ----------
    def to_dict(self):
        return {
            "x": str(self.x),
            "y": str(self.y),
            "fee": str(self.fee),
            "total_lp": str(self.total_lp),
            "price_history": self.price_history,
            "slippage_history": self.slippage_history,
            "k_history": self.k_history,
            "fee_x_collected": str(self.fee_x_collected),
            "fee_y_collected": str(self.fee_y_collected)
        }

    @classmethod
    def from_dict(cls, data):
        amm = cls(
            data.get("x", "1000000"),
            data.get("y", "1000000"),
            data.get("fee", "0.003")
        )

        amm.total_lp = Decimal(data.get("total_lp", "0"))
        amm.price_history = data.get("price_history", [])
        amm.slippage_history = data.get("slippage_history", [])
        amm.k_history = data.get("k_history", [])

        amm.fee_x_collected = Decimal(data.get("fee_x_collected", "0"))
        amm.fee_y_collected = Decimal(data.get("fee_y_collected", "0"))

        return amm

    def save_state(self):
        ensure_dir(POOL_STATE_FILE)

        with open(POOL_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load_state(cls):
        if not os.path.exists(POOL_STATE_FILE):
            return None

        try:
            with open(POOL_STATE_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()

                if not content:
                    return None

                data = json.loads(content)

            return cls.from_dict(data)

        except Exception:
            try:
                os.remove(POOL_STATE_FILE)
            except Exception:
                pass

            return None