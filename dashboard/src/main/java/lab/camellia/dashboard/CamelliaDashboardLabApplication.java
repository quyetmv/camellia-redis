package lab.camellia.dashboard;

import com.netease.nim.camellia.dashboard.springboot.EnableCamelliaDashboard;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@EnableCamelliaDashboard
public class CamelliaDashboardLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(CamelliaDashboardLabApplication.class, args);
    }
}
