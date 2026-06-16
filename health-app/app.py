# app.py —— 程序主体：网址(路由) + 登录逻辑都在这里
import os
from datetime import datetime, date, time, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)

from models import db, User, WeightLog, Meal, Exercise, Profile, now_jst


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
            return now_jst()
        try:
            return datetime.strptime(text, "%Y-%m-%dT%H:%M")
        except ValueError:
            return now_jst()

    def parse_date(text):
        if not text:
            return now_jst().date()
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return now_jst().date()

    # 记录列表的"期间"筛选：返回 (起, 止) 两个日期，含两端；(None,None) 表示全部
    PERIOD_OPTIONS = [
        ("7d", "近7天"), ("30d", "近30天"), ("month", "本月"),
        ("lastmonth", "上月"), ("all", "全部"),
    ]

    def period_range(period):
        today = now_jst().date()
        if period == "30d":
            return today - timedelta(days=29), today
        if period == "month":
            return today.replace(day=1), today
        if period == "lastmonth":
            first_this = today.replace(day=1)
            last_prev = first_this - timedelta(days=1)
            return last_prev.replace(day=1), last_prev
        if period == "all":
            return None, None
        return today - timedelta(days=6), today   # 默认近7天

    def normalize_period(period):
        valid = {k for k, _ in PERIOD_OPTIONS}
        return period if period in valid else "7d"

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
    def build_weight_chart(points, goals):
        """纯 SVG 折线图。
        points: [(label, weight), ...] 已按时间排好，label 是 x 轴两端的文字。
        goals:  [(value, color, name), ...] 要画的水平目标虚线。
        少于 2 个点不画线。"""
        if len(points) < 2:
            return None
        W, H = 320.0, 140.0
        padx, top, bottom = 12.0, 18.0, 30.0
        ws = [w for _, w in points]
        # y 轴范围要把目标线也算进去，否则目标线会画到图外
        allvals = ws + [g[0] for g in goals if g[0] is not None]
        wmin, wmax = min(allvals), max(allvals)
        span = (wmax - wmin) or 1.0
        n = len(points)
        fx = lambda i: padx + (W - 2 * padx) * (i / (n - 1))
        fy = lambda w: top + (H - top - bottom) * (1 - (w - wmin) / span)

        # 目标虚线
        goal_lines = ""
        for value, color, name in goals:
            if value is None:
                continue
            gy = fy(value)
            goal_lines += (
                f'<line x1="{padx}" y1="{gy:.1f}" x2="{W-padx}" y2="{gy:.1f}" '
                f'stroke="{color}" stroke-width="1" stroke-dasharray="4 3"/>'
                f'<text x="{W-padx:.0f}" y="{gy-3:.1f}" font-size="8" fill="{color}" '
                f'text-anchor="end">{name} {value:g}</text>'
            )

        coords = [(fx(i), fy(w)) for i, (_, w) in enumerate(points)]
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
        dots = "".join(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="var(--primary)"/>'
            f'<circle class="wpt" cx="{x:.1f}" cy="{y:.1f}" r="8" fill="transparent" '
            f'data-d="{lbl}" data-w="{w:g}" style="cursor:pointer"/>'
            for (x, y), (lbl, w) in zip(coords, points)
        )
        return (
            f'<svg viewBox="0 0 {W:.0f} {H:.0f}" width="100%" '
            f'preserveAspectRatio="xMidYMid meet" style="display:block">'
            f'{goal_lines}'
            f'<polyline points="{poly}" fill="none" stroke="var(--primary)" '
            f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
            f'{dots}'
            f'<text x="{padx}" y="11" font-size="9" fill="#7d877f">{wmax:g} kg</text>'
            f'<text x="{padx}" y="{H-16:.0f}" font-size="9" fill="#7d877f">{wmin:g} kg</text>'
            f'<text x="{padx}" y="{H-3:.0f}" font-size="9" fill="#7d877f">{points[0][0]}</text>'
            f'<text x="{W-padx:.0f}" y="{H-3:.0f}" font-size="9" fill="#7d877f" '
            f'text-anchor="end">{points[-1][0]}</text>'
            f'</svg>'
        )

    def get_or_create_profile(uid):
        p = Profile.query.filter_by(user_id=uid).first()
        if not p:
            p = Profile(user_id=uid)
            db.session.add(p)
            db.session.commit()
        return p

    @app.route("/")
    @login_required
    def dashboard():
        uid = current_user.id
        today = now_jst().date()
        sel = parse_date(request.args.get("date")) if request.args.get("date") else today
        period = request.args.get("period", "month")  # week / month / year，默认一个月

        sel_meals = Meal.query.filter_by(user_id=uid, eaten_on=sel).all()
        sel_ex = Exercise.query.filter_by(user_id=uid, done_on=sel).all()
        calories_in = sum(m.calories for m in sel_meals)
        calories_out = sum(e.calories_burned for e in sel_ex)

        day_end = datetime.combine(sel, time.max)
        latest_weight = (
            WeightLog.query.filter_by(user_id=uid)
            .filter(WeightLog.recorded_at <= day_end)
            .order_by(WeightLog.recorded_at.desc())
            .first()
        )

        profile = get_or_create_profile(uid)

        # 本月目标是否需要提醒重设（跨月了）
        this_ym = today.strftime("%Y-%m")
        month_goal_outdated = (
            profile.month_goal_weight is not None and profile.month_goal_ym != this_ym
        )

        # 离目标差多少
        cur = latest_weight.weight_kg if latest_weight else None
        diff_goal = round(cur - profile.goal_weight, 1) if (cur is not None and profile.goal_weight) else None
        diff_month = round(cur - profile.month_goal_weight, 1) if (cur is not None and profile.month_goal_weight) else None

        # ---- 体重趋势：按时段取数据 ----
        now_dt = now_jst()
        if period == "week":
            start_dt = now_dt - timedelta(days=7)
        elif period == "year":
            start_dt = now_dt - timedelta(days=365)
        else:
            period = "month"
            start_dt = now_dt - timedelta(days=30)

        logs = (
            WeightLog.query.filter_by(user_id=uid)
            .filter(WeightLog.recorded_at >= start_dt)
            .order_by(WeightLog.recorded_at.asc())
            .all()
        )

        if period == "year":
            # 一年：按月平均，每月一个点
            buckets = {}
            for l in logs:
                key = l.recorded_at.strftime("%Y-%m")
                buckets.setdefault(key, []).append(l.weight_kg)
            points = [
                (k[2:].replace("-", "/"), round(sum(v) / len(v), 1))  # 标签如 26/06
                for k, v in sorted(buckets.items())
            ]
        else:
            points = [(l.recorded_at.strftime("%m/%d"), l.weight_kg) for l in logs]

        goals = [
            (profile.goal_weight, "#c2553f", "终极"),
            (profile.month_goal_weight, "#246b5f", "本月"),
        ]
        chart_svg = build_weight_chart(points, goals)

        # 最近体重记录（最近 8 条，算出与上一条的升降）
        rw = (
            WeightLog.query.filter_by(user_id=uid)
            .order_by(WeightLog.recorded_at.desc())
            .limit(8)
            .all()
        )
        recent_weights = []
        for i, w in enumerate(rw):
            older = rw[i + 1] if i + 1 < len(rw) else None
            delta = round(w.weight_kg - older.weight_kg, 1) if older else None
            recent_weights.append({"dt": w.recorded_at, "kg": w.weight_kg, "delta": delta})

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
            period=period,
            profile=profile,
            diff_goal=diff_goal,
            diff_month=diff_month,
            month_goal_outdated=month_goal_outdated,
            recent_weights=recent_weights,
        )

    @app.route("/profile", methods=["POST"])
    @login_required
    def profile_update():
        p = get_or_create_profile(current_user.id)

        def parse_num(name):
            raw = request.form.get(name, "").strip()
            if raw == "":
                return None
            try:
                return float(raw)
            except ValueError:
                return None

        p.height_cm = parse_num("height_cm")
        p.goal_weight = parse_num("goal_weight")
        new_month_goal = parse_num("month_goal_weight")
        if new_month_goal != p.month_goal_weight:
            # 本月目标有变动，记下是这个月设的
            p.month_goal_weight = new_month_goal
            p.month_goal_ym = now_jst().strftime("%Y-%m")
        db.session.commit()
        flash("个人资料已更新", "ok")
        return redirect(url_for("dashboard"))

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

        # 期间筛选（只影响下面的明细列表）
        period = normalize_period(request.args.get("period", "7d"))
        start, end = period_range(period)
        q = WeightLog.query.filter_by(user_id=current_user.id)
        if start is not None:
            q = q.filter(
                WeightLog.recorded_at >= datetime.combine(start, time.min),
                WeightLog.recorded_at <= datetime.combine(end, time.max),
            )
        logs = q.order_by(WeightLog.recorded_at.desc()).all()

        # BMI / 标准体重：始终基于"全部记录里最新的一条"（不受期间筛选影响）
        latest = (
            WeightLog.query.filter_by(user_id=current_user.id)
            .order_by(WeightLog.recorded_at.desc())
            .first()
        )
        profile = Profile.query.filter_by(user_id=current_user.id).first()
        height = profile.height_cm if profile else None
        bmi = bmi_label = standard_weight = bmi_date = None
        if height and latest:
            h_m = height / 100.0
            cur = latest.weight_kg
            bmi = round(cur / (h_m * h_m), 1)
            bmi_date = latest.recorded_at  # 这条体重是哪天的
            if bmi < 18.5:
                bmi_label = "偏瘦"
            elif bmi < 25:
                bmi_label = "正常"
            elif bmi < 30:
                bmi_label = "偏胖"
            else:
                bmi_label = "肥胖"
            standard_weight = round(22 * h_m * h_m, 1)  # BMI=22 对应的标准体重

        return render_template(
            "weight.html",
            logs=logs,
            now=now_jst(),
            period=period,
            period_options=PERIOD_OPTIONS,
            bmi_date=bmi_date,
            bmi_weight=(latest.weight_kg if latest else None),
            height=height,
            bmi=bmi,
            bmi_label=bmi_label,
            standard_weight=standard_weight,
            goal_weight=(profile.goal_weight if profile else None),
        )

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

        period = normalize_period(request.args.get("period", "7d"))
        start, end = period_range(period)
        q = Meal.query.filter_by(user_id=current_user.id)
        if start is not None:
            q = q.filter(Meal.eaten_on >= start, Meal.eaten_on <= end)
        items = q.order_by(Meal.eaten_on.desc(), Meal.id.desc()).all()
        return render_template(
            "meals.html", items=items, today=now_jst().date(),
            period=period, period_options=PERIOD_OPTIONS,
        )

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

        period = normalize_period(request.args.get("period", "7d"))
        start, end = period_range(period)
        q = Exercise.query.filter_by(user_id=current_user.id)
        if start is not None:
            q = q.filter(Exercise.done_on >= start, Exercise.done_on <= end)
        items = q.order_by(Exercise.done_on.desc(), Exercise.id.desc()).all()
        # 取最新体重，用来估算运动消耗；没有记录就先用 60kg 兜底
        lw = (
            WeightLog.query.filter_by(user_id=current_user.id)
            .order_by(WeightLog.recorded_at.desc())
            .first()
        )
        user_weight = lw.weight_kg if lw else 60
        return render_template(
            "exercise.html", items=items, today=now_jst().date(), user_weight=user_weight,
            period=period, period_options=PERIOD_OPTIONS,
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
