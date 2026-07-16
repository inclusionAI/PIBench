/* eslint-disable no-undef */
const healthCheckController = require('../src/controllers/healthCheck.controller');

describe("Healthcheck", () => {
    it("returns OK, success and up, if server is healthy", async () => {
        let statusCode = 200;
        let body;
        const res = {
            status: (code) => {
                statusCode = code;
                return res;
            },
            send: (responseBody) => {
                body = responseBody;
            }
        };

        await healthCheckController.getHealthStatus({}, res, () => {});

        const result = {
            health: body.body.health,
            success: body.headers.success,
            up: body.body.uptime > 0
        };

        if (statusCode !== 200) throw new Error(`Expected 200, got ${statusCode}`);
        if (result.health !== 'OK') throw new Error(`Expected OK, got ${result.health}`);
        if (result.success !== 1) throw new Error(`Expected success 1, got ${result.success}`);
        if (!result.up) throw new Error('Expected uptime to be greater than 0');
    });
});
