# syntax=docker/dockerfile:1
FROM eclipse-temurin:25-jdk AS build
WORKDIR /src
COPY .mvn .mvn
COPY mvnw pom.xml ./
RUN --mount=type=cache,target=/root/.m2 ./mvnw -q -B dependency:go-offline
COPY src src
RUN --mount=type=cache,target=/root/.m2 ./mvnw -q -B package -DskipTests \
    && cp target/*.jar /app.jar

# Debian (not the Ubuntu-based Temurin runtime) so Chromium is a real package, not a snap:
# WebsitePreviewService uses it for website screenshot fallbacks.
FROM debian:trixie-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-25-jre-headless chromium fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    # Chromium's user-namespace sandbox is unavailable inside the container.
    && echo 'export CHROMIUM_FLAGS="$CHROMIUM_FLAGS --no-sandbox"' > /etc/chromium.d/zz-container \
    && useradd --system --create-home app
USER app
WORKDIR /app
COPY --from=build /app.jar app.jar
ENV SERVER_PORT=8080 SCREENSHOT_BROWSER_PATH=/usr/bin/chromium
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
