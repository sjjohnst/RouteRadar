# Stage 1 – build the Vite app
FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

# Stage 2 – serve with nginx
FROM nginx:alpine

# Copy compiled assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Replace the default nginx config with our custom one
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
