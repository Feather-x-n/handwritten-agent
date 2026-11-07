# agent-chat

手写 Agent 的 Web 聊天前端：Vue 3 + TypeScript + Vite。

- 左侧会话列表：新建、切换、删除
- 右侧流式聊天：SSE 逐字渲染，支持中途“停止”
- 敏感工具确认：后端暂停工具执行，页面出现“是/否”确认条
- 请求封装：REST 用 axios，SSE 用原生 `fetch` + `ReadableStream`

## 启动

```bash
npm install
npm run dev
```

默认 <http://localhost:5173>。后端默认地址 `http://127.0.0.1:8000`，需要改端口时在本目录建 `.env`：

```
VITE_API_BASE=http://127.0.0.1:8011
```

后端启动和接口说明见 [../../backen/README.md](../../backen/README.md)，整个项目的介绍见 [../../README.md](../../README.md)。

## 目录

```
src/
  App.vue            单页聊天界面、流式渲染、确认条
  api/chat.ts        REST + SSE 请求与类型定义
  utils/request.ts   axios 实例、get/post/del、baseURL
  main.ts            应用入口（单页面，未启用 router/pinia）
```

## 声明

> 本项目的界面样式（页面布局、配色、组件外观、CSS）由 **AI 生成**；接口封装、流式解析、确认交互等逻辑在此基础上编写与调试。
