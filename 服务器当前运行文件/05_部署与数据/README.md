# 部署配置与运行数据

当前容器使用的编排文件：

- CAET：`/opt/caet/docker-compose.yml`、`/opt/caet/docker-compose.override.yml`
- CabinLingo 主站：`/opt/cabinlingo/docker-compose.production.yml`、`/opt/cabinlingo/docker-compose.ports.yml`
- 课程测试：`/opt/cabinlingo/docker-compose.staging.yml`、`/opt/cabinlingo-course-test/compose.override.yml`
- 发音引擎：`/home/ubuntu/cabinlingo-pronunciation-engine/docker-compose.yml`

运维脚本分别位于 `/opt/caet/scripts`、`/opt/cabinlingo/scripts`、`/home/ubuntu/cabinlingo-pronunciation-engine/scripts`。

数据库、Redis、上传文件及证书仍由原有 Docker 卷或绑定目录承载。此处只记录位置，不复制或上传运行数据。
