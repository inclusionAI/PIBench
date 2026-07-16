const config = require("../../config");

Page({
  data: {
    plans: [],
    selectedPlanId: null,
    form: {
      buyerName: "Benchmark Buyer",
      buyerContact: "13800138000",
      buyerEmail: "benchmark-buyer@example.com"
    },
    order: null,
    statusText: "Loading membership cards...",
    creating: false
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
          selectedPlanId: plans.length ? plans[0].id : null,
          statusText: plans.length ? "Ready to create an order." : "No active membership cards."
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

    this.setData({ creating: true, statusText: "Creating order..." });
    this.request("POST", "/orders", {
      plan_id: selectedPlanId,
      buyer_name: form.buyerName,
      buyer_contact: form.buyerContact,
      buyer_email: form.buyerEmail
    })
      .then((data) => {
        getApp().globalData.currentOrder = data.order;
        this.setData({
          order: data.order,
          statusText: "Order created."
        });
      })
      .catch((error) => this.showError(error))
      .then(() => this.setData({ creating: false }));
  },

  request(method, path, data) {
    return new Promise((resolve, reject) => {
      my.request({
        url: `${config.apiBase}${path}`,
        method,
        data,
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
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
