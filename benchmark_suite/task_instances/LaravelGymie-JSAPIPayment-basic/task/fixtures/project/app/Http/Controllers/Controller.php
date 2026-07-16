<?php

namespace App\Http\Controllers;

use Illuminate\Foundation\Auth\Access\AuthorizesRequests;
use Illuminate\Foundation\Validation\ValidatesRequests;

/**
 * Base application controller.
 *
 * Provides common Laravel controller helpers such as authorization and validation.
 */
abstract class Controller
{
    use AuthorizesRequests, ValidatesRequests;
}
