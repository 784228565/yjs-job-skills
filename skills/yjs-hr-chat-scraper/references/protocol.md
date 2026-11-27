# 协议与实现备忘（排坑用）

## 链路

```
App 抓包凭证 (txinit) ──→ 腾讯 IM SDK 官方登录 ──→ getConversationList / getMessageList
     im_creds.json            (tx.umd.min.js,          结构化消息
                              全局名 TencentCloudChat)
```

- 聊天入口虽在 App，但消息存在腾讯 IM 云端，官方 SDK 登录后全量可读
- SDKAPPID=1400329（应届生/51job 嗨聊共用）
- SDK 资源内置在 `assets/tx_umd.min.js`，不依赖外网 CDN

## 已踩过的坑

1. **CDP WebSocket 403**：Chrome 155+ 校验 Origin，必须 `websocket.create_connection(..., suppress_origin=True)`
2. **SDK ready 前不能调 `once`/`on`**（code 3000 拦截，promise 永不 resolve）：必须轮询 `tim.isReady()`
3. **userSig 里的 `*`**：抓包 URL 转义会把 `+` 变 `*`，base64 解码前要替换回 `+`
4. **SDK 全局名是 `TencentCloudChat`** 不是 `TIM`（UMD 导出名）
5. 会话列表要分页（`nextReqMessageID` + `isCompleted`），237+ 会话一次拉不完
6. 系统号会话：`special1`=谁对我感兴趣、`special10`=OK仔广播站、`special35`=校招发布；
   special1 的自定义卡片 `payload.data` 是 JSON，含 HR 浏览记录（公司/jobid/时间），可 `JSON.parse`

## 消息类型

| TIM 类型 | 解析 |
|---|---|
| TIMTextElem | payload.text |
| TIMImageElem | payload.imageInfoArray[0].url |
| TIMCustomElem | payload.description + payload.data（JSON 时解析为 extra） |
| 其他 | 原样标记 [类型] |

## 合规

- 只抓取**本人账号**的消息数据；凭证文件 im_creds.json 等同账号密码，仅存本机、勿提交 git
- 输出文件含 HR 个人信息，注意本地保存与分享范围
- 抓取频率保持温和（会话间隔 0.3s），不要并发打腾讯 IM 接口
