import axios from 'axios'

// 后端地址：axios 和流式 fetch 共用，避免两处写不一样
export const baseURL = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

// axios 实例：统一后端地址、超时和错误处理
const service = axios.create({
  baseURL,
  // Agent 一次回复可能要十几秒（模型 + 工具循环），5 秒不够用
  timeout: 120000,
})

// 响应拦截器：成功时直接返回后端 JSON；失败时把后端的 detail 转成 Error
service.interceptors.response.use(
  (res) => res.data,
  (err) => Promise.reject(new Error(err.response?.data?.detail ?? err.message ?? '请求失败')),
)

// 拦截器已经把 res.data 取出来了，这里补一层泛型，调用处就能拿到正确的类型
export function get<T>(url: string): Promise<T> {
  return service.get(url) as unknown as Promise<T>
}

export function post<T>(url: string, data?: unknown): Promise<T> {
  return service.post(url, data) as unknown as Promise<T>
}

export function del<T>(url: string): Promise<T> {
  return service.delete(url) as unknown as Promise<T>
}

export default service
