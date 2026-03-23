FROM maven:3.9.9-eclipse-temurin-21 AS build
WORKDIR /src

COPY camellia-ref ./camellia-ref
COPY camellia-redis/dashboard-app ./dashboard-app

RUN cd camellia-ref && mvn -q -DskipTests -pl camellia-admin/camellia-dashboard-spring-boot-starter -am install
RUN cd dashboard-app && mvn -q -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /src/dashboard-app/target/camellia-dashboard-app-0.1.0.jar /app/app.jar

EXPOSE 8080
ENTRYPOINT ["java", "--add-opens=java.base/java.lang=ALL-UNNAMED", "--add-opens=java.base/java.lang.reflect=ALL-UNNAMED", "-jar", "/app/app.jar"]
