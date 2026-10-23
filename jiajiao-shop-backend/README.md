# 家教小铺 · 后端

FastAPI + SQLite 的多店铺交易流程演示后端。前端仓库为 `HEltDeng/jiajiao-shop-frontend`。

这是可运行、数据持久化的 sandbox 版本。未接入真实支付、真实托管、实名登录或商家资质验证；`APP_MODE` 不是 `sandbox` 时直接拒绝启动。演示角色切换不代表生产权限系统，不能直接改成经营系统。

## 本地运行

Python 3.11+，将前后端仓库克隆为相邻目录。

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
FRONTEND_PATH=../jiajiao-shop-frontend .venv/bin/uvicorn app:app --host 127.0.0.1 --port 8796
```

打开 `http://127.0.0.1:8796`。`FRONTEND_PATH` 也可以使用绝对路径。默认数据库是本仓库 `data/sandbox.sqlite3`，已忽略。

## 行为与边界

- 每个浏览器持有独立 HttpOnly 会话，服务端存储 token 哈希。7 天后过期，后续新会话创建时清理旧数据。
- 每个空间有青禾样板店及一个待审核申请。所有课程、联系人、金额均为样例。
- 商品、订单、店铺、审核、流水由 SQLite 持久化；所有读写按空间隔离，商家操作再按所属店铺隔离。
- 创建订单由服务端确定价格；`BEGIN IMMEDIATE` 事务避免库存超卖，幂等键避免重复订单。
- 支付前无联系人；模拟支付后交付。15 分钟未付过期。完成后模拟退保证金并结算信息费。
- 售后申请冻结订单，只有平台演示角色可审核退回全部费用或驳回。重复支付/退款/完成不会重复记账。
- 没有跨店铺公开检索接口。`noindex` / `robots.txt` 用于不收录提示，不构成访问控制。
- CSRF token、同源校验、严格请求模型、安全响应头、请求频率限制；不允许请求体传入价格覆盖或工作空间。
- 管理子域名跳转主域 `/platform`，保留同一主机的隔离 Cookie，避免共享给其他业务子域。

## 主要 API

| 接口 | 用途 |
| --- | --- |
| `POST /api/session` | 建立/恢复隔离演示空间 |
| `POST /api/demo/role` | 仅 sandbox 的角色切换 |
| `GET /api/shops/{slug}` | 当前空间的独立店铺 |
| `POST /api/orders` | 创建订单 |
| `GET /api/orders` | 当前空间的学生订单 |
| `POST /api/orders/{id}/action` | 模拟支付、取消、完成、争议与退款 |
| `POST /api/applications` | 店铺开通申请 |
| `POST /api/shops/{id}/action` | 审核/暂停/恢复 |
| `POST /api/listings` | 商家发布家教需求 |
| `PATCH /api/listings/{id}` | 上下架 |
| `GET /api/workbench` | 按角色和店铺隔离的后台数据 |
| `GET /api/health` | 健康与支付关闭状态 |

所有写请求（建立会话除外）需要 `X-CSRF-Token`。金额单位均为分。启动变量见 `deploy/jiajiao-shop.service`，不包含密钥。

## 测试

```sh
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q tests
```

测试覆盖交付权限、服务端定价、资金状态机、幂等性、并发库存、过期、CSRF、跨空间隔离、商家范围、开铺、停铺及生产收款关闭。

## 部署

`deploy/` 提供 Nginx、systemd 及安装脚本。服务仅监听 `127.0.0.1:8796`；数据库在 `/var/lib/jiajiao-shop`，源码在版本化发布目录。使用非 root 服务账户运行，静态源码只读，只有数据库目录可写。证书通过既有 ACME 账户签发并由 certbot 自动续期。首次部署前需已配置两个域名 A 记录。

## 正式运营前仍需实施

真实账号与商家 RBAC、实名/资质审核、真实支付机构交易及退款、托管/担保安排、签名回调、对账与异常补偿、申诉凭证、商家结算、个人信息授权与保护、数据备份恢复及业务适用性核验。本版本不宣称具备这些能力。
