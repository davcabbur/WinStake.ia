/**
 * WinStake.ia — Environment Configuration (Development)
 *
 * IMPORTANT: This file is committed to git as it only contains
 * the structure. The actual API key should be set via environment
 * or replaced during build.
 */
export const environment = {
  production: false,
  apiBaseUrl: 'http://localhost:8000',
  // Set your DASHBOARD_API_KEY here for local development.
  // In production, this should be injected at build time.
  apiKey: '477af6fafada45aa5dfacde49d8ee012ee90477c402b838414a5f1bb2fec8567',
};
