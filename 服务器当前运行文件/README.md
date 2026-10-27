# 当前运行文件分类

核对时间：2026-10-27（北京时间）。GitHub 中的此目录是从服务器提取的源码与配置快照；服务器上的同名中文导航用链接指向原位置。修改这里的文件不会自动部署，运行路径未改变。

| 分类 | 内容 | 对应运行实例 |
| --- | --- | --- |
| [01_公网入口](01_公网入口/README.md) | Nginx 配置和已发布页面 | `caet-nginx`、`cabinlingo-nginx-1` |
| [02_业务后端](02_业务后端/README.md) | CAET 与 CabinLingo 的部署源码 | `caet-api`、`cabinlingo-api-1` |
| [03_前端页面](03_前端页面/README.md) | CabinLingo 前端工程 | `cabinlingo-nginx-1` |
| [04_测试与发音](04_测试与发音/README.md) | 课程测试环境和发音引擎 | `cabinlingo-course-test-*`、`cabinlingo-pronunciation-engine` |
| [05_部署与数据](05_部署与数据/README.md) | Compose、脚本、数据位置说明 | 多个容器 |

容器中运行的程序来自已构建镜像，服务器上的源码可能与镜像内版本不同。此导航记录的是当前容器使用的部署目录、绑定挂载及相关源码位置，不应视为镜像内容的逐字节副本。

同步 GitHub 时仅选择代码、文档和可公开的配置模板；`.env`、私钥、证书、数据库、上传文件、备份和模型文件不上传。
