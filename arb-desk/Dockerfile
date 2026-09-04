# Stage 1: Build
FROM node:18-alpine AS builder

WORKDIR /app

# A URL do websocket injetada no momento do build
ARG VITE_WS_URL
ENV VITE_WS_URL=$VITE_WS_URL

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

# Stage 2: Serve
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html

# Expor porta 80 do Nginx
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
