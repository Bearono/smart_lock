FROM node:24-bookworm-slim AS build
WORKDIR /src
COPY FE_smart_lock/smartlock/package*.json ./
RUN npm ci
COPY FE_smart_lock/smartlock/ ./
RUN npm run build
FROM nginx:stable-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
