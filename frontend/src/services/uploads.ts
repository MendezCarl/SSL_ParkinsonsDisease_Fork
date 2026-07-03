import { apiClient } from '@/services/client';
import type { UploadVideoResponse } from '@/services/patient-mappers';
import type { ServiceResponse } from '@/services/service-response';

export async function uploadVideo(formData: FormData): Promise<ServiceResponse<UploadVideoResponse>> {
  return apiClient.request<UploadVideoResponse>('/upload-video/', {
    method: 'POST',
    body: formData,
  });
}
