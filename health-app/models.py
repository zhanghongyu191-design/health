# models.py —— 数据库的"表结构"都定义在这里
# 一共 4 张表：用户、体重记录、餐食、运动

from datetime import datetime
from zoneinfo import ZoneInfo
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# 日本时区。统一用它来取"现在"，避免服务器在海外导致时间差9小时
JST = ZoneInfo("Asia/Tokyo")


def now_jst():
    """返回日本当前时间（不带时区标记，方便存库和显示）"""
    return datetime.now(JST).replace(tzinfo=None)

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """用户：用来登录。密码不会明文存，存的是加密后的结果。"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=now_jst)

    # 一个用户拥有多条体重/餐食/运动记录
    weights = db.relationship("WeightLog", backref="user", cascade="all, delete-orphan")
    meals = db.relationship("Meal", backref="user", cascade="all, delete-orphan")
    exercises = db.relationship("Exercise", backref="user", cascade="all, delete-orphan")

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)


class WeightLog(db.Model):
    """体重记录。单位 kg。recorded_at 默认当下，可手动改、可编辑、可删除。"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    weight_kg = db.Column(db.Float, nullable=False)
    recorded_at = db.Column(db.DateTime, nullable=False, default=now_jst)
    note = db.Column(db.String(200))


class Meal(db.Model):
    """餐食。meal_type = 早餐/午餐/晚餐/加餐；calories 手动填写。"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    eaten_on = db.Column(db.Date, nullable=False, default=lambda: now_jst().date())
    meal_type = db.Column(db.String(20), nullable=False)   # 早餐 / 午餐 / 晚餐 / 加餐
    food = db.Column(db.String(200), nullable=False)
    calories = db.Column(db.Integer, nullable=False)        # 千卡 kcal


class Exercise(db.Model):
    """运动记录。"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    done_on = db.Column(db.Date, nullable=False, default=lambda: now_jst().date())
    activity = db.Column(db.String(100), nullable=False)    # 例如：跑步、走路
    minutes = db.Column(db.Integer, nullable=False)
    calories_burned = db.Column(db.Integer, nullable=False) # 千卡 kcal
