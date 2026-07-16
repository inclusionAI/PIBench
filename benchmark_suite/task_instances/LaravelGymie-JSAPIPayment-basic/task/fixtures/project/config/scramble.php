<?php

/**
 * Scramble (OpenAPI) configuration.
 *
 * Note: this file must stay safe to load even when Scramble isn't installed yet.
 * Avoid referencing Scramble classes directly; use strings where needed.
 *
 * @see https://scramble.dedoc.co/
 */
return [
    /*
    |--------------------------------------------------------------------------
    | API path
    |--------------------------------------------------------------------------
    |
    | Only routes under this path will be documented.
    */
    'api_path' => 'api/v1',

    /*
    |--------------------------------------------------------------------------
    | API domain
    |--------------------------------------------------------------------------
    |
    | Set this if your API is hosted on a separate domain.
    */
    'api_domain' => null,

    /*
    |--------------------------------------------------------------------------
    | API Information
    |--------------------------------------------------------------------------
    */
    'info' => [
        'version' => env('API_VERSION', '1.0.0'),
        'title' => 'Gymie API',
        'description' => 'Gymie JSON API. Bearer token auth: send `Authorization: Bearer <token>` and `Accept: application/json`.',
    ],

    /*
    |--------------------------------------------------------------------------
    | Servers
    |--------------------------------------------------------------------------
    |
    | When null, Scramble generates server URL from `api_path` and `api_domain`.
    */
    'servers' => null,

    /*
    |--------------------------------------------------------------------------
    | Docs access
    |--------------------------------------------------------------------------
    |
    | By default, keep docs accessible only in local environment.
    | You can override the gate in a service provider if needed later.
     */
    'middleware' => [
        'web',
        'Dedoc\\Scramble\\Http\\Middleware\\RestrictedDocsAccess',
    ],

    /*
    |--------------------------------------------------------------------------
    | Extensions
    |--------------------------------------------------------------------------
    */
    'extensions' => [],
];
