# 公网入口

| 位置 | 用途 | 依据 |
| --- | --- | --- |
| `/opt/caet/nginx/default.conf` | CAET Nginx 入口配置 | `caet-nginx` 容器绑定挂载 |
| `/opt/caet/frontend/dist` | CAET 已发布页面 | `caet-nginx` 容器绑定挂载 |
| `/opt/cabinlingo` | CabinLingo 入口容器的 Compose 工作目录 | `cabinlingo-nginx-1` 容器标签 |

证书位于 `/opt/caet/nginx/ssl`，本目录不建立证书链接，也不将证书同步到 GitHub。
