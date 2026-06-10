# 健康记录 App（体重 / 三餐 / 运动）

一个多人使用、可手机访问的简单健康记录系统。
技术：Python + Flask + SQLAlchemy + Flask-Login。本地用 SQLite，上线用 PostgreSQL。

## 功能
- 注册 / 登录（每人各自账号，密码加密存储，互相看不到数据）
- 体重记录：单位 kg，默认当前时间、可手动改时间、可编辑、可删除
- 三餐：日期 + 餐别 + 食物 + 热量（手动填）
- 运动：日期 + 项目 + 时长 + 消耗热量
- 首页：今日摄入、消耗、净摄入、最新体重

---

## 一、先在自己电脑上跑跑看（可选）

需要先装 Python 3.10 以上。

```bash
pip install -r requirements.txt
python app.py
```

然后浏览器打开 http://127.0.0.1:5000 。
第一次会自动建好数据库文件 local.db。

---

## 二、上线，让大家随时随地用（GitHub + Neon + Render，全免费）

### 第 1 步：把代码放到 GitHub
1. 注册 https://github.com ，新建一个仓库（Repository），可设为 Private。
2. 把这个文件夹里的所有文件传上去（网页上直接拖拽上传也行）。

### 第 2 步：建一个免费数据库（Neon）
1. 注册 https://neon.tech ，新建一个 Project（区域可选 Tokyo，离日本近）。
2. 在 Connection / Dashboard 里复制那串连接地址（Connection String），
   形如：`postgresql://用户名:密码@xxxx.neon.tech/dbname?sslmode=require`
3. 先留着，第 3 步要用。

### 第 3 步：部署到 Render
1. 注册 https://render.com ，选 **New → Web Service**，连上你刚才的 GitHub 仓库。
2. 配置：
   - **Build Command**：`pip install -r requirements.txt`
   - **Start Command**：`gunicorn app:app`
   - **Instance Type**：Free
3. 在 **Environment** 里加两个变量：
   - `DATABASE_URL` = 第 2 步复制的 Neon 连接地址
   - `SECRET_KEY` = 任意一长串随机字符（用来保护登录会话，别人不知道就行）
4. 点 Deploy。完成后 Render 会给你一个网址，形如
   `https://你的应用名.onrender.com` —— 这就是随时随地能访问的地址，
   手机 Safari 打开、加到主屏幕，用起来就像个 App。

---

## 注意事项
- Render 免费版闲置一段时间会休眠，下次打开第一下大约要等 1 分钟唤醒，之后就正常。
- `SECRET_KEY` 上线后一定要设成你自己的随机串，不要用代码里默认的那个。
- 想以后加"AI 自动估算热量""体重折线图"等功能，告诉我，在现有代码上加即可。

## 文件说明
- `app.py` —— 程序主体，所有网址和逻辑
- `models.py` —— 4 张数据库表的定义
- `templates/` —— 各个页面（HTML）
- `static/style.css` —— 样式（已做手机适配）
- `requirements.txt` —— 依赖清单
- `Procfile` —— 告诉 Render 怎么启动
