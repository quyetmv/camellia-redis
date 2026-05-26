package com.netease.nim.camellia.dashboard.conf;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties({CamelliaDashboardConfiguration.class})
public class CamelliaDashboardConfigurationStarter {

    @Bean
    public DashboardProperties dashboardProperties(CamelliaDashboardConfiguration configuration) {
        DashboardProperties dashboardProperties = new DashboardProperties();
        dashboardProperties.setLocalCacheExpireSeconds(configuration.getLocalCacheExpireSeconds());
        dashboardProperties.setStatsExpireSeconds(configuration.getStatsExpireSeconds());
        dashboardProperties.setStatsKeyExpireHours(configuration.getStatsKeyExpireHours());
        dashboardProperties.setDaoCacheExpireSeconds(configuration.getDaoCacheExpireSeconds());
        return dashboardProperties;
    }
}
