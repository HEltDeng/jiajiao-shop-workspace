# 家教小铺

可运行并已部署的前后端预览版。当前运行模式是 sandbox，不收取真实费用。

- 店铺：https://jiajiao.mychangliapp.cn/s/qinghe
- 商家工作台：https://jiajiao.mychangliapp.cn/merchant
- 平台管理入口：https://jiajiao-admin.mychangliapp.cn （跳转同源 `/platform`）
- 前端私有仓库：https://github.com/HEltDeng/jiajiao-shop-frontend
- 后端私有仓库：https://github.com/HEltDeng/jiajiao-shop-backend

本工作区同时保留两个项目。各子目录 README 包含运行方法和接口说明。线上数据保存在服务器 `/var/lib/jiajiao-shop`，不在代码仓库中。未读取或上传本地公司私有资料。

## 验收

- 10 个 API 自动化测试通过：金额与交付、幂等支付/完成/退款、并发库存、超时、权限与 CSRF、租户隔离、商家开铺与商品管理。
- 浏览器完成下单、模拟支付、信息交付、完成退保证金、申请售后、平台退款和流水核对。
- 已检查 390px 手机与 1440px 桌面布局。
- HTTPS、Nginx 配置、后台服务和证书续期计时器正常；既有主站仍返回 HTTP 200。

每个浏览器有独立且有效期为 7 天的演示数据。页头可以切换学生、商家、平台身份。正式收款、真实账号与资质审核、支付签名回调、结算对账等仍需单独接入，当前源码明确禁止开启生产资金模式。
