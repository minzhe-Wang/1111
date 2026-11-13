# AI 智能行政办公平台

## 启动

需要 Python 3.11 或更新版本。在本目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000 。接口说明位于 http://127.0.0.1:8000/docs 。

| 身份 | 用户名 | 本地演示密码 |
| --- | --- | --- |
| 员工 | employee | OfficeDemo1 |
| 管理员 | admin | OfficeDemo2 |

首次启动自动创建 SQLite 数据库。可将 .env.example 复制为 .env，并按需设置 DeepSeek 密钥和 MySQL 连接。MySQL 需先创建空库并授予建表权限。现场验证使用 SQLite 和离线规则。小程序、微信认证、完整日程 CRUD、按时间筛选空闲会议室和多轮对话属于后续范围。账号为本地演示账号。

通过 Git bundle 恢复源码：`git clone office-project.bundle office-project`。如果课程需要在线 Git 地址，把本仓库推送到小组仓库后，将仓库克隆链接填入提交材料。
