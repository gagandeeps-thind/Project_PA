# Admin console: type-checked Vite build served as static files by an unprivileged nginx.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.29-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=infra admin-nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
