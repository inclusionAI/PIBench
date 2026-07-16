<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/**
 * Force API routes to negotiate JSON responses.
 *
 * When a browser hits `/api/...` directly, it typically sends `Accept: text/html`,
 * which causes Laravel's authentication middleware to attempt a redirect to a
 * `login` route. This app intentionally does not expose a web login route (Filament
 * handles authentication), so we force JSON Accept headers for API requests.
 */
final class ForceJsonResponse
{
    /**
     * @param  Closure(Request): Response  $next
     */
    public function handle(Request $request, Closure $next): Response
    {
        $accept = (string) $request->headers->get('Accept', '');

        if (! str_contains($accept, 'application/json')) {
            $request->headers->set('Accept', 'application/json');
        }

        return $next($request);
    }
}
