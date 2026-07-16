<?php

    //learn from w3schools.com

    session_start();

    if(isset($_SESSION["user"])){
        if(($_SESSION["user"])=="" or $_SESSION['usertype']!='p'){
            header("location: ../login.php");
        }else{
            $useremail=$_SESSION["user"];
        }

    }else{
        header("location: ../login.php");
    }
    

    //import database
    include("../connection.php");
    require_once("../lib/payment_repository.php");
    $sqlmain= "select * from patient where pemail=?";
    $stmt = $database->prepare($sqlmain);
    $stmt->bind_param("s",$useremail);
    $stmt->execute();
    $userrow = $stmt->get_result();
    $userfetch=$userrow->fetch_assoc();
    $userid= $userfetch["pid"];
    $username=$userfetch["pname"];


    if($_POST){
        if(isset($_POST["booknow"])){
            $apponum=$_POST["apponum"];
            $scheduleid=$_POST["scheduleid"];
            $date=$_POST["date"];
            $promoCode=$_POST["promo_code"] ?? "";
            $appointment = create_pending_appointment($database, (int) $userid, (int) $apponum, (int) $scheduleid, $date, $promoCode);
            create_or_reuse_payment($database, $appointment);
            header("location: alipay-h5/pay.php?out_trade_no=".$appointment["out_trade_no"]);

        }
    }
 ?>
