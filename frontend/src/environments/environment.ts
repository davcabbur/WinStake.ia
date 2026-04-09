/**
 * WinStake.ia — Environment Configuration (template/production)
 *
 * Do NOT put real secrets here. This file is committed to git.
 * For local dev, create src/environments/environment.development.ts
 * (gitignored) with the real values — angular.json will swap it in
 * automatically when running `ng serve` or `ng build --configuration development`.
 *
 * For production deployments, inject WINSTAKE_API_KEY and
 * WINSTAKE_API_BASE_URL at build time via CI/CD.
 */
export const environment = {
  production: true,
  apiBaseUrl: 'http://localhost:8000',
  apiKey: '',
};
