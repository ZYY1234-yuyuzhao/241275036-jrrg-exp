from flask import Flask, jsonify, request, session, send_from_directory
from services.user_service import register, login, init_default_user
from services.trade_service import TradeService
from services.history_service import load_history
import os

app = Flask(__name__)
app.secret_key = "amm-local-exchange-secret-key"

# 确保 static 文件夹存在，用于放 logo.jpg
os.makedirs("static", exist_ok=True)

# 初始化默认用户
init_default_user()

# 初始化交易服务
trade_service = TradeService()


# ---------- 页面 ----------
@app.route("/")
def index():
    return send_from_directory(".", "index.html")


# ---------- Logo 接口 ----------
@app.route("/api/logo", methods=["GET"])
def api_logo():
    """
    Logo 展示接口。

    使用方法：
    1. 在项目根目录创建 static 文件夹；
    2. 把 logo 图片放进去；
    3. 图片命名为 logo.jpg。

    路径应该是：
    static/logo.jpg
    """
    logo_path = os.path.join("static", "logo.jpg")

    if os.path.exists(logo_path):
        return jsonify({
            "success": True,
            "logo_url": "/static/logo.jpg",
            "logo_text": ""
        })

    return jsonify({
        "success": True,
        "logo_url": "",
        "logo_text": "AMM"
    })


# ---------- 用户接口 ----------
@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json() or {}

    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({
            "success": False,
            "message": "用户名和密码不能为空"
        })

    ok = register(username, password)

    if ok:
        return jsonify({
            "success": True,
            "message": "注册成功"
        })

    return jsonify({
        "success": False,
        "message": "用户名已存在"
    })


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}

    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if login(username, password):
        session["username"] = username
        return jsonify({
            "success": True,
            "message": "登录成功"
        })

    return jsonify({
        "success": False,
        "message": "用户名或密码错误"
    })


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.pop("username", None)

    return jsonify({
        "success": True,
        "message": "已退出登录"
    })


@app.route("/api/user", methods=["GET"])
def api_user():
    username = session.get("username")

    if not username:
        return jsonify({
            "success": False,
            "message": "未登录"
        })

    user = trade_service.get_user(username)

    if not user:
        return jsonify({
            "success": False,
            "message": "用户不存在"
        })

    return jsonify({
        "success": True,
        "user": {
            "username": username,
            "x": float(user["x"]),
            "y": float(user["y"]),
            "lp": float(user["lp"])
        }
    })


# ---------- 池子接口 ----------
@app.route("/api/pool", methods=["GET"])
def api_pool():
    return jsonify(trade_service.get_pool_info())


@app.route("/api/price_history", methods=["GET"])
def api_price_history():
    return jsonify(trade_service.get_price_history())


@app.route("/api/slippage_history", methods=["GET"])
def api_slippage_history():
    return jsonify(trade_service.get_slippage_history())


@app.route("/api/k_history", methods=["GET"])
def api_k_history():
    return jsonify(trade_service.get_k_history())


@app.route("/api/fee_summary", methods=["GET"])
def api_fee_summary():
    return jsonify(trade_service.get_fee_summary())


@app.route("/api/lp_position", methods=["GET"])
def api_lp_position():
    username = session.get("username")

    if not username:
        return jsonify({
            "success": False,
            "message": "未登录"
        })

    data = trade_service.get_lp_position(username)

    if data is None:
        return jsonify({
            "success": False,
            "message": "用户不存在"
        })

    return jsonify({
        "success": True,
        "data": data
    })


# ---------- 历史记录 ----------
@app.route("/api/history", methods=["GET"])
def api_history():
    username = session.get("username")

    if not username:
        return jsonify([])

    history = load_history()

    user_history = []
    for h in history:
        if h.get("user") == username:
            user_history.append(h)

    return jsonify(user_history)


# ---------- 交易接口 ----------
@app.route("/api/trade/buy", methods=["POST"])
def api_buy():
    username = session.get("username")

    if not username:
        return jsonify({
            "success": False,
            "message": "未登录"
        })

    data = request.get_json() or {}
    amount = data.get("amount", 0)

    ok, result = trade_service.buy(username, amount)

    if ok:
        return jsonify({
            "success": True,
            "result": result
        })

    return jsonify({
        "success": False,
        "message": result
    })


@app.route("/api/trade/sell", methods=["POST"])
def api_sell():
    username = session.get("username")

    if not username:
        return jsonify({
            "success": False,
            "message": "未登录"
        })

    data = request.get_json() or {}
    amount = data.get("amount", 0)

    ok, result = trade_service.sell(username, amount)

    if ok:
        return jsonify({
            "success": True,
            "result": result
        })

    return jsonify({
        "success": False,
        "message": result
    })


@app.route("/api/trade/cancel", methods=["POST"])
def api_cancel_trade():
    username = session.get("username")

    if not username:
        return jsonify({
            "success": False,
            "message": "未登录"
        })

    data = request.get_json() or {}
    record_id = data.get("record_id", None)

    ok, message = trade_service.cancel_trade(username, record_id)

    return jsonify({
        "success": ok,
        "message": message
    })


# ---------- 流动性接口 ----------
@app.route("/api/liquidity/add", methods=["POST"])
def api_add_liquidity():
    username = session.get("username")

    if not username:
        return jsonify({
            "success": False,
            "message": "未登录"
        })

    data = request.get_json() or {}
    dx = data.get("dx", 0)

    ok, message = trade_service.add_liquidity(username, dx)

    return jsonify({
        "success": ok,
        "message": message
    })


@app.route("/api/liquidity/remove", methods=["POST"])
def api_remove_liquidity():
    username = session.get("username")

    if not username:
        return jsonify({
            "success": False,
            "message": "未登录"
        })

    data = request.get_json() or {}
    share = data.get("share", 0)

    ok, message = trade_service.remove_liquidity(username, share)

    return jsonify({
        "success": ok,
        "message": message
    })


# ---------- 预览接口 ----------
@app.route("/api/preview/buy", methods=["GET"])
def api_preview_buy():
    amount = request.args.get("amount", 0)

    result, slippage = trade_service.preview_buy(amount)

    return jsonify({
        "success": True,
        "result": result,
        "slippage": slippage
    })


@app.route("/api/preview/sell", methods=["GET"])
def api_preview_sell():
    amount = request.args.get("amount", 0)

    result, slippage = trade_service.preview_sell(amount)

    return jsonify({
        "success": True,
        "result": result,
        "slippage": slippage
    })


@app.route("/api/preview/liquidity/add", methods=["GET"])
def api_preview_add_liquidity():
    dx = request.args.get("dx", 0)

    dy, lp_minted = trade_service.preview_add_liquidity(dx)

    return jsonify({
        "success": True,
        "dy": dy,
        "lp_minted": lp_minted
    })


@app.route("/api/preview/liquidity/remove", methods=["GET"])
def api_preview_remove_liquidity():
    share = request.args.get("share", 0)

    dx, dy = trade_service.preview_remove_liquidity(share)

    return jsonify({
        "success": True,
        "dx": dx,
        "dy": dy
    })


# ---------- 无常损失 ----------
@app.route("/api/impermanent_loss", methods=["GET"])
def api_impermanent_loss_curve():
    r_values = []
    il_values = []

    value = 0.1

    while value <= 10:
        r = round(value, 2)
        il = trade_service.calc_impermanent_loss(r)

        r_values.append(r)
        il_values.append(il)

        value += 0.1

    return jsonify({
        "r": r_values,
        "il": il_values
    })


@app.route("/api/impermanent_loss/calc", methods=["GET"])
def api_impermanent_loss_calc():
    r = request.args.get("r", 1)

    il = trade_service.calc_impermanent_loss(r)

    return jsonify({
        "success": True,
        "r": float(r),
        "impermanent_loss": il
    })


# ---------- 滑点曲线 ----------
@app.route("/api/slippage_curve", methods=["GET"])
def api_slippage_curve():
    pool = trade_service.get_pool_info()

    current_x = pool["x"]
    price = pool["price_yx"]

    dx_list = []
    dy_actual_list = []
    dy_theory_list = []

    max_dx = current_x * 0.1

    for i in range(1, 21):
        dx = max_dx * i / 20

        dy_actual, _ = trade_service.preview_buy(dx)
        dy_theory = dx * price

        dx_list.append(dx)
        dy_actual_list.append(dy_actual)
        dy_theory_list.append(dy_theory)

    return jsonify({
        "dx": dx_list,
        "dy_actual": dy_actual_list,
        "dy_theory": dy_theory_list
    })


# ---------- 启动 ----------
if __name__ == "__main__":
    app.run(debug=True)