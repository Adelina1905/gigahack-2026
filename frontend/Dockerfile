# syntax=docker/dockerfile:1
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .
# Same-origin API: nginx below proxies /api to the backend. The shell value
# overrides the committed frontend/.env.
ENV VITE_API_BASE_URL=/api VITE_USE_MOCK=false
RUN npm run build

FROM nginx:1.29-alpine
COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /src/dist /usr/share/nginx/html
ENV BACKEND_URL=http://backend:8080
EXPOSE 80
