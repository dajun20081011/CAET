# 测试与发音

| 位置 | 用途 | 对应容器 |
| --- | --- | --- |
| `/opt/cabinlingo/docker-compose.staging.yml` | 课程测试环境编排 | `cabinlingo-course-test-*` |
| `/opt/cabinlingo-course-test/compose.override.yml` | 课程测试环境覆盖配置 | `cabinlingo-course-test-*` |
| `/home/ubuntu/cabinlingo-pronunciation-engine/app` | 发音引擎源码 | `cabinlingo-pronunciation-engine` |
| `/home/ubuntu/cabinlingo-pronunciation-engine/docker-compose.yml` | 发音引擎编排 | `cabinlingo-pronunciation-engine` |

发音模型、运行数据和环境变量留在原位置，不纳入 GitHub 同步。
