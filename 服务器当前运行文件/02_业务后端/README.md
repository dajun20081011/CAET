# 业务后端

| 位置 | 用途 | 依据 |
| --- | --- | --- |
| `/opt/caet/app` | CAET 后端部署源码 | `caet-api` 的 Compose 工作目录为 `/opt/caet` |
| `/opt/cabinlingo/backend-package/backend` | CabinLingo 后端部署源码 | `cabinlingo-api-1` 的 Compose 工作目录为 `/opt/cabinlingo` |

上述源码可能晚于容器镜像的构建时间。需核对镜像构建记录后，才能确认每个源码文件与运行镜像完全一致。
