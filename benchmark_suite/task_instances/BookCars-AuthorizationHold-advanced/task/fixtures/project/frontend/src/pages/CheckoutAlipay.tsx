import React, { useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import Layout from "@/components/Layout"
import env from "@/config/env.config"

const CheckoutAlipay = () => {
  const [searchParams] = useSearchParams()
  const bookingId = searchParams.get("bookingId")
  const [status, setStatus] = useState("checking")
  const [authNo, setAuthNo] = useState("")

  useEffect(() => {
    if (!bookingId) return
    const check = async () => {
      try {
        const res = await fetch(`${env.API_HOST}/api/alipay/query/${bookingId}`, { credentials: "include" })
        const data = await res.json()
        if (data.authNo) {
          setStatus("authorized")
          setAuthNo(data.authNo)
        } else {
          setStatus(data.status || "pending")
        }
      } catch {
        setStatus("error")
      }
    }
    check()
    const timer = setInterval(check, 5000)
    return () => clearInterval(timer)
  }, [bookingId])

  return (
    <Layout strict={false}>
      <div style={{ textAlign: "center", padding: "60px 20px" }}>
        <h2>Alipay Pre-Authorization</h2>
        {status === "checking" && <p>Checking authorization status...</p>}
        {status === "authorized" && (
          <div>
            <p style={{ color: "green", fontSize: 18 }}>Deposit authorized successfully!</p>
            <p>Authorization No: {authNo}</p>
            <p>Booking ID: {bookingId}</p>
          </div>
        )}
        {status === "INIT" && <p>Authorization pending... Please complete in Alipay App.</p>}
        {status === "pending" && <p>Waiting for authorization...</p>}
        {status === "error" && <p style={{ color: "red" }}>Error checking authorization status.</p>}
      </div>
    </Layout>
  )
}

export default CheckoutAlipay
