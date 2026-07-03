import { getStoredAuthToken } from '@/auth/auth-session';
import type { ServiceResponse } from '@/services/service-response';

export const API_BASE_URL = '/api';

export class ApiClient {
  constructor(private readonly baseUrl: string = API_BASE_URL) {}

  async request<T>(endpoint: string, options: RequestInit = {}): Promise<ServiceResponse<T>> {
    try {
      const url = `${this.baseUrl}${endpoint}`;
      const isFormDataBody = options.body instanceof FormData;
      const token = getStoredAuthToken();
      const headers: HeadersInit = isFormDataBody
        ? {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...options.headers,
          }
        : {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...options.headers,
          };

      const response = await fetch(url, {
        headers,
        ...options,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));

        let errorMessage = `HTTP error! status: ${response.status}`;

        if (errorData.detail) {
          if (Array.isArray(errorData.detail)) {
            errorMessage = errorData.detail
              .map((err: { loc?: string[]; msg: string }) => {
                const field = err.loc?.join('.') || 'field';
                return `${field}: ${err.msg}`;
              })
              .join(', ');
          } else if (typeof errorData.detail === 'object') {
            errorMessage = JSON.stringify(errorData.detail);
          } else {
            errorMessage = errorData.detail;
          }
        } else if (errorData.message) {
          errorMessage = errorData.message;
        }

        throw new Error(errorMessage);
      }

      const data = await response.json();
      return { success: true, data };
    } catch (error) {
      console.error('API request failed:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred',
      };
    }
  }
}

export const apiClient = new ApiClient();
