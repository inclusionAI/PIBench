import AlipaySdkPkg from 'alipay-sdk'
import * as env from '../config/env.config'
import * as logger from '../utils/logger'

const AlipaySdk = (AlipaySdkPkg as any).default || (AlipaySdkPkg as any)

let sdk: any | null = null

const getSdk = () => {
  if (sdk) return sdk
  sdk = new AlipaySdk({
    appId: env.ALIPAY_APP_ID,
    privateKey: env.ALIPAY_PRIVATE_KEY,
    alipayPublicKey: env.ALIPAY_PUBLIC_KEY,
    gateway: env.ALIPAY_GATEWAY,
    keyType: 'PKCS1',
    signType: 'RSA2',
    timeout: 15000,
  })
  return sdk
}

export interface FreezeParams {
  outOrderNo: string
  outRequestNo: string
  orderTitle: string
  amount: string
}

export interface FreezeResult {
  sdkStr: string
  schemeUrl: string
  outOrderNo: string
  outRequestNo: string
}

/**
 * 资金预授权冻结 - 使用 sdkExec (客户端SDK类API)
 * API: alipay.fund.auth.order.app.freeze
 * product_code: PREAUTH_PAY
 */
export const freeze = (params: FreezeParams): FreezeResult => {
  const _sdk = getSdk()
  const bizContent = {
    out_order_no: params.outOrderNo,
    out_request_no: params.outRequestNo,
    order_title: params.orderTitle,
    amount: params.amount,
    product_code: 'PREAUTH_PAY',
    timeout_express: '30m',
  }
  logger.info('[alipay.freeze] request', JSON.stringify(bizContent))
  const sdkStr = _sdk.sdkExec('alipay.fund.auth.order.app.freeze', {
    bizContent,
    notify_url: env.ALIPAY_NOTIFY_URL,
  })
  logger.info('[alipay.freeze] sdkStr length', String(sdkStr.length))
  const schemeUrl = 'alipays://platformapi/startapp?saId=20000199&orderStr=' + encodeURIComponent(sdkStr)
  return {
    sdkStr,
    schemeUrl,
    outOrderNo: params.outOrderNo,
    outRequestNo: params.outRequestNo,
  }
}

/**
 * 查询预授权状态
 * API: alipay.fund.auth.operation.detail.query
 */
export const query = async (outOrderNo: string, outRequestNo: string): Promise<any> => {
  const _sdk = getSdk()
  const r = await _sdk.exec('alipay.fund.auth.operation.detail.query', {
    bizContent: { out_order_no: outOrderNo, out_request_no: outRequestNo },
  }, { validateSign: false })
  logger.info('[alipay.query] response', JSON.stringify(r))
  return r
}

export default { freeze, query }
