<?php
require_once __DIR__ . "/connection.php";

$result = $database->query("SELECT 1 AS ok");

header("Content-Type: application/json");
echo json_encode([
    "ok" => $result && $result->fetch_assoc()["ok"] == 1,
    "service" => "edoc-h5",
]);
?>
