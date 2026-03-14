# sort_trash

这个仓库现在适合按“小步验证”推进，不适合一上来追求整套抓取闭环。

建议顺序：

1. 先确认 conda 环境和 Python 依赖
2. 再确认 YOLO 模型和纯视觉推理
3. 再确认 RealSense 取流
4. 再做固定相机标定
5. 最后才接 NERO 和 OmniHand

建议在Ubuntu22.04操作系统下运行。
如果是在WSL2中，需要将windows宿主机的USB接口Attach到虚拟机，以BUSID为2-2为例：
```bash
usbipd list
usbipd bind --busid 2-2
usbipd attach --wsl --busid 2-2
```
检查state，若为Attached则成功
```bash
usbipd list
```

## 项目架构

下面是这个仓库当前最重要的目录树。  
这里只列“项目真正会用到的核心部分”，不把第三方库和大量资料文件全部展开。

```text
sort_trash/
├── README.md                           # 项目主说明，记录当前推荐流程和命令
├── environment/
│   ├── grasp-gpu.yml                   # conda 环境定义
│   └── setup_grasp_gpu.sh              # 一键创建/更新环境并安装本地 pyAgxArm
├── config/
│   ├── sort_trash_pipeline.example.yaml# 总控示例配置
│   ├── calibration.identity.yaml       # 无真机时使用的占位标定文件
│   ├── task_poses.yaml                 # 记录 home/work/standby 等流程位姿
│   ├── drop_poses.yaml                 # 记录 bottle/cup 回收盒中心点
│   └── robot_workspace.yaml            # 机械臂工作空间约束和已知安全区域
├── data/
│   └── calib_run_02/                   # 当前可用的一套手眼标定结果和验证结果
├── assets/
│   └── calibration_boards/             # 标定板 PDF/PNG，例如标准 ChArUco 板
├── docs/
│   ├── project_intro_for_students.md   # 面向高中生的项目科普介绍
│   ├── frontend_handoff_fake_grasp_console.md
│   │                                   # 给前端/网页 AI 的主交接文档
│   └── frontend_handoff_web_ai_addendum.md
│                                       # 给网页 AI 的补充实现约束
├── scripts/
│   ├── _local_sdk.py                   # 统一优先加载当前仓库里的 pyAgxArm
│   ├── dev/
│   │   └── check_setup.py              # 环境自检：依赖、模型、相机、配置是否正常
│   ├── vision/
│   │   ├── view_realsense_stream.py    # 只看 D435 彩色/深度画面
│   │   ├── detect_realsense_yolo_2d.py # D435 + YOLO 2D 检测
│   │   ├── detect_realsense_yolo_xyz.py# D435 + YOLO + 深度，输出 camera/base XYZ
│   │   ├── yolo_detect_realsense.py    # 更早期的 RealSense + YOLO 检测脚本
│   │   ├── train_yolo11_trash.py       # 训练垃圾分类 YOLO 模型
│   │   └── _common.py                  # 视觉脚本共用的相机/深度/绘图工具函数
│   ├── calibration/
│   │   ├── capture_eye_to_hand.py      # 采集相机图像和机械臂位姿做手眼标定
│   │   ├── solve_eye_to_hand.py        # 计算 T_base_camera 标定结果
│   │   ├── verify_eye_to_hand.py       # 验证标定误差是否可接受
│   │   ├── generate_charuco_board.py   # 生成标准 ChArUco 标定板
│   │   └── _common.py                  # 标定流程共用的角点检测和 PnP 工具
│   └── control/
│       ├── _safety.py                  # 统一安全规则，例如末端 z >= 0.10m
│       ├── move_flange_pose.py         # 机械臂笛卡尔位姿调试工具
│       ├── hover_detected_target.py    # 检测目标后悬停到目标上方，可单次或连续跟随
│       ├── run_fake_grasp_cycle.py     # 当前最重要的完整 fake grasp 流程脚本
│       ├── record_task_poses.py        # 记录 home/work/standby 的完整六维位姿
│       ├── record_drop_poses.py        # 记录 bottle/cup 回收盒中心 XY
│       ├── probe_cartesian_reachability.py
│       │                                   # 探测哪些笛卡尔点可达
│       ├── sweep_cartesian_pose.py     # 从一个已知可达点逐步扫向目标点
│       └── run_sort_trash_pipeline.py  # 总控骨架脚本，当前偏实验性质
├── pyAgxArm/                           # 当前项目实际使用的机械臂 Python SDK
├── webapp/                             # 独立前端工程（React + Vite + Tailwind）
│   ├── src/components/                 # 前端页面组件
│   ├── src/api/                        # 前端 API 客户端壳
│   ├── src/mocks/                      # 前端 mock 数据层
│   └── src/features/dashboard/         # 假抓取控制台主页面
└── third_party/                        # 第三方代码、SDK 和参考实现
```

### 目录怎么理解

- `scripts/vision/`
  - 负责“看见物体”
- `scripts/calibration/`
  - 负责“把相机坐标变成机械臂坐标”
- `scripts/control/`
  - 负责“让机械臂按流程运动”
- `config/`
  - 负责“保存流程位姿、回收点和工作空间”
- `data/`
  - 负责“保存标定结果和实验数据”
- `webapp/`
  - 负责“给小白操作的网页控制台”

## 环境初始化

如果需要创建或更新 `grasp-gpu`：

```bash
cd /home/robot/project/sort_trash
bash environment/setup_grasp_gpu.sh
```

这个脚本会：

- 创建或更新 `grasp-gpu`
- 把当前仓库里的 `pyAgxArm` 以 editable 方式安装进去
- 跑一次基础自检

## 当前默认配置

[sort_trash_pipeline.example.yaml](/home/robot/project/sort_trash/config/sort_trash_pipeline.example.yaml) 默认引用的是 [calibration.identity.yaml](/home/robot/project/sort_trash/config/calibration.identity.yaml)。

这只是一个占位标定文件，目的是让你在没有真机、没有真实标定结果时，先把脚本入口、模型加载、配置解析这些基础链路跑通。

只要后面开始碰机械臂，就必须换成真实的 `calibration_result.yaml`。

## 基础自检

不接真机时，先跑：

```bash
cd /home/robot/project/sort_trash
conda run -n grasp-gpu python scripts/dev/check_setup.py \
  --config config/sort_trash_pipeline.example.yaml
```

如果只想额外试加载 YOLO 权重：

```bash
conda run -n grasp-gpu python scripts/dev/check_setup.py \
  --config config/sort_trash_pipeline.example.yaml \
  --try-model
```

如果已经接上 D435，再试：

```bash
conda run -n grasp-gpu python scripts/dev/check_setup.py \
  --config config/sort_trash_pipeline.example.yaml \
  --try-camera
```

## 渐进式联调

### 第 1 步：无硬件自测

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
python scripts/control/run_sort_trash_pipeline.py \
  --config config/sort_trash_pipeline.example.yaml \
  --allow-cpu \
  --self-test
```

这一步完全不需要相机和机械臂。

它会验证：

- 配置文件能否读取
- 占位标定文件能否读取
- YOLO 权重能否加载
- 总控脚本主链路能否完整执行一次

如果这一步通过，再进入相机三步验证。

### 第 2 步：只测 RealSense 取流

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
python scripts/vision/view_realsense_stream.py
```

目标：

- 左侧彩色图正常
- 右侧深度图正常
- 桌面和物体的深度变化可见

### 第 3 步：RealSense + YOLO 2D 检测

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
python scripts/vision/detect_realsense_yolo_2d.py --allow-cpu
```

目标：

- 能识别瓶子、杯子等目标
- 检测框和类别大体正确
- 框中心点大致落在物体上

### 第 4 步：RealSense + YOLO + 深度，输出相机坐标 XYZ

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
python scripts/vision/detect_realsense_yolo_xyz.py --allow-cpu
```

目标：

- 取到检测框中心点
- 取到中心点附近的有效深度
- 输出目标在相机坐标系下的 `X, Y, Z`

说明：

- 这一步还不是手眼标定
- 这一步不需要机械臂在线
- 这一步输出的是“候选抓取点”的相机坐标，不是机械臂基坐标

如果已经完成标定，也可以直接同时显示机械臂基坐标：

```bash
python scripts/vision/detect_realsense_yolo_xyz.py \
  --allow-cpu \
  --calibration-file ./data/calib_run_02/calibration_result.yaml
```

这时画面和终端都会同时输出：

- `camera_xyz_m`
- `base_xyz_m`

### 第 5 步：做标定

先打印并使用仓库里生成的标准 ChArUco 板：

```text
assets/calibration_boards/charuco_11x8_15mm_11mm_dict4x4_50_a4.pdf
```

打印时务必使用 `100%` 比例，关闭 `fit to page`。

采集：

```bash
python scripts/calibration/capture_eye_to_hand.py \
  --channel can0 \
  --board-type charuco \
  --board-cols 11 \
  --board-rows 8 \
  --square-size-mm 15 \
  --marker-size-mm 11 \
  --aruco-dict DICT_4X4_50 \
  --samples 15 \
  --output-dir ./data/calib_run_02

python scripts/calibration/solve_eye_to_hand.py \
  --dataset-dir ./data/calib_run_02

python scripts/calibration/verify_eye_to_hand.py \
  --calibration-file ./data/calib_run_02/calibration_result.yaml \
  --channel can0 \
  --camera-serial 241222074755 \
  --samples 5
```

这一步需要机械臂和相机都在线。

当前这一套标准板和脚本已经验证通过，`calib_run_02` 可作为当前可用标定基线。

### 第 6 步：单独碰机械臂

如果 `hover_detected_target.py`、`move_flange_pose.py`、`run_fake_grasp_cycle.py` 报：

- `CAN port can0 is not UP`
- 或 `candump can0` 提示 `Network is down`

先执行：

```bash
cd /home/robot/project/sort_trash/pyAgxArm/pyAgxArm/scripts/ubuntu
sudo bash can_activate.sh can0 1000000
```

然后检查：

```bash
ip -details link show can0
candump can0
```

只有 `can0` 正常 `UP` 且 `candump can0` 能刷帧时，再继续后面的机械臂脚本。

先 dry-run：

```bash
python scripts/control/move_flange_pose.py \
  --channel can0 \
  --pose -450 0 360 40 45 45 \
  --mm \
  --degrees \
  --send-order mode_target_mode \
  --mode-resend 3
```

确认打印的目标位姿没问题后，再加 `--go`。

说明：

- `move_p` 在这台 NERO 上对可达性很敏感，不是所有笛卡尔位姿都能执行。
- 当前更稳定的发送方式是：
  - `--send-order mode_target_mode`
  - `--mode-resend 3`
- 现在脚本会同时检查平移和姿态误差，不再只看平移。

### 第 7 步：视觉悬停验证

把目标检测结果转成机械臂基坐标，在目标上方固定高度生成悬停位姿：

```bash
DISPLAY=:0 XAUTHORITY=/run/user/1000/gdm/Xauthority \
python scripts/control/hover_detected_target.py \
  --camera-serial 241222074755 \
  --allow-cpu \
  --calibration-file ./data/calib_run_02/calibration_result.yaml
```

说明：

- 默认优先抓取 `bottle`，其次 `cup`
- `cell phone` 会按 `bottle` 处理，方便兼容当前场景中的误检
- 目标短暂丢失时会保留一段时间继续使用最近一次结果
- 当前默认姿态已经改成 `rx=90, ry=-90, rz=0`
- 支持运行时手动调偏移：
  - `a / d`：`X - / X +`
  - `w / s`：`Y + / Y -`
  - `r / v`：`Z + / Z -`
  - `x`：恢复到启动 offset

按键：

- `g`：单次锁定当前目标并发送一次悬停命令
- `f`：切换连续跟随模式
- `q`：退出

真机执行时加 `--go`。连续跟随默认发送上限为 `30Hz`，也可以通过 `--follow-rate-hz` 修改。

当前常用示例：

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
DISPLAY=:0 XAUTHORITY=/run/user/1000/gdm/Xauthority \
python scripts/control/hover_detected_target.py \
  --camera-serial 241222074755 \
  --allow-cpu \
  --calibration-file ./data/calib_run_02/calibration_result.yaml \
  --follow-rate-hz 10 \
  --hover-height-m 0.20 \
  --go
```

### 第 7.5 步：本地前端操作台

仓库现在包含一个独立前端工程：

```text
webapp/
```

它的定位是：

- React + Vite + Tailwind 的本地 Fake Grasp 操作台壳
- 页面结构按真实 `/api/*` 协议设计
- 可用 `mock` 模式先做前端联调
- 不直接碰机器人 SDK

当前前端范围说明：

- 已有前端工程骨架、页面组件、API 客户端壳、mock 层
- **还没有正式 FastAPI 后端**
- 默认真实接口使用相对路径 `/api`

如果你在有 Node.js / npm 的机器上运行：

```bash
cd /home/robot/project/sort_trash/webapp
npm install
VITE_USE_MOCK=true npm run dev
```

说明：

- `VITE_USE_MOCK=true`：使用本地 mock 数据开发
- `VITE_USE_MOCK=false` 或不设置：按真实 `/api/*` 请求后端
- 如果当前机器没有 `node` / `npm`，就只能先保留代码，不能在本机直接构建

### 第 8 步：记录流程位姿和回收点

记录完整流程位姿：

- `home`：零点位
- `work`：工作模式位
- `standby`：待定位

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu

python scripts/control/record_task_poses.py --init-defaults
python scripts/control/record_task_poses.py --record home
python scripts/control/record_task_poses.py --record work
python scripts/control/record_task_poses.py --record standby
```

这会写到：

- `config/task_poses.yaml`

记录回收盒中心点：

```bash
python scripts/control/record_drop_poses.py --record bottle
python scripts/control/record_drop_poses.py --record cup
```

这会写到：

- `config/drop_poses.yaml`

说明：

- `record_task_poses.py` 记录完整 `x y z rx ry rz`
- `record_drop_poses.py` 只记录回收盒中心的 `x y`
- 如果已有同名记录，终端会询问是否覆盖

### 第 9 步：假抓取全流程

当前已经增加一个“无灵巧手”的完整机械臂流程脚本：

- `home -> work -> target_hover -> pregrasp_10cm -> [FAKE GRASP] -> target_retreat -> standby -> drop_hover -> drop_down(z=0.15) -> [FAKE RELEASE] -> drop_retreat -> home`

脚本：

- `scripts/control/run_fake_grasp_cycle.py`

当前默认参数基线：

- 默认姿态：`rx=90, ry=-90, rz=0`
- `target_hover`：目标上方 `0.20m`
- `pregrasp_10cm`：当前默认 `grasp_z_offset_m=0.18`
- `drop_down`：固定 `z=0.15m`

运行方式：

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
DISPLAY=:0 XAUTHORITY=/run/user/1000/gdm/Xauthority \
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

说明：

- 启动时如果不在 `home`，脚本会先自动回 `home`
- 按 `g` 执行一次完整 fake grasp cycle
- 按 `q` 退出
- 项目里所有主要位姿控制入口都增加了安全限制：末端目标 `z` 必须 `>= 0.10m`

### 第 10 步：总控骨架

先 dry-run：

```bash
python scripts/control/run_sort_trash_pipeline.py \
  --config config/sort_trash_pipeline.example.yaml \
  --allow-cpu
```

真机动作确认后，再加 `--go`。

## 当前已做的仓库修正

- 机械臂相关脚本现在会优先使用当前仓库内的 `pyAgxArm`
- 环境文件已去掉旧的绝对路径依赖
- 已增加总控骨架脚本和示例配置
- 已增加标准 ChArUco 生成脚本和可打印板
- 已增加目标悬停脚本 `hover_detected_target.py`
- 已增加笛卡尔可达性探测脚本 `probe_cartesian_reachability.py`
- 已增加流程位姿记录脚本 `record_task_poses.py`
- 已增加回收点记录脚本 `record_drop_poses.py`
- 已增加 fake 抓取全流程脚本 `run_fake_grasp_cycle.py`
- `detect_realsense_yolo_xyz.py` 已支持同时显示 `camera_xyz` 和 `base_xyz`
- `move_flange_pose.py` 已支持更细的发送顺序调试和姿态误差检查
- 主要位姿控制入口已统一增加 `z >= 0.10m` 安全检查

## 当前仍然保留为占位的部分

- OmniHand 需要安装官方 Python SDK，并在 `hand` 配置里填好开合角度后才能 `--go`
- `run_sort_trash_pipeline.py` 目前是单目标 pick/place 骨架，不是完整生产流程
