# sort_trash 前端交接文档（Fake Grasp Console）

## 1. 项目目标

这个前端不是通用机器人平台，而是一个**现场操作台**，用于让非开发人员也能操作当前项目的 fake grasp 流程。

当前项目的目标流程是：

1. 打开相机并识别目标（`bottle` / `cup`）
2. 通过深度相机得到目标三维位置
3. 通过手眼标定换算到机械臂基坐标
4. 执行一套 fake grasp 流程：
   - `home`
   - `work`
   - `target_hover`
   - `pregrasp_10cm`
   - `[FAKE GRASP]`
   - `target_retreat`
   - `standby`
   - `drop_hover`
   - `drop_down`
   - `[FAKE RELEASE]`
   - `drop_retreat`
   - `home`

这个前端的重点不是炫酷视觉，而是：

- 让小白知道当前系统状态
- 能看见实时检测画面
- 能记录关键位姿
- 能记录回收盒中心点
- 能安全地启动 / 停止 fake grasp 流程
- 能调少量运行参数（如 hover 高度、offset）

## 2. 当前系统事实

### 2.1 现有硬件/能力

- 机械臂：NERO
- 相机：Intel RealSense D435
- 控制方式：Ubuntu 本机 + `pyAgxArm` + CAN
- 检测模型：YOLO
- 手眼标定：已经完成并有可用标定文件

### 2.2 当前已存在的本地脚本

- `scripts/vision/detect_realsense_yolo_xyz.py`
  - 检测 + 深度 + 输出 `camera_xyz` / `base_xyz`
- `scripts/control/hover_detected_target.py`
  - 目标上方悬停 / 连续跟随
- `scripts/control/record_task_poses.py`
  - 记录 `home` / `work` / `standby`
- `scripts/control/record_drop_poses.py`
  - 记录回收盒中心 `x/y`
- `scripts/control/run_fake_grasp_cycle.py`
  - 跑完整 fake grasp 流程

### 2.3 当前默认行为

- 默认姿态：`rx=90, ry=-90, rz=0`
- fake 流程中的预抓取位：当前以“物体上方 10cm”为目标语义
- drop 放下高度：`z=0.15m`
- 所有主要位姿控制入口都有安全限制：
  - **末端目标 `z >= 0.10m`**

## 3. 前端总体设计

## 3.1 设计原则

- 第一版做成一个本地 Web 操作台
- 前端只负责显示和发指令
- 后端负责：
  - 相机
  - YOLO
  - CAN
  - 机械臂状态读取
  - fake grasp 流程调度
- 前端**不要直接运行多个脚本抢占资源**
- 前端**不要直接处理机器人 SDK**

## 3.2 推荐架构

- 前端：React + Vite
- 后端：FastAPI
- 实时状态：
  - 第一版可用 HTTP 轮询
  - 第二版可加 WebSocket
- 视频流：
  - 第一版推荐 MJPEG

## 4. 页面草图与分区

建议做成一个单页控制台，分成 5 个区域。

---

## 4.1 顶部状态条

用途：让操作者一眼知道当前系统是否可用。

显示内容：

- CAN 状态：`UP / DOWN`
- 机械臂连接状态：`connected / disconnected`
- 相机状态：`ready / not ready`
- 模型状态：`loaded / not loaded`
- 标定文件：当前使用的文件名
- 当前任务状态：`idle / detecting / following / running_fake_cycle / error`
- 安全状态：
  - `min_z_m = 0.10`

推荐展示形式：

- 左侧：硬件状态标签
- 中间：当前模式
- 右侧：当前使用的配置名/标定文件

---

## 4.2 左侧视频与检测区

用途：展示现场画面和检测结果。

内容：

- 实时视频窗口
- 当前检测框
- 当前主目标类别
- 当前置信度
- `camera_xyz_m`
- `base_xyz_m`
- 当前 hover / pregrasp / drop 的位置摘要

建议布局：

- 上方：大视频窗
- 下方：目标信息卡片

建议展示字段：

- `target class`
- `target confidence`
- `camera_xyz`
- `base_xyz`
- `target_hover xyz`
- `pregrasp xyz`
- `drop_hover xyz`

---

## 4.3 中间流程控制区

用途：让操作者直接执行流程。

按钮建议：

- `Move Home`
- `Move Work`
- `Move Standby`
- `Start Detection Preview`
- `Run One Fake Grasp`
- `Start Follow`
- `Stop Follow`
- `Stop Current Task`

流程进度显示：

- `home`
- `work`
- `target_hover`
- `pregrasp_10cm`
- `FAKE GRASP`
- `target_retreat`
- `standby`
- `drop_hover`
- `drop_down`
- `FAKE RELEASE`
- `drop_retreat`
- `return_home`

建议做成一个竖直步骤条，高亮当前步骤。

---

## 4.4 右侧参数区

用途：暴露少量小白可调参数。

第一版建议允许调整：

- `hover_height_m`
- `grasp_z_offset_m`
- `drop_hover_z_m`
- `drop_z_m`
- `follow_rate_hz`
- `base_offset_x`
- `base_offset_y`
- `base_offset_z`
- 目标类别：
  - `bottle`
  - `cup`
  - `both`

建议 UI：

- 数字输入框
- 小步加减按钮
- “应用到运行时”按钮

---

## 4.5 底部记录区

用途：记录流程位姿和回收点。

### A. Task Poses

- `Record Home`
- `Record Work`
- `Record Standby`
- 查看当前记录值

### B. Drop Poses

- `Record Bottle Drop XY`
- `Record Cup Drop XY`
- 查看当前记录值

已有记录时，前端必须二次确认是否覆盖。

---

## 5. 页面交互流程

## 5.1 首次进入页面

前端先调用：

- `GET /api/status`
- `GET /api/task-poses`
- `GET /api/drop-poses`
- `GET /api/runtime-config`

如果存在未配置项，要明确提示：

- 缺少 `home`
- 缺少 `work`
- 缺少 `standby`
- 缺少 `bottle` 回收点
- 缺少 `cup` 回收点

## 5.2 操作员标准流程

1. 进入页面
2. 检查状态区全部为绿色
3. 必要时记录 `home/work/standby`
4. 必要时记录 `bottle/cup` 回收点
5. 看视频，确认检测正常
6. 调整 hover / offset 参数
7. 点击 `Run One Fake Grasp`
8. 观察步骤条执行过程

## 6. API 设计

建议后端统一加前缀：

- `/api/...`

所有返回统一建议格式：

```json
{
  "ok": true,
  "data": {},
  "message": ""
}
```

错误时：

```json
{
  "ok": false,
  "message": "error reason"
}
```

---

## 6.1 系统状态

### `GET /api/status`

用途：获取整体运行状态。

返回示例：

```json
{
  "ok": true,
  "data": {
    "can_up": true,
    "robot_connected": true,
    "camera_ready": true,
    "model_ready": true,
    "busy": false,
    "current_mode": "idle",
    "calibration_file": "data/calib_run_02/calibration_result.yaml",
    "safety": {
      "min_z_m": 0.1
    }
  },
  "message": ""
}
```

---

## 6.2 机械臂状态

### `GET /api/robot/state`

返回示例：

```json
{
  "ok": true,
  "data": {
    "flange_pose": [0.0, -0.0235, 0.718, 1.33, 1.57, -0.24],
    "joint_angles": [0.1, 0.2, 0.3, 0.4, 0.0, 0.0, 0.0],
    "enabled_joints": [true, true, true, true, true, true, true],
    "ctrl_mode": "CAN_CTRL"
  },
  "message": ""
}
```

---

## 6.3 检测状态

### `GET /api/detection/state`

返回当前最佳目标和对应位姿。

返回示例：

```json
{
  "ok": true,
  "data": {
    "target": {
      "class_name": "bottle",
      "target_name": "bottle",
      "confidence": 0.67,
      "camera_xyz_m": [0.12, -0.03, 0.85],
      "base_xyz_m": [-0.34, 0.18, 0.06]
    },
    "poses": {
      "target_hover": [-0.34, 0.18, 0.26, 1.57, -1.57, 0.0],
      "pregrasp_10cm": [-0.34, 0.18, 0.16, 1.57, -1.57, 0.0],
      "drop_hover": [-0.30, -0.37, 0.25, 1.57, -1.57, 0.0],
      "drop_down": [-0.30, -0.37, 0.15, 1.57, -1.57, 0.0]
    }
  },
  "message": ""
}
```

---

## 6.4 视频流

### `GET /api/video.mjpg`

返回 MJPEG 视频流。

前端直接用：

```html
<img src="/api/video.mjpg" />
```

如果后端不方便做 MJPEG，也可以改成：

- `GET /api/video/frame` 返回 JPEG
- 前端轮询

但第一版 MJPEG 更简单。

---

## 6.5 运行时配置

### `GET /api/runtime-config`

获取当前运行参数。

返回示例：

```json
{
  "ok": true,
  "data": {
    "hover_height_m": 0.2,
    "grasp_z_offset_m": 0.18,
    "drop_hover_z_m": 0.25,
    "drop_z_m": 0.15,
    "follow_rate_hz": 10,
    "base_offset_m": [-0.1, 0.0, 0.0],
    "pose_rpy_deg": [90, -90, 0],
    "target_labels": ["bottle", "cup"]
  },
  "message": ""
}
```

### `POST /api/runtime-config`

用途：更新运行参数。

请求示例：

```json
{
  "hover_height_m": 0.2,
  "grasp_z_offset_m": 0.18,
  "drop_hover_z_m": 0.25,
  "drop_z_m": 0.15,
  "follow_rate_hz": 10,
  "base_offset_m": [-0.1, 0.0, 0.0],
  "pose_rpy_deg": [90, -90, 0],
  "target_labels": ["bottle", "cup"]
}
```

返回示例：

```json
{
  "ok": true,
  "data": {
    "updated": true
  },
  "message": "runtime config updated"
}
```

---

## 6.6 记录流程位姿

### `GET /api/task-poses`

返回示例：

```json
{
  "ok": true,
  "data": {
    "home": {
      "pose": [0.0, -0.0235, 0.718, 1.33, 1.57, -0.24],
      "updated_at": "2026-03-13T19:28:58+08:00"
    },
    "work": {
      "pose": [-0.28, -0.02, 0.43, 1.64, -0.90, -0.04],
      "updated_at": "2026-03-13T19:31:47+08:00"
    },
    "standby": {
      "pose": [-0.13, -0.28, 0.28, 1.76, -1.26, 1.39],
      "updated_at": "2026-03-13T19:32:24+08:00"
    }
  },
  "message": ""
}
```

### `POST /api/task-poses/record`

请求：

```json
{
  "name": "home",
  "overwrite": false
}
```

返回：

```json
{
  "ok": true,
  "data": {
    "name": "home",
    "pose": [0.0, -0.0235, 0.718, 1.33, 1.57, -0.24],
    "overwritten": false
  },
  "message": "task pose recorded"
}
```

如果已存在且 `overwrite=false`：

```json
{
  "ok": false,
  "data": {
    "exists": true,
    "current": {
      "pose": [0.0, -0.0235, 0.718, 1.33, 1.57, -0.24]
    }
  },
  "message": "task pose already exists"
}
```

---

## 6.7 记录回收点

### `GET /api/drop-poses`

返回示例：

```json
{
  "ok": true,
  "data": {
    "bottle": {
      "xy": [-0.308629, -0.371221],
      "updated_at": "2026-03-13T19:18:03+08:00"
    },
    "cup": {
      "xy": [-0.058509, -0.34524],
      "updated_at": "2026-03-13T19:18:31+08:00"
    }
  },
  "message": ""
}
```

### `POST /api/drop-poses/record`

请求：

```json
{
  "name": "bottle",
  "overwrite": false
}
```

返回：

```json
{
  "ok": true,
  "data": {
    "name": "bottle",
    "xy": [-0.308629, -0.371221],
    "overwritten": false
  },
  "message": "drop pose recorded"
}
```

---

## 6.8 基础动作接口

### `POST /api/robot/move-home`
### `POST /api/robot/move-work`
### `POST /api/robot/move-standby`

请求体可以为空：

```json
{}
```

返回示例：

```json
{
  "ok": true,
  "data": {
    "accepted": true
  },
  "message": "move request accepted"
}
```

---

## 6.9 执行一次 fake grasp

### `POST /api/workflow/fake-grasp`

请求示例：

```json
{
  "hover_height_m": 0.2,
  "grasp_z_offset_m": 0.18,
  "drop_hover_z_m": 0.25,
  "drop_z_m": 0.15,
  "base_offset_m": [-0.1, 0.0, 0.0],
  "pose_rpy_deg": [90, -90, 0],
  "target_labels": ["bottle", "cup"]
}
```

返回示例：

```json
{
  "ok": true,
  "data": {
    "task_id": "fake-grasp-20260313-001",
    "accepted": true
  },
  "message": "fake grasp workflow started"
}
```

---

## 6.10 跟随模式

### `POST /api/follow/start`

请求：

```json
{
  "follow_rate_hz": 10,
  "hover_height_m": 0.2,
  "base_offset_m": [-0.1, 0.0, 0.0],
  "pose_rpy_deg": [90, -90, 0],
  "target_labels": ["bottle", "cup"]
}
```

### `POST /api/follow/stop`

请求：

```json
{}
```

---

## 6.11 停止当前任务

### `POST /api/workflow/stop`

停止当前 follow 或 fake grasp 任务。

返回示例：

```json
{
  "ok": true,
  "data": {
    "stopped": true
  },
  "message": "current workflow stopped"
}
```

## 7. 后端目录结构建议

建议不要直接在前端里调用现有脚本。  
推荐做一个统一的本地控制服务。

建议目录结构：

```text
sort_trash/
  frontend/
    package.json
    vite.config.ts
    src/
      main.tsx
      App.tsx
      api/
        client.ts
        status.ts
        robot.ts
        detection.ts
        workflow.ts
        config.ts
      components/
        StatusBar.tsx
        VideoPanel.tsx
        DetectionInfo.tsx
        RuntimeConfigPanel.tsx
        TaskPosePanel.tsx
        DropPosePanel.tsx
        WorkflowPanel.tsx
        ProgressTimeline.tsx
      pages/
        ConsolePage.tsx
      types/
        api.ts
      styles/
        app.css

  backend/
    app/
      main.py
      api/
        status.py
        robot.py
        detection.py
        workflow.py
        config.py
        poses.py
        stream.py
      services/
        robot_service.py
        camera_service.py
        detection_service.py
        workflow_service.py
        config_service.py
        pose_record_service.py
      models/
        schemas.py
      core/
        state.py
        safety.py
        paths.py
      static/
      templates/
```

## 8. 前端目录结构建议

如果只做前端独立仓，也可以是：

```text
frontend/
  src/
    api/
    components/
    hooks/
    pages/
    store/
    types/
    styles/
```

建议组件拆分：

- `StatusBar`
- `VideoPanel`
- `DetectionPanel`
- `PoseRecordPanel`
- `DropRecordPanel`
- `WorkflowControls`
- `RuntimeTuningPanel`
- `SafetyBanner`

## 9. 后端状态机建议

后端应该维护一个全局状态机，避免多个动作同时执行。

建议状态：

- `idle`
- `camera_ready`
- `detecting`
- `following`
- `running_fake_grasp`
- `recording_pose`
- `error`

建议规则：

- `running_fake_grasp` 时不能再启动第二个 fake grasp
- `following` 时不能再启动 fake grasp，除非先停止 follow
- `recording_pose` 时不能同时发运动命令

## 10. 安全要求

前端必须显式提示这些安全规则：

- 当前项目是 fake grasp，不是真实夹爪抓取
- 所有主要位姿目标都受 `z >= 0.10m` 限制
- 如果目标低于安全线，后端会拒绝执行
- 覆盖 `home/work/standby` 或 `drop poses` 时必须二次确认

## 11. 建议的第一版功能边界

第一版只做：

- 看状态
- 看视频
- 看检测
- 记录 `home/work/standby`
- 记录 `bottle/cup`
- 调少量参数
- 执行一次 fake grasp
- 启停 follow

第一版不要做：

- 用户登录
- 多机器人支持
- 历史任务系统
- 复杂权限模型
- 真正的灵巧手控制
- 大而全的参数编辑器

## 12. 对做网页的 AI 的明确要求

请优先实现：

1. 单页控制台
2. 本地运行
3. 中文界面
4. 明确状态提示
5. 少量但稳定的按钮
6. API 调用失败时清楚提示
7. 不要把页面做成花哨 dashboard
8. 优先可操作性、状态清晰度和安全感

UI 风格建议：

- 偏工业控制台
- 清晰、克制
- 信息分区明确
- 危险操作要用确认弹窗
- 不要做过多动画

## 13. 当前默认运行命令（给后端开发参考）

### 视觉悬停

```bash
python scripts/control/hover_detected_target.py \
  --camera-serial 241222074755 \
  --allow-cpu \
  --calibration-file ./data/calib_run_02/calibration_result.yaml \
  --follow-rate-hz 10 \
  --hover-height-m 0.20 \
  --go
```

### fake grasp

```bash
python scripts/control/run_fake_grasp_cycle.py \
  --camera-serial 241222074755 \
  --allow-cpu \
  --calibration-file ./data/calib_run_02/calibration_result.yaml \
  --hover-height-m 0.20 \
  --drop-z-m 0.15 \
  --drop-hover-z-m 0.25 \
  --pose-rpy-deg 90 -90 0 \
  --go
```

---

这份文档的用途是：让专门做网页的 AI 或工程师，直接按这里的页面结构和 API 约束开始实现，不需要再反向理解机器人脚本细节。
