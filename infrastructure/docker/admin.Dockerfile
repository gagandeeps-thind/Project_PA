# Admin console: type-checked Vite build served as static files by an unprivileged nginx.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
# Without the API URL the bundle only shows a configuration error, so stop the build instead.
RUN test -n "$VITE_API_BASE_URL" || { echo "VITE_API_BASE_URL build arg is required" >&2; exit 1; }
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.29-alpine
ARG VITE_API_BASE_URL
# The only origin the CSP lets the console call. The image renders the template with it at start.
ENV API_ORIGIN=${VITE_API_BASE_URL}
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=infra admin-nginx.conf /etc/nginx/templates/default.conf.template
EXPOSE 8080
