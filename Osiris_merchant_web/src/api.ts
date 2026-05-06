import axios from 'axios';

// Connect to the local backend using standard localhost.
// The backend now has CORSMiddleware enabled for development.
const apiClient = axios.create({
  baseURL: 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor to attach the auth token to requests automatically
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('merchant_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const loginMerchant = async (email: string, password: string) => {
  // Uses the new unified role-aware login endpoint
  const response = await apiClient.post('/api/v1/auth/login', {
    email,
    password,
    device_timestamp: new Date().toISOString(),
  });
  return response.data;
};

export const registerMerchant = async (name: string, email: string, password: string, businessType: string) => {
  const response = await apiClient.post('/api/v1/merchants/register', {
    name,
    email,
    password,
    business_type: businessType,
  });
  return response.data;
};

export const fetchBounties = async (merchantId: number) => {
  // Uses the newly created endpoint for fetching merchant analytics
  const response = await apiClient.get(`/api/v1/merchants/${merchantId}/bounties`);
  return response.data;
};

export default apiClient;
