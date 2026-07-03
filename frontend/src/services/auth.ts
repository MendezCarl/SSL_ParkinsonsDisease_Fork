import type { AuthUser } from '@/auth/auth-session';
import { apiClient } from '@/services/client';
import type { ServiceResponse } from '@/services/service-response';
import type { AuthTokenPayload, HealthStatus, LoginResponse } from '@/services/patient-mappers';

export async function getHealthStatus(): Promise<ServiceResponse<HealthStatus>> {
  return apiClient.request<HealthStatus>('/health');
}

export async function login(username: string, password: string): Promise<ServiceResponse<AuthTokenPayload>> {
  const formData = new URLSearchParams();
  formData.set('username', username);
  formData.set('password', password);

  const response = await apiClient.request<LoginResponse>('/token', {
    method: 'POST',
    body: formData.toString(),
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  });

  if (response.success && response.data) {
    return {
      success: true,
      data: {
        accessToken: response.data.access_token,
        tokenType: response.data.token_type,
      },
    };
  }

  return { success: false, error: response.error };
}

export async function getCurrentUser(authToken?: string): Promise<ServiceResponse<AuthUser>> {
  const response = await apiClient.request<{
    username: string;
    full_name: string;
    email?: string | null;
    location: string;
    title: string;
    speciality: string;
  }>('/me', {
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
  });

  if (response.success && response.data) {
    return {
      success: true,
      data: {
        username: response.data.username,
        fullName: response.data.full_name,
        email: response.data.email,
        location: response.data.location,
        title: response.data.title,
        speciality: response.data.speciality,
      },
    };
  }

  return { success: false, error: response.error };
}
