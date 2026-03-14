# 给网页 AI 的补充约束说明

这份补充说明是对 [frontend_handoff_fake_grasp_console.md](/home/robot/project/sort_trash/docs/frontend_handoff_fake_grasp_console.md) 的收紧和落地约束。

如果你要继续为 `sort_trash` 做网页前端，请不要只按“静态控制台 demo”实现，必须满足下面这些真实工程约束。

## 1. 目标不是静态控制台，而是真实可控的本地操作台

这个前端的目标不是展示一个看起来像工业控制台的页面，而是：

- 真正显示当前相机和检测状态
- 真正显示当前机械臂连接状态
- 真正执行 fake grasp 流程
- 真正记录 `home/work/standby`
- 真正记录 `bottle/cup` 回收点
- 真正能启动 / 停止 follow 和 fake grasp

所以不能只做本地 `useState` 模拟数据，必须基于真实后端接口。

## 2. 后端必须是“单服务统一持有资源”，不能把 CLI 脚本当主控

当前项目已有很多 CLI 脚本，例如：

- `scripts/control/run_fake_grasp_cycle.py`
- `scripts/control/hover_detected_target.py`
- `scripts/control/record_task_poses.py`
- `scripts/control/record_drop_poses.py`
- `scripts/vision/detect_realsense_yolo_xyz.py`

这些脚本适合人工在终端里运行，但**不适合网页后端直接每次 `subprocess` 启多个实例来驱动系统**。

必须改成下面这个架构：

- 一个常驻后端进程
- 后端进程统一持有：
  - RealSense 相机
  - YOLO 模型
  - 机械臂连接
  - 当前检测状态
  - 当前任务状态
- 前端只能通过 API 与后端交互

禁止做法：

- 每个按钮都起一个新的 Python 子进程
- “开始检测”起一个脚本，“开始 follow”再起另一个脚本
- 多个进程同时抢占相机
- 多个进程同时抢占 `can0`

## 3. 必须有任务互斥和状态机

当前系统不允许多个控制流程同时运行。

后端必须维护统一状态机，至少要有：

- `idle`
- `detecting`
- `following`
- `running_fake_cycle`
- `recording_pose`
- `error`

同时需要一个 `busy` 标志或等价机制。

规则：

- `running_fake_cycle` 时，不能再启动 follow
- `following` 时，不能再启动 fake cycle
- 正在记录 pose 时，不能同时运行其他运动流程
- 相机或机械臂资源异常时，状态必须切到 `error`

前端按钮必须根据状态机做禁用处理，而不是随时都可点。

## 4. 必须接入真实配置文件，而不是前端硬编码

当前项目真实配置来源是这些文件：

- `config/task_poses.yaml`
- `config/drop_poses.yaml`
- `data/calib_run_02/calibration_result.yaml`

前端和后端必须读取这些真实文件对应的数据，而不是自己维护一份副本。

### 4.1 task poses

这些是完整六维位姿：

- `home`
- `work`
- `standby`

来源：

- `scripts/control/record_task_poses.py`
- `config/task_poses.yaml`

### 4.2 drop poses

这些只记录回收盒中心点的 XY：

- `bottle`
- `cup`

来源：

- `scripts/control/record_drop_poses.py`
- `config/drop_poses.yaml`

### 4.3 calibration

检测目标的 `camera_xyz` 转 `base_xyz` 时，必须使用：

- `data/calib_run_02/calibration_result.yaml`

## 5. 当前真实运行参数必须纳入后端运行态

不要把这些值只写在前端页面上，必须进入后端运行态并真实生效：

- `hover_height_m`
- `grasp_z_offset_m`
- `drop_hover_z_m`
- `drop_z_m`
- `follow_rate_hz`
- `base_offset_m`
- `pose_rpy_deg`
- `target_labels`

前端只负责修改它们，后端负责真正应用。

## 6. 当前真实默认值

基于当前项目状态，网页后端默认值应当与现在的控制脚本一致：

- `pose_rpy_deg = [90, -90, 0]`
- `hover_height_m = 0.20`
- `grasp_z_offset_m = 0.18`
- `drop_hover_z_m = 0.25`
- `drop_z_m = 0.15`
- `follow_rate_hz = 10`

这些值不是随便猜的，是当前现场联调后得到的经验默认值。

## 7. 必须保留安全规则

当前项目中已经有统一安全规则：

- 任何执行位姿的目标 `z` 必须满足 `z >= 0.10 m`

如果不满足：

- 后端拒绝执行
- 返回明确错误信息
- 前端显示红色安全警告

禁止前端绕过这个规则。

## 8. 必须显式处理 CAN 状态

当前系统里，`can0` 会掉线或 `DOWN`，这是现场真实问题，不是边缘情况。

前端必须明确展示：

- `can0` 是否 `UP`
- 是否能正常读到机械臂状态

如果 `can0` 不可用：

- 所有运动按钮应禁用
- 页面明确提示先执行：

```bash
cd /home/robot/project/sort_trash/pyAgxArm/pyAgxArm/scripts/ubuntu
sudo bash can_activate.sh can0 1000000
```

如果做高级一点，也可以后端提供“尝试激活 can0”的按钮，但这不是第一版必须项。

## 9. 视频流必须来自后端统一检测循环

前端不能自己直接开摄像头。

应该由后端：

- 持有 D435
- 跑 YOLO
- 生成带框图像
- 通过 MJPEG 或 WebSocket 发给前端

前端只负责显示：

- 当前实时画面
- 当前检测框
- 当前主目标信息
- `camera_xyz`
- `base_xyz`

## 10. Fake Grasp 流程必须和现有脚本一致

当前 fake 流程是：

1. `home`
2. `work`
3. `target_hover`
4. `pregrasp_10cm`
5. `[FAKE GRASP]`
6. `target_retreat`
7. `standby`
8. `drop_hover`
9. `drop_down`
10. `[FAKE RELEASE]`
11. `drop_retreat`
12. `home`

前端不应该发明新的流程名称或改变流程顺序。

前端应该能显示当前步骤高亮，但真实执行必须由后端控制。

## 11. 按钮设计必须保守

建议保留这些按钮：

- `Move Home`
- `Move Work`
- `Move Standby`
- `Record Home`
- `Record Work`
- `Record Standby`
- `Record Bottle Drop`
- `Record Cup Drop`
- `Start Detection Preview`
- `Start Follow`
- `Stop Follow`
- `Run One Fake Grasp`
- `Stop Current Task`

不建议第一版暴露：

- 底层 CAN 发包参数
- `send-order`
- `mode-resend`
- 内部 debug 参数

这些应由后端固定。

## 12. 错误返回必须结构化

所有 API 都应采用统一响应结构，例如：

```json
{
  "ok": false,
  "code": "MIN_Z_BLOCKED",
  "message": "Target z is below the minimum allowed z.",
  "data": {
    "target_z_m": 0.069,
    "min_allowed_z_m": 0.10
  }
}
```

这样前端可以明确区分：

- 安全拦截
- CAN 未连接
- 相机未就绪
- 模型未加载
- 任务忙
- 配置缺失

## 13. 建议先做 MVP，不要一次做成“大平台”

第一版先完成这 7 件事就够了：

1. 状态页
2. 实时视频流
3. 当前检测目标信息
4. 记录 `home/work/standby`
5. 记录 `bottle/cup` 回收点
6. 启动一次 fake grasp
7. 启动 / 停止 follow

不要第一版就试图做：

- 用户权限系统
- 多机械臂管理
- 历史任务数据库
- 云端部署
- 复杂权限控制

## 14. 推荐开发顺序

建议网页 AI 按下面顺序实现：

1. 建好 FastAPI 常驻服务骨架
2. 接入 `GET /api/status`
3. 接入 `GET /api/robot/state`
4. 接入 `GET /api/detection/state`
5. 接入视频流
6. 接入 pose 记录接口
7. 接入 fake grasp 启动接口
8. 最后再做前端精细样式和交互

## 15. 最后要求

请把这个项目当作：

- 一个**本地现场操作台**
- 一个**真实硬件控制界面**
- 一个**单后端服务 + 前端控制台**

不要把它实现成“UI 很像工业控制台，但后端只是模拟状态”的 demo。
