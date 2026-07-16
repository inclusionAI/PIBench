const config = require("../../config");

Page({
  data: {
    plans: [],
    selectedPlanId: null,
    form: {
      buyerName: "Benchmark Buyer",
      buyerContact: "13800138000",
      buyerEmail: "benchmark-buyer@example.com",
      buyerId: "",
      buyerOpenId: "",
      buyerAuthCode: ""
    },
    order: null,
    demoMode: true,
    statusText: "Loading membership cards...",
    creating: false,
    paying: false,
    refunding: false
  },

  onLoad() {
    this.loadPlans();
  },

  loadPlans() {
    this.request("GET", "/plans")
      .then((data) => {
        const plans = data.plans || [];
        this.setData({
          plans,
          demoMode: !!data.demo_mode,
          selectedPlanId: plans.length ? plans[0].id : null,
          statusText: plans.length ? "Ready to create a JSAPI trade." : "No active membership cards."
        });
      })
      .catch((error) => this.showError(error));
  },

  selectPlan(event) {
    const id = Number((event.currentTarget || event.target).dataset.id);
    this.setData({ selectedPlanId: id });
  },

  handleInput(event) {
    const field = (event.currentTarget || event.target).dataset.field;
    const value = event.detail.value;
    this.setData({ [`form.${field}`]: value });
  },

  getAuthCode() {
    if (!my.getAuthCode) {
      my.alert({ content: "Run this page in Alipay Mini Program to get an auth code." });
      return;
    }

    my.getAuthCode({
      scopes: ["auth_user"],
      success: (res) => {
        const authCode = res.authCode || "";
        this.setData({
          "form.buyerAuthCode": authCode,
          statusText: authCode ? "Auth code ready for backend exchange." : "Auth code was empty."
        });
      },
      fail: (res) => {
        my.alert({ content: JSON.stringify(res) });
      }
    });
  },

  createOrder() {
    const { selectedPlanId, form } = this.data;
    if (!selectedPlanId) {
      my.alert({ content: "Choose a membership card first." });
      return;
    }

    if (!form.buyerName) {
      my.alert({ content: "Buyer name is required." });
      return;
    }

    this.setData({ creating: true, statusText: "Creating Alipay JSAPI trade..." });
    this.request("POST", "/orders", {
      plan_id: selectedPlanId,
      buyer_name: form.buyerName,
      buyer_contact: form.buyerContact,
      buyer_email: form.buyerEmail,
      buyer_id: form.buyerId,
      buyer_open_id: form.buyerOpenId,
      buyer_auth_code: form.buyerAuthCode
    })
      .then((data) => {
        getApp().globalData.currentOrder = data.order;
        this.setData({
          order: data.order,
          demoMode: !!data.demo_mode,
          statusText: data.demo_mode
            ? "Trade created in demo mode."
            : "Trade created. Ready to call my.tradePay."
        });
      })
      .catch((error) => this.showError(error))
      .then(() => this.setData({ creating: false }));
  },

  payOrder() {
    const order = this.data.order;
    if (!order || !order.tradeNO) {
      my.alert({ content: "Create a JSAPI trade first." });
      return;
    }

    if (!my.tradePay) {
      my.alert({ content: "my.tradePay is only available inside Alipay Mini Program." });
      return;
    }

    this.setData({ paying: true, statusText: "Opening Alipay cashier..." });
    my.tradePay({
      tradeNO: order.tradeNO,
      success: (res) => {
        const resultCode = String(res.resultCode || "");
        this.submitClientResult(resultCode);
      },
      fail: (res) => {
        this.setData({ statusText: "Payment call failed." });
        my.alert({ content: JSON.stringify(res) });
      },
      complete: () => this.setData({ paying: false })
    });
  },

  submitClientResult(resultCode) {
    const order = this.data.order;
    if (!order) {
      return Promise.resolve();
    }

    this.setData({ statusText: `Submitting client payment result: ${resultCode}` });
    return this.request("POST", `/orders/${order.out_trade_no}/client-result`, {
      result_code: resultCode
    })
      .then((data) => {
        getApp().globalData.currentOrder = data.order;
        this.setData({
          order: data.order,
          statusText: `Client result accepted: ${data.order.status}`
        });
      })
      .catch((error) => this.showError(error));
  },

  syncOrder(message) {
    const order = this.data.order;
    if (!order) {
      return Promise.resolve();
    }

    this.setData({ statusText: message || "Confirming payment status..." });
    return this.request("POST", `/orders/${order.out_trade_no}/sync`, {})
      .then((data) => {
        getApp().globalData.currentOrder = data.order;
        this.setData({
          order: data.order,
          statusText: `Payment status: ${data.order.status}`
        });
      })
      .catch((error) => this.showError(error));
  },

  completeDemoPayment() {
    const order = this.data.order;
    if (!order) {
      return;
    }

    this.setData({ paying: true, statusText: "Completing demo payment..." });
    this.request("POST", `/orders/${order.out_trade_no}/demo-complete`, {})
      .then((data) => {
        getApp().globalData.currentOrder = data.order;
        this.setData({
          order: data.order,
          statusText: "Demo payment completed."
        });
      })
      .catch((error) => this.showError(error))
      .then(() => this.setData({ paying: false }));
  },

  refundOrder() {
    const order = this.data.order;
    if (!order) {
      return;
    }

    this.setData({ refunding: true, statusText: "Refunding order..." });
    this.request("POST", `/orders/${order.out_trade_no}/refund`, {
      amount: order.amount
    })
      .then((data) => {
        getApp().globalData.currentOrder = data.order;
        this.setData({
          order: data.order,
          statusText: "Refund completed."
        });
      })
      .catch((error) => this.showError(error))
      .then(() => this.setData({ refunding: false }));
  },

  request(method, path, data) {
    return new Promise((resolve, reject) => {
      const headers = {
        Accept: "application/json",
        "Content-Type": "application/json"
      };

      if (config.refundToken) {
        headers["X-Refund-Token"] = config.refundToken;
      }

      my.request({
        url: `${config.apiBase}${path}`,
        method,
        data,
        headers,
        success: (res) => {
          const status = Number(res.status || res.statusCode || 0);
          if (status >= 200 && status < 300) {
            resolve(res.data || {});
            return;
          }

          reject(new Error((res.data && res.data.message) || `HTTP ${status}`));
        },
        fail: (res) => reject(new Error(res.errorMessage || JSON.stringify(res)))
      });
    });
  },

  showError(error) {
    const message = error && error.message ? error.message : String(error);
    this.setData({ statusText: message });
    my.alert({ content: message });
  }
});
