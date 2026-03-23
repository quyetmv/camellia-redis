package lab.camellia.dashboard;

import com.netease.nim.camellia.dashboard.CamelliaDashboardScanBase;
import com.netease.nim.camellia.dashboard.springboot.EnableCamelliaDashboard;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;

@SpringBootApplication
@EnableCamelliaDashboard
@ComponentScan(basePackageClasses = {CamelliaDashboardScanBase.class, CamelliaDashboardAppApplication.class})
public class CamelliaDashboardAppApplication {

    public static void main(String[] args) {
        SpringApplication.run(CamelliaDashboardAppApplication.class, args);
    }
}
