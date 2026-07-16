export const apiFetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  const credentials = localStorage.getItem('auth_credentials');

  const headers = new Headers(init?.headers);
  if (credentials) {
    headers.set('Authorization', `Basic ${credentials}`);
  }

  const response = await fetch(input, {
    ...init,
    headers,
  });

  if (response.status === 401) {
    // Optional: trigger a logout if the token becomes invalid
    // localStorage.removeItem('auth_credentials');
    // localStorage.setItem('isAuthenticated', 'false');
    // window.location.href = '/';
  }

  return response;
};
