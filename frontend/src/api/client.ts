import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "@/store/auth";

export const api = axios.create({ baseURL: "/api", timeout: 15000 });

api.interceptors.request.use((cfg: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

let refreshInFlight: Promise<string | null> | null = null;

async function refreshTokens(): Promise<string | null> {
  const rt = useAuthStore.getState().refreshToken;
  if (!rt) return null;
  try {
    const { data } = await axios.post("/api/auth/refresh", { refresh_token: rt });
    useAuthStore.getState().setTokens(data.access_token, data.refresh_token);
    return data.access_token as string;
  } catch {
    useAuthStore.getState().logout();
    return null;
  }
}

api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const cfg = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status === 401 && cfg && !cfg._retry &&
        !cfg.url?.includes("/auth/login") && !cfg.url?.includes("/auth/refresh")) {
      cfg._retry = true;
      refreshInFlight ??= refreshTokens().finally(() => { refreshInFlight = null; });
      const newToken = await refreshInFlight;
      if (newToken) {
        cfg.headers!.Authorization = `Bearer ${newToken}`;
        return api.request(cfg);
      }
    }
    return Promise.reject(error);
  }
);
