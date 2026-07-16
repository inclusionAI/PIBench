<?php
/**
 * Router for `php -S` that mimics Apache mod_php behaviour for the legacy eDoc
 * app: it chdir()s into the executed script's directory so cwd-relative
 * includes such as include("../connection.php") resolve correctly.
 *
 * Usage: php -S 127.0.0.1:8136 -t /workspace/app /path/to/router.php
 */
$root = rtrim($_SERVER['DOCUMENT_ROOT'], '/');
$uriPath = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$uriPath = rawurldecode($uriPath);

// Normalize and resolve the target inside the docroot.
$target = $root . $uriPath;

// Directory request -> look for index.php / index.html.
if (is_dir($target)) {
    foreach (['index.php', 'index.html'] as $idx) {
        if (is_file($target . '/' . $idx)) {
            $target = $target . '/' . $idx;
            break;
        }
    }
}

$real = realpath($target);

// Outside docroot or missing -> let the built-in server return its default 404,
// unless the bare path has no extension (then 404 explicitly).
if ($real === false || strpos($real, $root) !== 0) {
    // Fall back to built-in static handling (covers css/img/etc that exist).
    return false;
}

if (is_file($real)) {
    if (substr($real, -4) === '.php') {
        chdir(dirname($real));
        $_SERVER['SCRIPT_FILENAME'] = $real;
        $_SERVER['SCRIPT_NAME'] = substr($real, strlen($root));
        require $real;
        return true;
    }
    // Static asset: let the built-in server stream it.
    return false;
}

return false;
