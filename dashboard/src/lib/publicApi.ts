import axios from 'axios';

/**
 * Unauthenticated client for public, opt-in endpoints (e.g. GET /public/{slug}).
 *
 * Intentionally separate from `lib/api.ts`: it has NO Authorization header and
 * NO 401 refresh/redirect interceptor. Public pages must never attach a token
 * or bounce an anonymous visitor to /login.
 */
const publicApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

export default publicApi;
