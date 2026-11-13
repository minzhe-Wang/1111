# 智行政 · AI 智能行政办公平台

成员为王闽浙。负责需求、开发、测试与答辩，使用 AI 辅助编码。
源码仓库 https://github.com/minzhe-Wang/1111.git

## 运行环境

Python 3.11+、Java 21、Maven 3.9、MariaDB/MySQL、Redis。
数据库创建 office 库，配置数据库账号。将 .env.example 复制为 .env，填写 DATABASE_URL、REDIS_URL、JWT_SECRET、DEEPSEEK_API_KEY。
.env 不提交到 Git。默认 SQLite 仅供快速启动，验收测试使用 MariaDB 11.7。

在项目根目录安装 Python 依赖，然后启动数据服务。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001
```

在另一个终端启动 Java Web 入口。

```powershell
cd java-server
mvn package
java -jar target/office-web-1.0.0.jar
```

员工端 http://127.0.0.1:8080/
管理端 http://127.0.0.1:8080/admin.html
移动 H5 http://127.0.0.1:8080/mobile.html
接口文档 http://127.0.0.1:8001/docs

演示员工 employee / OfficeDemo1，管理员 admin / OfficeDemo2。注册接口仅能创建员工。
密码使用随机盐与 PBKDF2-SHA256 存储。

## 实现

SpringBoot 承担静态页面和 API 统一入口，Python FastAPI 执行业务与模型调用。
MariaDB 保存用户、资源锁、业务记录和 Agent 日志。
日程支持提交、修改与删除。会议室支持预约、撤回、审批及并发冲突检查。出差支持申请、撤回、审批与归档。
会议室目录使用本地 3 秒与 Redis 60 秒缓存。目录当前为固定配置，变更后应重启数据服务并清理 office:room-catalog:v1。
实时预约状态直接读取数据库。并发预约对资源记录加锁。
Agent 调用 DeepSeek 解析有限技能，提供日程查询、容量匹配与出差草稿。Redis 保存最近 12 条对话，过期时间 30 分钟。
业务写入通过表单提交，管理员审批接口单独鉴权。
模型异常会切换离线规则，并在界面与日志标明模式。

## 验证与范围

test-result.json 为本机通过 SpringBoot 入口的实际测试结果。包含并发预约、权限隔离和 10 并发 100 次查询测试。性能数字仅代表本机此次测试。
tests/integration.py 可重新执行，要求本机服务已启动及 DeepSeek 密钥可用，会创建带 test_ 前缀的账号和测试业务记录，并产生少量模型调用费用。

当前移动端为 H5，尚未实现微信授权、多模态、完整自然语言写操作、独立 Agent 服务账号和 Skill 开关。会议室助手按容量匹配，提交预约时才校验时段。
