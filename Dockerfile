# ============================================================
# CAET 前端镜像：Node 构建 Vue3 → Nginx 托管静态 + 反代 /api
# 构建上下文为仓库根目录（见 .dockerignore 排除 caet-backend）。
# ============================================================
# ---- 构建阶段 ----
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---- 运行阶段 ----
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.caet.conf /etc/nginx/conf.d/default.conf
EXPOSE 80 443
CMD ["nginx", "-g", "daemon off;"]
