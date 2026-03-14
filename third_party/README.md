# 第三方仓库说明

更新时间: 2026-03-09

当前目录用于存放“机械臂 + 灵巧手”联调用到的官方仓库。

## 已下载仓库

### pyAgxArm

路径:

- `C:\Users\33590\Desktop\RA项目\控制机械臂垃圾分类项目\第三方仓库\pyAgxArm`

来源:

- `https://github.com/agilexrobotics/pyAgxArm.git`

用途:

- AgileX 机械臂 Python SDK
- 用于控制 NERO 机械臂
- 适合后续写 Python 抓取脚本

当前提交:

- `b4fe1e7`

### agx_arm_ros

路径:

- `C:\Users\33590\Desktop\RA项目\控制机械臂垃圾分类项目\第三方仓库\agx_arm_ros`

来源:

- `https://github.com/agilexrobotics/agx_arm_ros.git`

用途:

- AgileX 机械臂 ROS2 驱动与描述文件
- 适合后续接 ROS2 / MoveIt / 规划控制

当前提交:

- `1c1d90e`

### Omnihand-2025-SDK

路径:

- `C:\Users\33590\Desktop\RA项目\控制机械臂垃圾分类项目\第三方仓库\Omnihand-2025-SDK`

来源:

- `https://github.com/AgibotTech/Omnihand-2025-SDK.git`

用途:

- 智元 OmniHand 灵巧手 SDK
- 用于灵巧手二次开发和联调

当前提交:

- `bcbccf4`

## 建议使用顺序

如果目标是“机械臂抓取 + 灵巧手配合抓取”，建议优先看:

1. `pyAgxArm`
2. `Omnihand-2025-SDK`
3. `agx_arm_ros`

说明:

- 先用 Python 跑通单机控制最直接
- 跑通后再决定是否切到 ROS2 做系统集成
