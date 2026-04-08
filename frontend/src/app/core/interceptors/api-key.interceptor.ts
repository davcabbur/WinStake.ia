import { HttpInterceptorFn } from '@angular/common/http';
import { environment } from '../../../environments/environment';

/**
 * HTTP Interceptor that attaches the X-API-Key header to all
 * outgoing requests to the WinStake backend.
 */
export const apiKeyInterceptor: HttpInterceptorFn = (req, next) => {
  // Only attach to requests going to our API
  if (req.url.startsWith(environment.apiBaseUrl)) {
    const cloned = req.clone({
      setHeaders: {
        'X-API-Key': environment.apiKey,
      },
    });
    return next(cloned);
  }
  return next(req);
};
