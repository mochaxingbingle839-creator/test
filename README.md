# Encrypted Chat Room（多人聊天室与消息加密）

满足图片中的要求：

- Socket 客户端-服务器通信
- OOP：User / ChatRoom / Message
- 字典管理在线用户与聊天室列表
- select 事件循环收发消息
- 封装消息格式化与用户认证逻辑
- 聊天记录文件保存与导出
- SQLite 存储用户信息与历史消息
- 加分项：AES（AES-GCM）消息加密传输、服务端线程池并发处理、正则文本功能（@提及、表情替换）

## 1. 准备环境

安装 Python 3.10+（Windows）。

在本目录执行：

```bash
pip install -r requirements.txt
```

## 2. 配置

复制并修改配置：

```bash
copy config.example.json config.json
```

把 `shared_secret` 改成足够长的随机字符串。服务端和客户端必须使用同一份 `config.json`（至少 `host/port/shared_secret` 要一致）。

## 3. 启动服务端

```bash
python server.py
```

## 4. 启动客户端

另开一个终端：

```bash
python client.py
```

## 5. 客户端命令

- `/register <用户名> <密码>`
- `/login <用户名> <密码>`
- `/join <房间名>`
- `/rooms`
- `/users`
- `/export <房间名>`
- `/quit`

加入房间后，直接输入文本并回车即可发送到当前房间。

