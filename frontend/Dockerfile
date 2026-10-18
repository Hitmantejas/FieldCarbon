# The frontend service: the built React app, plus a proxy that forwards /api to the backend service.
# The browser keeps talking to one origin, so the app needs no CORS settings and the answer stream works as before.
# BACKEND_URL (for example https://fieldcarbon-backend-xxxx-uc.a.run.app) is set when the service is deployed.

FROM node:24-slim AS build
WORKDIR /ui
COPY package.json package-lock.json ./
RUN npm ci
COPY . ./
RUN npm run build

FROM nginxinc/nginx-unprivileged:stable-alpine
ENV PORT=8080 NGINX_ENVSUBST_FILTER='^(PORT|BACKEND_URL)$'
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /ui/dist/ /usr/share/nginx/html/
