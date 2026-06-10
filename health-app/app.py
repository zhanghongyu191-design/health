# app.py —— 程序主体：网址(路由) + 登录逻辑都在这里
import os
from datetime import datetime, date, time, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)

from models import db, User, WeightLog, Meal, Exercise


def create_app():
    app = Flask(__name__)

    # SECRET_KEY 用来给登录会话签名；上线时建议用环境变量覆盖
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-please-change-me")

    # 数据库地址：上线时 Render/Neon 会给一个 DATABASE_URL；本地没有就用 SQLite 文件
    db_url = os.environ.get("DATABASE_URL", "sqlite:///local.db")
    # 有些平台给的是 postgres:// 开头，SQLAlchemy 需要 postgresql://
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = "login"
    login_manager.login_message = "请先登录"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # 第一次运行时自动建表
    with app.app_context():
        db.create_all()

    # ---------- 小工具：把表单里的日期/时间文字转成 Python 对象 ----------
    def parse_datetime(text):
        """处理 <input type=datetime-local> 的值，例如 2026-06-09T08:30"""
        if not text:
            return datetime.now()
        try:
            return datetime.strptime(text, "%Y-%m-%dT%H:%M")
        except ValueError:
            return datetime.now()

    def parse_date(text):
        if not text:
            return date.today()
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return date.today()

    # ========================= 注册 / 登录 / 登出 =========================
    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            if not username or not password:
                flash("用户名和密码都要填", "error")
            elif User.query.filter_by(username=username).first():
                flash("这个用户名已经有人用了", "error")
            else:
                user = User(username=username)
                user.set_password(password)
                db.session.add(user)
                db.session.commit()
                login_user(user)
                return redirect(url_for("dashboard"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                login_user(user)
                return redirect(url_for("dashboard"))
            flash("用户名或密码不对", "error")
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    # ============================== 首页小结 ==============================
    def build_weight_chart(logs):
        """用纯 SVG 画体重折线图（不依赖任何外部库，离线也能显示）。
        logs 需按时间从早到晚排好。少于 2 个点就不画。"""
        pts = [(l.recorded_at, l.weight_kg) for l in logs]
        if len(pts) < 2:
            return None
        W, H = 320.0, 130.0
        padx, top, bottom = 12.0, 18.0, 30.0
        ws = [w for _, w in pts]
        wmin, wmax = min(ws), max(ws)
        span = (wmax - wmin) or 1.0
        n = len(pts)
        fx = lambda i: padx + (W - 2 * padx) * (i / (n - 1))
        fy = lambda w: top + (H - top - bottom) * (1 - (w - wmin) / span)
        coords = [(fx(i), fy(w)) for i, (_, w) in enumerate(pts)]
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
        dots = "".join(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="var(--primary)"/>'
            for x, y in coords
        )
        return (
            f'<svg viewBox="0 0 {W:.0f} {H:.0f}" width="100%" '
            f'preserveAspectRatio="xMidYMid meet" style="display:block">'
            f'<polyline points="{poly}" fill="none" stroke="var(--primary)" '
            f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
            f'{dots}'
            f'<text x="{padx}" y="11" font-size="9" fill="#7d877f">{wmax:g} kg</text>'
            f'<text x="{padx}" y="{H-16:.0f}" font-size="9" fill="#7d877f">{wmin:g} kg</text>'
            f'<text x="{padx}" y="{H-3:.0f}" font-size="9" fill="#7d877f">'
            f'{pts[0][0].strftime("%m/%d")}</text>'
            f'<text x="{W-padx:.0f}" y="{H-3:.0f}" font-size="9" fill="#7d877f" '
            f'text-anchor="end">{pts[-1][0].strftime("%m/%d")}</text>'
            f'</svg>'
        )

    @app.route("/")
    @login_required
    def dashboard():
        uid = current_user.id
        today = date.today()
        # 选中的日期：网址带 ?date=YYYY-MM-DD 就看那天，否则看今天
        sel = parse_date(request.args.get("date")) if request.args.get("date") else today

        # 选中日的摄入/消耗
        sel_meals = Meal.query.filter_by(user_id=uid, eaten_on=sel).all()
        sel_ex = Exercise.query.filter_by(user_id=uid, done_on=sel).all()
        calories_in = sum(m.calories for m in sel_meals)
        calories_out = sum(e.calories_burned for e in sel_ex)

        # “截至选中日”的最新体重（那天没称就显示之前最近一次）
        day_end = datetime.combine(sel, time.max)
        latest_weight = (
            WeightLog.query.filter_by(user_id=uid)
            .filter(WeightLog.recorded_at <= day_end)
            .order_by(WeightLog.recorded_at.desc())
            .first()
        )

        # 体重趋势图（全部记录，从早到晚）
        all_weights = (
            WeightLog.query.filter_by(user_id=uid)
            .order_by(WeightLog.recorded_at.asc())
            .all()
        )
        chart_svg = build_weight_chart(all_weights)
        weight_change = None
        if len(all_weights) >= 2:
            weight_change = round(all_weights[-1].weight_kg - all_weights[0].weight_kg, 1)

        # 最近 7 天（从选中日往前数）的每日摘要
        start = sel - timedelta(days=6)
        rng_meals = (
            Meal.query.filter_by(user_id=uid)
            .filter(Meal.eaten_on >= start, Meal.eaten_on <= sel).all()
        )
        rng_ex = (
            Exercise.query.filter_by(user_id=uid)
            .filter(Exercise.done_on >= start, Exercise.done_on <= sel).all()
        )
        recent = []
        for i in range(0, 7):  # 选中日在最上面
            d = sel - timedelta(days=i)
            cin = sum(m.calories for m in rng_meals if m.eaten_on == d)
            cout = sum(e.calories_burned for e in rng_ex if e.done_on == d)
            recent.append({"date": d, "cin": cin, "cout": cout, "net": cin - cout})

        return render_template(
            "dashboard.html",
            sel=sel,
            is_today=(sel == today),
            latest_weight=latest_weight,
            calories_in=calories_in,
            calories_out=calories_out,
            net=calories_in - calories_out,
            meal_count=len(sel_meals),
            ex_count=len(sel_ex),
            chart_svg=chart_svg,
            weight_change=weight_change,
            recent=recent,
        )

    # ============================== 体重 ==============================
    @app.route("/weight", methods=["GET", "POST"])
    @login_required
    def weight():
        if request.method == "POST":
            try:
                kg = float(request.form.get("weight_kg", ""))
            except ValueError:
                flash("体重要填数字", "error")
                return redirect(url_for("weight"))
            log = WeightLog(
                user_id=current_user.id,
                weight_kg=kg,
                recorded_at=parse_datetime(request.form.get("recorded_at")),
                note=request.form.get("note", "").strip(),
            )
            db.session.add(log)
            db.session.commit()
            flash("体重已记录", "ok")
            return redirect(url_for("weight"))

        logs = (
            WeightLog.query.filter_by(user_id=current_user.id)
            .order_by(WeightLog.recorded_at.desc())
            .all()
        )
        return render_template("weight.html", logs=logs, now=datetime.now())

    @app.route("/weight/<int:log_id>/edit", methods=["GET", "POST"])
    @login_required
    def weight_edit(log_id):
        log = db.session.get(WeightLog, log_id)
        if not log or log.user_id != current_user.id:
            flash("找不到这条记录", "error")
            return redirect(url_for("weight"))
        if request.method == "POST":
            try:
                log.weight_kg = float(request.form.get("weight_kg", ""))
            except ValueError:
                flash("体重要填数字", "error")
                return redirect(url_for("weight_edit", log_id=log_id))
            log.recorded_at = parse_datetime(request.form.get("recorded_at"))
            log.note = request.form.get("note", "").strip()
            db.session.commit()
            flash("已更新", "ok")
            return redirect(url_for("weight"))
        return render_template("weight_edit.html", log=log)

    @app.route("/weight/<int:log_id>/delete", methods=["POST"])
    @login_required
    def weight_delete(log_id):
        log = db.session.get(WeightLog, log_id)
        if log and log.user_id == current_user.id:
            db.session.delete(log)
            db.session.commit()
            flash("已删除", "ok")
        return redirect(url_for("weight"))

    # ============================== 餐食 ==============================
    @app.route("/meals", methods=["GET", "POST"])
    @login_required
    def meals():
        if request.method == "POST":
            try:
                cal = int(request.form.get("calories", ""))
            except ValueError:
                flash("热量要填整数", "error")
                return redirect(url_for("meals"))
            m = Meal(
                user_id=current_user.id,
                eaten_on=parse_date(request.form.get("eaten_on")),
                meal_type=request.form.get("meal_type", "早餐"),
                food=request.form.get("food", "").strip(),
                calories=cal,
            )
            db.session.add(m)
            db.session.commit()
            flash("已记录", "ok")
            return redirect(url_for("meals"))

        items = (
            Meal.query.filter_by(user_id=current_user.id)
            .order_by(Meal.eaten_on.desc(), Meal.id.desc())
            .all()
        )
        return render_template("meals.html", items=items, today=date.today())

    @app.route("/meals/<int:meal_id>/delete", methods=["POST"])
    @login_required
    def meal_delete(meal_id):
        m = db.session.get(Meal, meal_id)
        if m and m.user_id == current_user.id:
            db.session.delete(m)
            db.session.commit()
            flash("已删除", "ok")
        return redirect(url_for("meals"))

    # ============================== 运动 ==============================
    @app.route("/exercise", methods=["GET", "POST"])
    @login_required
    def exercise():
        if request.method == "POST":
            try:
                minutes = int(request.form.get("minutes", ""))
                burned = int(request.form.get("calories_burned", ""))
            except ValueError:
                flash("时长和消耗都要填整数", "error")
                return redirect(url_for("exercise"))
            e = Exercise(
                user_id=current_user.id,
                done_on=parse_date(request.form.get("done_on")),
                activity=request.form.get("activity", "").strip(),
                minutes=minutes,
                calories_burned=burned,
            )
            db.session.add(e)
            db.session.commit()
            flash("已记录", "ok")
            return redirect(url_for("exercise"))

        items = (
            Exercise.query.filter_by(user_id=current_user.id)
            .order_by(Exercise.done_on.desc(), Exercise.id.desc())
            .all()
        )
        # 取最新体重，用来估算运动消耗；没有记录就先用 60kg 兜底
        lw = (
            WeightLog.query.filter_by(user_id=current_user.id)
            .order_by(WeightLog.recorded_at.desc())
            .first()
        )
        user_weight = lw.weight_kg if lw else 60
        return render_template(
            "exercise.html", items=items, today=date.today(), user_weight=user_weight
        )

    @app.route("/exercise/<int:ex_id>/delete", methods=["POST"])
    @login_required
    def exercise_delete(ex_id):
        e = db.session.get(Exercise, ex_id)
        if e and e.user_id == current_user.id:
            db.session.delete(e)
            db.session.commit()
            flash("已删除", "ok")
        return redirect(url_for("exercise"))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
