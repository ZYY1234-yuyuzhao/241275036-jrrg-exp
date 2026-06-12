from core.amm import AMM
from services.user_service import load_users, save_users
from services.history_service import add_record, load_history, find_record_by_id, mark_record_canceled
from decimal import Decimal
from datetime import datetime


class TradeService:
    CANCEL_LIMIT_SECONDS = 60
    CANCEL_EXTRA_FEE = Decimal("0.002")

    def __init__(self):
        saved = AMM.load_state()

        if saved:
            self.amm = saved
        else:
            self.amm = AMM(1000000, 1000000)

    def _load_users(self):
        return load_users()

    # ---------- 交易 ----------
    def buy(self, username, amount):
        """
        买入：用户支付 X，获得 Y。
        """
        try:
            amount = Decimal(str(amount))
        except Exception:
            return False, "请输入有效数字"

        if amount <= 0:
            return False, "交易金额必须为正数"

        users = self._load_users()
        user = users.get(username)

        if not user:
            return False, "用户不存在"

        if user["x"] < amount:
            return False, "X 余额不足"

        try:
            fee_amount = amount * self.amm.fee
            dy, slippage = self.amm.swap_x_for_y(amount)
        except Exception as e:
            return False, f"交易失败: {str(e)}"

        user["x"] -= amount
        user["y"] += Decimal(str(dy))

        save_users(users)

        add_record(
            username,
            "buy",
            amount,
            dy,
            self.amm.price(),
            slippage=slippage,
            fee=fee_amount,
            k_after=self.amm.k()
        )

        self.amm.save_state()

        return True, float(dy)

    def sell(self, username, amount):
        """
        卖出：用户支付 Y，获得 X。
        """
        try:
            amount = Decimal(str(amount))
        except Exception:
            return False, "请输入有效数字"

        if amount <= 0:
            return False, "交易金额必须为正数"

        users = self._load_users()
        user = users.get(username)

        if not user:
            return False, "用户不存在"

        if user["y"] < amount:
            return False, "Y 余额不足"

        try:
            fee_amount = amount * self.amm.fee
            dx, slippage = self.amm.swap_y_for_x(amount)
        except Exception as e:
            return False, f"交易失败: {str(e)}"

        user["y"] -= amount
        user["x"] += Decimal(str(dx))

        save_users(users)

        add_record(
            username,
            "sell",
            amount,
            dx,
            self.amm.price(),
            slippage=slippage,
            fee=fee_amount,
            k_after=self.amm.k()
        )

        self.amm.save_state()

        return True, float(dx)

    # ---------- 撤回交易 ----------
    def cancel_trade(self, username, record_id=None):
        """
        撤回交易。

        规则：
        1. 只能撤回 60 秒内的 buy / sell 交易；
        2. 已撤回交易不能重复撤回；
        3. 撤回不是恢复旧状态，而是按当前池子价格执行反向交易；
        4. 撤回时额外扣除 0.2% 的输出资产作为手续费；
        5. 额外手续费留在池子中，归 LP 受益。
        """
        users = self._load_users()
        user = users.get(username)

        if not user:
            return False, "用户不存在"

        record = None

        if record_id:
            record = find_record_by_id(record_id)

            if not record:
                return False, "未找到该交易记录"

            if record.get("user") != username:
                return False, "不能撤回其他用户的交易"

        else:
            history = load_history()

            for h in reversed(history):
                if (
                    h.get("id")
                    and h.get("user") == username
                    and h.get("type") in ["buy", "sell"]
                    and not h.get("canceled", False)
                ):
                    record = h
                    break

            if not record:
                return False, "没有可撤回的交易"

        if record.get("type") not in ["buy", "sell"]:
            return False, "只能撤回买入或卖出交易"

        if record.get("canceled", False):
            return False, "该交易已经撤回过，不能重复撤回"

        try:
            record_time = datetime.strptime(record["time"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            return False, "交易时间格式错误，无法撤回"

        now = datetime.now()
        diff_seconds = (now - record_time).total_seconds()

        if diff_seconds < 0:
            return False, "交易时间异常，无法撤回"

        if diff_seconds > self.CANCEL_LIMIT_SECONDS:
            return False, "超过 1 分钟，不能撤回该交易"

        trade_type = record.get("type")
        original_result = Decimal(str(record.get("result", 0)))

        if original_result <= 0:
            return False, "原交易结果异常，无法撤回"

        # 原交易 buy：支付 X，获得 Y
        # 撤回 buy：退回 Y，按当前池价换回 X，再扣 0.2% X
        if trade_type == "buy":
            y_to_return = original_result

            if user["y"] < y_to_return:
                return False, "Y 余额不足，无法撤回该买入交易"

            try:
                dx_back, slippage = self.amm.swap_y_for_x(y_to_return)
            except Exception as e:
                return False, f"撤回失败: {str(e)}"

            dx_back = Decimal(str(dx_back))
            extra_fee_x = dx_back * self.CANCEL_EXTRA_FEE
            actual_x_back = dx_back - extra_fee_x

            if actual_x_back <= 0:
                return False, "撤回后返还金额异常"

            self.amm.x += extra_fee_x
            self.amm.update_last_state(slippage)

            user["y"] -= y_to_return
            user["x"] += actual_x_back

            save_users(users)

            add_record(
                username,
                "cancel_buy",
                float(y_to_return),
                float(actual_x_back),
                self.amm.price(),
                cancel_of=record.get("id", ""),
                extra_cancel_fee=extra_fee_x,
                slippage=slippage,
                k_after=self.amm.k()
            )

            mark_record_canceled(
                record.get("id"),
                {
                    "cancel_result": actual_x_back,
                    "cancel_extra_fee": extra_fee_x
                }
            )

            self.amm.save_state()

            return True, (
                f"撤回成功：退回 {float(y_to_return):.4f} Y，"
                f"按当前池子价格获得 {float(dx_back):.4f} X，"
                f"扣除额外撤回手续费 {float(extra_fee_x):.4f} X，"
                f"实际返还 {float(actual_x_back):.4f} X"
            )

        # 原交易 sell：支付 Y，获得 X
        # 撤回 sell：退回 X，按当前池价换回 Y，再扣 0.2% Y
        if trade_type == "sell":
            x_to_return = original_result

            if user["x"] < x_to_return:
                return False, "X 余额不足，无法撤回该卖出交易"

            try:
                dy_back, slippage = self.amm.swap_x_for_y(x_to_return)
            except Exception as e:
                return False, f"撤回失败: {str(e)}"

            dy_back = Decimal(str(dy_back))
            extra_fee_y = dy_back * self.CANCEL_EXTRA_FEE
            actual_y_back = dy_back - extra_fee_y

            if actual_y_back <= 0:
                return False, "撤回后返还金额异常"

            self.amm.y += extra_fee_y
            self.amm.update_last_state(slippage)

            user["x"] -= x_to_return
            user["y"] += actual_y_back

            save_users(users)

            add_record(
                username,
                "cancel_sell",
                float(x_to_return),
                float(actual_y_back),
                self.amm.price(),
                cancel_of=record.get("id", ""),
                extra_cancel_fee=extra_fee_y,
                slippage=slippage,
                k_after=self.amm.k()
            )

            mark_record_canceled(
                record.get("id"),
                {
                    "cancel_result": actual_y_back,
                    "cancel_extra_fee": extra_fee_y
                }
            )

            self.amm.save_state()

            return True, (
                f"撤回成功：退回 {float(x_to_return):.4f} X，"
                f"按当前池子价格获得 {float(dy_back):.4f} Y，"
                f"扣除额外撤回手续费 {float(extra_fee_y):.4f} Y，"
                f"实际返还 {float(actual_y_back):.4f} Y"
            )

        return False, "未知交易类型，无法撤回"

    # ---------- 流动性 ----------
    def add_liquidity(self, username, dx):
        """
        用户提供 dx 数量的 X，系统根据当前池比例自动计算所需 Y，并铸造 LP 份额。
        """
        try:
            dx = Decimal(str(dx))
        except Exception:
            return False, "请输入有效数字"

        if dx <= 0:
            return False, "数量必须为正数"

        users = self._load_users()
        user = users.get(username)

        if not user:
            return False, "用户不存在"

        dy = dx * self.amm.y / self.amm.x

        if user["x"] < dx:
            return False, "X 余额不足"

        if user["y"] < dy:
            return False, "Y 余额不足"

        try:
            lp_minted = self.amm.add_liquidity(dx, dy)
        except Exception as e:
            return False, f"添加流动性失败: {str(e)}"

        user["x"] -= dx
        user["y"] -= dy
        user["lp"] += Decimal(str(lp_minted))

        save_users(users)

        add_record(
            username,
            "add_liquidity",
            float(dx),
            float(dy),
            self.amm.price(),
            lp_minted=lp_minted,
            k_after=self.amm.k()
        )

        self.amm.save_state()

        return True, f"成功注入 {float(dx):.4f} X 和 {float(dy):.4f} Y，获得 {lp_minted:.4f} LP"

    def remove_liquidity(self, username, share):
        """
        用户销毁指定 LP 份额，按比例取回 X 和 Y。
        """
        try:
            share = Decimal(str(share))
        except Exception:
            return False, "请输入有效数字"

        if share <= 0:
            return False, "份额必须为正数"

        users = self._load_users()
        user = users.get(username)

        if not user:
            return False, "用户不存在"

        if user["lp"] < share:
            return False, "LP 份额不足"

        try:
            dx, dy = self.amm.remove_liquidity(share)
        except Exception as e:
            return False, f"移除流动性失败: {str(e)}"

        user["lp"] -= share
        user["x"] += Decimal(str(dx))
        user["y"] += Decimal(str(dy))

        save_users(users)

        add_record(
            username,
            "remove_liquidity",
            float(dx),
            float(dy),
            self.amm.price(),
            lp_removed=share,
            k_after=self.amm.k()
        )

        self.amm.save_state()

        return True, f"成功取回 {dx:.4f} X 和 {dy:.4f} Y"

    # ---------- 预览 ----------
    def preview_buy(self, amount):
        try:
            return self.amm.quote_x_for_y(amount)
        except Exception:
            return 0, 0

    def preview_sell(self, amount):
        try:
            return self.amm.quote_y_for_x(amount)
        except Exception:
            return 0, 0

    def preview_add_liquidity(self, dx):
        try:
            dx = Decimal(str(dx))

            if dx <= 0:
                return 0, 0

            dy = dx * self.amm.y / self.amm.x

            if self.amm.total_lp == 0:
                lp_minted = dx
            else:
                lp_minted = (dx / self.amm.x) * self.amm.total_lp

            return float(dy), float(lp_minted)
        except Exception:
            return 0, 0

    def preview_remove_liquidity(self, share):
        try:
            return self.amm.lp_share_value(share)
        except Exception:
            return 0, 0

    # ---------- 池子状态与分析 ----------
    def get_pool_info(self):
        return {
            "x": float(self.amm.x),
            "y": float(self.amm.y),
            "price_yx": self.amm.price(),
            "price_xy": self.amm.price_x_per_y(),
            "fee": float(self.amm.fee),
            "total_lp": float(self.amm.total_lp),
            "k": float(self.amm.k()),
            "fee_x_collected": float(self.amm.fee_x_collected),
            "fee_y_collected": float(self.amm.fee_y_collected)
        }

    def get_price_history(self):
        return self.amm.price_history

    def get_slippage_history(self):
        return self.amm.slippage_history

    def get_k_history(self):
        return self.amm.k_history

    def get_fee_summary(self):
        return {
            "fee_x_collected": float(self.amm.fee_x_collected),
            "fee_y_collected": float(self.amm.fee_y_collected)
        }

    def get_lp_position(self, username):
        users = self._load_users()
        user = users.get(username)

        if not user:
            return None

        user_lp = user.get("lp", Decimal("0"))
        dx, dy = self.amm.lp_share_value(user_lp)

        return {
            "lp": float(user_lp),
            "claimable_x": dx,
            "claimable_y": dy
        }

    def calc_impermanent_loss(self, r):
        try:
            return self.amm.impermanent_loss(r)
        except Exception:
            return 0

    def get_user(self, username):
        users = self._load_users()
        return users.get(username)