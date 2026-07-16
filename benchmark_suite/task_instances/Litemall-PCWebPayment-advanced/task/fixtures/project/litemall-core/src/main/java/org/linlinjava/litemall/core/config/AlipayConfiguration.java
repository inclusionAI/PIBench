package org.linlinjava.litemall.core.config;

import com.alipay.api.AlipayClient;
import com.alipay.api.DefaultAlipayClient;
import com.alipay.api.AlipayConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AlipayConfiguration {

    @Bean
    public AlipayClient alipayClient(AlipayProperties props) throws Exception {
        AlipayConfig alipayConfig = new AlipayConfig();
        alipayConfig.setServerUrl(props.getGatewayUrl());
        alipayConfig.setAppId(props.getAppId());
        alipayConfig.setPrivateKey(props.getPrivateKey());
        alipayConfig.setFormat("json");
        alipayConfig.setAlipayPublicKey(props.getAlipayPublicKey());
        alipayConfig.setCharset("UTF-8");
        alipayConfig.setSignType("RSA2");
        return new DefaultAlipayClient(alipayConfig);
    }
}
