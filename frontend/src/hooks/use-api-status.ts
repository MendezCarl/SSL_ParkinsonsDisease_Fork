import { useState, useEffect } from 'react';
import apiService from '@/services/api';

export const useApiStatus = () => {
  const [isConnected, setIsConnected] = useState<boolean | null>(null);
  const [isChecking, setIsChecking] = useState(true);

  const checkConnection = async () => {
    setIsChecking(true);
    try {
      const healthResponse = await apiService.getHealthStatus();
      if (healthResponse.success) {
        const response = await apiService.getPatients(0, 1);
        setIsConnected(response.success);
      } else {
        setIsConnected(false);
      }
    } catch (error) {
      setIsConnected(false);
    } finally {
      setIsChecking(false);
    }
  };

  useEffect(() => {
    checkConnection();
  }, []);

  return {
    isConnected,
    isChecking,
    checkConnection,
  };
}; 
