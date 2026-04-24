import axios, { AxiosError, type AxiosRequestConfig } from "axios";

import webConfig from "@/constants/common-env";
import { clearStoredUserToken, getStoredUserToken } from "@/store/user-auth";

type RequestConfig = AxiosRequestConfig & {
  redirectOnUnauthorized?: boolean;
};

const request = axios.create({
  baseURL: webConfig.apiUrl.replace(/\/$/, ""),
});

request.interceptors.request.use(async (config) => {
  const nextConfig = { ...config };
  const token = await getStoredUserToken();
  const headers = { ...(nextConfig.headers || {}) } as Record<string, string>;
  if (token && !headers.Authorization) {
    headers.Authorization = `Bearer ${token}`;
  }
  // eslint-disable-next-line @typescript-eslint/ban-ts-comment
  // @ts-expect-error
  nextConfig.headers = headers;
  return nextConfig;
});

request.interceptors.response.use(
  (response) => response,
  async (
    error: AxiosError<{ detail?: { error?: string; status?: unknown }; error?: string; message?: string }>,
  ) => {
    const status = error.response?.status;
    const shouldRedirect = (error.config as RequestConfig | undefined)?.redirectOnUnauthorized !== false;
    if (status === 401 && shouldRedirect && typeof window !== "undefined") {
      if (!window.location.pathname.startsWith("/u/login")) {
        await clearStoredUserToken();
        window.location.replace("/u/login");
        return new Promise(() => {});
      }
    }

    const payload = error.response?.data;
    const message =
      payload?.detail?.error || payload?.error || payload?.message || error.message || `请求失败 (${status || 500})`;
    const rejection = new Error(message) as Error & { status?: number; detail?: unknown };
    rejection.status = status;
    rejection.detail = payload?.detail;
    return Promise.reject(rejection);
  },
);

type RequestOptions = {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  redirectOnUnauthorized?: boolean;
};

export async function userHttpRequest<T>(path: string, options: RequestOptions = {}) {
  const { method = "GET", body, headers, redirectOnUnauthorized = true } = options;
  const config: RequestConfig = {
    url: path,
    method,
    data: body,
    headers,
    redirectOnUnauthorized,
  };
  const response = await request.request<T>(config);
  return response.data;
}
