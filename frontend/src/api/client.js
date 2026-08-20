import axios from "axios";

// In dev (`npm run dev`), frontend and backend run on different ports
// (5173 vs 8000), so default to the backend's own origin. In a built
// production bundle, frontend and backend are served same-origin (FastAPI
// mounts the built frontend directly), so default to a relative "" instead
// of hardcoding localhost - a bundle built once and deployed elsewhere must
// not point back at the visitor's own machine.
export const BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.DEV ? "http://localhost:8000" : "");

const client = axios.create({ baseURL: `${BASE_URL}/api/v1` });

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("expms_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("expms_token");
      localStorage.removeItem("expms_user");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default client;

export function apiErrorMessage(err) {
  return err?.response?.data?.detail || err?.message || "Something went wrong";
}
