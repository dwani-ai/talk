# Build stage
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
# Same-origin: UI and API on same host; nginx will proxy /v1 to backend
ENV VITE_API_URL=
RUN npm run build

# Run stage: nginx serves static + proxies /v1 to backend
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
