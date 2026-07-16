<?php
$servername = getenv("DB_HOST") ?: "db";
$username = getenv("DB_USER") ?: "edoc";
$password = getenv("DB_PASSWORD") ?: "edoc";
$dbname = getenv("DB_NAME") ?: "edoc";
$port = (int) (getenv("DB_PORT") ?: 3306);

$database = new mysqli($servername, $username, $password, $dbname, $port);

if ($database->connect_error) {
    http_response_code(500);
    die("Database connection failed: " . $database->connect_error);
}

$database->set_charset("utf8mb4");
?>
