import { useState, useEffect } from 'react';
import { getHealthStatus } from '@/services/auth';

export const useApiStatus = () => {
  const [isConnected, setIsConnected] = useState<boolean | null>(null);
  const [isChecking, setIsChecking] = useState(true);

  const checkConnection = async () => {
    setIsChecking(true);
    try {
      const healthResponse = await getHealthStatus();
      setIsConnected(healthResponse.success);
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
