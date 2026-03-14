# AgileX Robotic Arm ROS2 Driver

[中文](./README.md)

|ROS |STATE|
|---|---|
|![humble](https://img.shields.io/badge/ros-humble-blue.svg)|![Pass](https://img.shields.io/badge/Pass-blue.svg)|
|![jazzy](https://img.shields.io/badge/ros-jazzy-blue.svg)|![Pass](https://img.shields.io/badge/Pass-blue.svg)|

## Overview

This driver package provides full ROS2 interface support for AgileX series robotic arms (Piper, Nero, etc.).

| Description | Documentation |
|---|---|
| SDK | [pyAgxArm](https://github.com/agilexrobotics/pyAgxArm) |
| CAN module usage | [can_user](./docs/CAN_USER_EN.md) |
| TCP Offset Configuration | [tcp_offset](./docs/tcp_offset/TCP_OFFSET_EN.md) |
| URDF | [URDF](https://github.com/agilexrobotics/agx_arm_urdf) |
| Moveit| [Moveit](./src/agx_arm_moveit/README_EN.md) |
| Q&A | [Q&A](./docs/Q&A.md) |

---

## Quick Start

### 1. Install Python SDK

```bash
git clone https://github.com/agilexrobotics/pyAgxArm.git
cd pyAgxArm
```

Choose the installation command based on your ROS version:

**Jazzy** installation command:

```bash
pip3 install . --break-system-packages
```

**Humble** installation command:

```bash
pip3 install .
```

### 2. Install ROS2 Driver

1. Create workspace

    ```bash
    mkdir -p ~/catkin_ws/src
    cd ~/catkin_ws/src
    ```

2. Clone repository

    ```bash
    git clone -b ros2 --recurse-submodules https://github.com/agilexrobotics/agx_arm_ros.git
    ```

    ```bash
    cd agx_arm_ros/
    git submodule update --remote --recursive
    ```

### 3. Install Dependencies

Run the script to install all dependencies at once:

```bash
cd ~/catkin_ws/src/agx_arm_ros/scripts/
chmod +x agx_arm_install_deps.sh
bash ./agx_arm_install_deps.sh
```

Or install manually by executing the following commands in order:

1. Python dependencies

    Choose the installation command based on your ROS version:

    **Jazzy** installation command:

    ```bash
    pip3 install python-can scipy numpy --break-system-packages
    ```

    **Humble** installation command:

    ```bash
    pip3 install python-can scipy numpy
    ```

2. CAN tools

    ```bash
    sudo apt update && sudo apt install can-utils ethtool
    ```

3. ROS2 dependencies

    ```bash
    sudo apt install -y \
        ros-$ROS_DISTRO-ros2-control \
        ros-$ROS_DISTRO-ros2-controllers \
        ros-$ROS_DISTRO-controller-manager \
        ros-$ROS_DISTRO-topic-tools \
        ros-$ROS_DISTRO-joint-state-publisher-gui \
        ros-$ROS_DISTRO-robot-state-publisher \
        ros-$ROS_DISTRO-xacro \
        python3-colcon-common-extensions
    ```

4. MoveIt

    Before using MoveIt, you need to configure the related dependencies. For detailed steps, please refer to: [agx_arm_moveit](./src/agx_arm_moveit/README_EN.md)
    
    Or execute the following commands in order:

    ```bash
    sudo apt install ros-$ROS_DISTRO-moveit*
    ```

    ```bash
    sudo apt-get install -y \
        ros-$ROS_DISTRO-control* \
        ros-$ROS_DISTRO-joint-trajectory-controller \
        ros-$ROS_DISTRO-joint-state-* \
        ros-$ROS_DISTRO-gripper-controllers \
        ros-$ROS_DISTRO-trajectory-msgs
    ```

    If the system locale is not set to English, it must be set to English locale:

    ```bash
    echo "export LC_NUMERIC=en_US.UTF-8" >> ~/.bashrc
    source ~/.bashrc
    ```

### 4. Build and Source Workspace

Check if you are in a virtual environment. If so, it is recommended to exit the virtual environment first.

```bash
which pip3
```

Build and Source the workspace:

```bash
cd ~/catkin_ws
colcon build
source install/setup.bash
```

---

## Usage

### Activate CAN Module

CAN module must be activated before use. For details, see: [CAN Configuration Guide](./docs/CAN_USER_EN.md)

When only a single CAN module is connected to the computer, you can **quickly complete activation** through the following steps:

Open a terminal window and execute the following command:

```bash
cd ~/catkin_ws/src/agx_arm_ros/scripts 
bash can_activate.sh
```

### Launch Driver

You can start the driver using a launch file or by running the node directly.

> **Important: Read before launching**
> The parameters in the following launch commands **must** be replaced according to your actual hardware configuration:
> - **`can_port`**: The CAN port connected to the arm, e.g. `can0`.
> - **`arm_type`**: The arm model, e.g. `piper`.
> - **`effector_type`**: The end-effector type, e.g. `none` or `agx_gripper`.
> - **`tcp_offset`**: Tool Center Point (TCP) offset relative to the flange center, e.g. [0.0, 0.0, 0.0, 0.0, 0.0, 0.0] 
>   - Note: All values of this parameter must be floating-point numbers; for TCP offset configuration examples, see [TCP Offset Guide](./docs/tcp_offset/TCP_OFFSET_EN.md).
>
> For full parameter descriptions, default values and options, see **[Launch Parameters](#launch-parameters)** below.


**Using launch file:**

```bash
ros2 launch agx_arm_ctrl start_single_agx_arm.launch.py can_port:=can0 arm_type:=piper effector_type:=none tcp_offset:='[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]'
```

**Running node directly:**

```bash
ros2 run agx_arm_ctrl agx_arm_ctrl_single --ros-args -p can_port:=can0 -p arm_type:=piper -p effector_type:=none -p tcp_offset:='[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]'
```

**Visualization Debug Launch:**

```bash
ros2 launch agx_arm_ctrl start_single_agx_arm_rviz.launch.py can_port:=can0 arm_type:=piper effector_type:=none tcp_offset:='[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]'
```

> **Note:** This launch file continuously occupies the `/joint_states` topic, preventing control commands in the [Control Examples](#control-examples) from executing properly. To run control commands, please terminate this launch file first.

### Launch Parameters

| Parameter | Default | Description | Options |
|-----------|---------|-------------|---------|
| `can_port` | `can0` | CAN port | - |
| `arm_type` | `piper` | Arm model | `piper`, `piper_h`, `piper_l`, `piper_x`, `nero` |
| `effector_type` | `none` | End-effector type | `none`, `agx_gripper`, `revo2` |
| `auto_enable` | `True` | Auto enable on startup | `True`, `False` |
| `installation_pos` | `horizontal` | Mount orientation (Piper series only) | `horizontal`, `left`, `right` |
| `payload` | `empty` | Payload config (Piper series only for now) | `full`, `half`, `empty` |
| `speed_percent` | `100` | Motion speed (%) | `0-100` |
| `pub_rate` | `200` | Status publish rate (Hz) | - |
| `enable_timeout` | `5.0` | Enable timeout (seconds) | - |
| `tcp_offset` | `[0.0,0.0,0.0,0.0,0.0,0.0]` | Tool Center Point (TCP) offset relative to the flange center [x,y,z,rx,ry,rz] | - |
| `log_level` | `info` | Log level | `debug`, `info`, `warn`, `error`, `fatal` |

### URDF Model Visualization

#### Standalone Model Viewer

No real robotic arm connection required. Load the URDF model in RViz and manually adjust joints using the GUI slider:

```bash
ros2 launch agx_arm_description display.launch.py arm_type:=piper
```

**The `arm_type` parameter supports three ways to specify the model:**

1. **Preset model name** (recommended): Use a built-in model name to automatically match the corresponding URDF file

    ```bash
    ros2 launch agx_arm_description display.launch.py arm_type:=piper
    ```

2. **Relative path**: Path relative to the `agx_arm_urdf/` directory, suitable for custom models

    ```bash
    ros2 launch agx_arm_description display.launch.py arm_type:=piper/urdf/piper_description.urdf
    ```

3. **Absolute path**: Directly specify the absolute path to a URDF file, suitable for model files at any location

    ```bash
    ros2 launch agx_arm_description display.launch.py arm_type:=/home/user/my_robot/custom_arm.urdf
    ```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `arm_type` | `piper` | Arm model or URDF path. Presets: `piper`, `piper_x`, `piper_l`, `piper_h`, `nero`; also supports relative paths under `agx_arm_urdf/` or any absolute path |
| `gui` | `true` | Enable joint_state_publisher_gui slider control interface |
| `rvizconfig` | Built-in config | Absolute path to a custom RViz configuration file |

#### Follow Real Arm

Please [Launch the Arm Driver](./README_EN.md#launch-driver) first. The model in RViz will track the real arm's joint states in real time (subscribes to `feedback/joint_states`):

```bash
ros2 launch agx_arm_description display_urdf_follow.launch.py arm_type:=piper
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `arm_type` | `piper` | Arm model or URDF path (same usage as `display.launch.py` above) |
| `rvizconfig` | Built-in config | Absolute path to a custom RViz configuration file |

> **⚠️ Note: Configuration Consistency**
>
> When running `display_urdf_follow`, the **arm type** and **end-effector type** of the selected `urdf` must strictly match the configuration in [Launch the Arm Driver](./README_EN.md#launch-driver)
>
> - If mismatched, the URDF model will not align with the actual hardware joint definitions, resulting in a **broken TF tree** or **missing model parts in RViz**.

---

## Control Examples

Open an additional terminal and run the following commands:

```bash
cd ~/catkin_ws
source install/setup.bash
cd src/agx_arm_ros
```

### Piper Arm

1. Joint motion

    ```bash
    ros2 topic pub /control/move_j sensor_msgs/msg/JointState \
      "$(cat test/piper/test_move_j.yaml)" -1
    ```

2. Point-to-point motion

    ```bash
    ros2 topic pub /control/move_p geometry_msgs/msg/PoseStamped \
      "$(cat test/piper/test_move_p.yaml)" -1
    ```

3. Linear motion

    ```bash
    ros2 topic pub /control/move_l geometry_msgs/msg/PoseStamped \
      "$(cat test/piper/test_move_l.yaml)" -1
    ```

4. Circular motion (start → middle → end)

    ```bash
    ros2 topic pub /control/move_c geometry_msgs/msg/PoseArray \
      "$(cat test/piper/test_move_c.yaml)" -1
    ```

### Nero Arm

1. Joint motion

    ```bash
    ros2 topic pub /control/move_j sensor_msgs/msg/JointState \
      "$(cat test/nero/test_move_j.yaml)" -1
    ```

2. Point-to-point motion

    ```bash
    ros2 topic pub /control/move_p geometry_msgs/msg/PoseStamped \
      "$(cat test/nero/test_move_p.yaml)" -1
    ```

3. Linear motion

    ```bash
    ros2 topic pub /control/move_l geometry_msgs/msg/PoseStamped \
      "$(cat test/nero/test_move_l.yaml)" -1
    ```

4. Circular motion (start → middle → end)

    ```bash
    ros2 topic pub /control/move_c geometry_msgs/msg/PoseArray \
      "$(cat test/nero/test_move_c.yaml)" -1
    ```

### Gripper

1. Gripper control (via `/control/joint_states`)

    ```bash
    ros2 topic pub /control/joint_states sensor_msgs/msg/JointState \
      "$(cat test/gripper/test_gripper_joint_states.yaml)" -1
    ```

2. Arm + Gripper combined control (via `/control/joint_states`)

    ```bash
    ros2 topic pub /control/joint_states sensor_msgs/msg/JointState \
      "$(cat test/piper/test_arm_gripper_joint_states.yaml)" -1
    ```

### Dexterous Hand

1. Dexterous hand — Position mode (all fingers move to 10)

    ```bash
    ros2 topic pub /control/hand agx_arm_msgs/msg/HandCmd \
      "$(cat test/hand/test_hand_position.yaml)" -1
    ```

2. Dexterous hand — Speed mode (all fingers speed 50)

    ```bash
    ros2 topic pub /control/hand agx_arm_msgs/msg/HandCmd \
      "$(cat test/hand/test_hand_speed.yaml)" -1
    ```

3. Dexterous hand — Current mode (all fingers current 50)

    ```bash
    ros2 topic pub /control/hand agx_arm_msgs/msg/HandCmd \
      "$(cat test/hand/test_hand_current.yaml)" -1
    ```

4. Dexterous hand — Position-time control (all fingers move to 50, time 1 second)

    ```bash
    ros2 topic pub /control/hand_position_time agx_arm_msgs/msg/HandPositionTimeCmd \
      "$(cat test/hand/test_hand_position_time.yaml)" -1
    ```

5. Dexterous hand control (via `/control/joint_states`)

    ```bash
    ros2 topic pub /control/joint_states sensor_msgs/msg/JointState \
      "$(cat test/hand/test_hand_joint_states.yaml)" -1
    ```

6. Arm + Dexterous hand combined control (via `/control/joint_states`)

    ```bash
    ros2 topic pub /control/joint_states sensor_msgs/msg/JointState \
      "$(cat test/piper/test_arm_hand_joint_states.yaml)" -1
    ```

### Service Calls

1. Enable arm

    ```bash
    ros2 service call /enable_agx_arm std_srvs/srv/SetBool "{data: true}"
    ```

2. Disable arm

    ```bash
    ros2 service call /enable_agx_arm std_srvs/srv/SetBool "{data: false}"
    ```

3. Move to home position

    ```bash
    ros2 service call /move_home std_srvs/srv/Empty
    ```

4. Exit teach mode (Piper series)

    ```bash
    ros2 service call /exit_teach_mode std_srvs/srv/Empty
    ```

    > **⚠️ Important Safety Note:** 
    > 1. After executing this command, the robotic arm will first perform a homing operation and then restart automatically; there is a risk of falling during this process. It is recommended to gently hold the robotic arm after homing to prevent damage from falling.
    > 2. For Piper series robotic arms with firmware version 1.8.5 and above, the seamless mode switching feature is supported. There is no need to execute the above service command to exit teach mode, as the system will complete the mode switch automatically, avoiding the aforementioned fall risk.

### Status Subscription

1. Joint states

    ```bash
    ros2 topic echo /feedback/joint_states
    ```

2. TCP pose

    ```bash
    ros2 topic echo /feedback/tcp_pose
    ```

3. Arm status

    ```bash
    ros2 topic echo /feedback/arm_status
    ```

4. Leader joint angles(For leader arm mode)

    ```bash
    ros2 topic echo /feedback/leader_joint_angles
    ```

5. Gripper status

    ```bash
    ros2 topic echo /feedback/gripper_status
    ```

6. Dexterous hand status 

    ```bash
    ros2 topic echo /feedback/hand_status
    ```

---

## ROS2 Interface

### Feedback Topics

| Topic | Message Type | Description | Condition |
|-------|--------------|-------------|-----------|
| `/feedback/joint_states` | `sensor_msgs/JointState` | Joint states | Always available |
| `/feedback/tcp_pose` | `geometry_msgs/PoseStamped` | TCP pose | Always available |
| `/feedback/arm_status` | `agx_arm_msgs/AgxArmStatus` | Arm status | Always available |
| `/feedback/leader_joint_angles` | `sensor_msgs/JointState` | Leader joint angles | Leader arm mode |
| `/feedback/gripper_status` | `agx_arm_msgs/GripperStatus` | Gripper status | AgxGripper configured |
| `/feedback/hand_status` | `agx_arm_msgs/HandStatus` | Dexterous hand status | Revo2 configured |

#### Joint States Details (`/feedback/joint_states`)

This topic contains combined joint states for the arm and end-effector:

**Arm Joints** (`joint1` ~ `joint*`)
| Field | Description |
|-------|-------------|
| `position` | Joint angle (rad) |
| `velocity` | Joint velocity (rad/s) |
| `effort` | Joint torque (Nm) |

**Gripper Joint** (`gripper`, requires `effector_type=agx_gripper`)
| Field | Description |
|-------|-------------|
| `position` | Gripper width (m) |
| `velocity` | 0.0 |
| `effort` | Force (N) |

**Dexterous Hand Joints** (requires `effector_type=revo2`)

Joint naming convention: `{hand}_f_joint{finger}_[segment]`
- `l` = left hand, `r` = right hand
- `joint1` = thumb, `joint2` ~ `joint5` = index to pinky
- `_1` = base, `_2` = tip (thumb only has two segments)

Example: `l_f_joint1_1` represents left hand thumb base joint

Full joint name list:
- Left hand: `l_f_joint1_1`, `l_f_joint1_2`, `l_f_joint2`, `l_f_joint3`, `l_f_joint4`, `l_f_joint5`
- Right hand: `r_f_joint1_1`, `r_f_joint1_2`, `r_f_joint2`, `r_f_joint3`, `r_f_joint4`, `r_f_joint5`

#### Arm Status Details (`/feedback/arm_status`)

Message type: `agx_arm_msgs/AgxArmStatus`

**Message Field Description:**

| Field | Type | Description |
|-------|------|-------------|
| `ctrl_mode` | `uint8` | Control mode, see table below |
| `arm_status` | `uint8` | Arm status, see table below |
| `mode_feedback` | `uint8` | Mode feedback, see table below |
| `teach_status` | `uint8` | Teach status, see table below |
| `motion_status` | `uint8` | Motion status: 0=reached target, 1=not reached |
| `trajectory_num` | `uint8` | Current trajectory point number (0~255, feedback in offline trajectory mode) |
| `err_status` | `int64` | Error status code |
| `joint_1_angle_limit` ~ `joint_7_angle_limit` | `bool` | Joint 1~7 angle limit (true=abnormal, false=normal) |
| `communication_status_joint_1` ~ `communication_status_joint_7` | `bool` | Joint 1~7 communication status (true=abnormal, false=normal) |

**Control Mode (`ctrl_mode`):**

| Value | Description |
|-------|-------------|
| 0 | Standby |
| 1 | CAN command control |
| 2 | Teach mode |
| 3 | Ethernet control |
| 4 | WiFi control |
| 5 | Remote control mode |
| 6 | Coordinated teach input |
| 7 | Offline trajectory mode |
| 8 | TCP control |

**Arm Status (`arm_status`):**

| Value | Description |
|-------|-------------|
| 0 | Normal |
| 1 | Emergency stop |
| 2 | No solution |
| 3 | Singularity |
| 4 | Target angle out of range |
| 5 | Joint communication abnormal |
| 6 | Joint brake not released |
| 7 | Collision detected |
| 8 | Teach drag overspeed |
| 9 | Joint status abnormal |
| 10 | Other abnormal |
| 11 | Teaching recording |
| 12 | Teaching executing |
| 13 | Teaching paused |
| 14 | Main controller NTC overtemperature |
| 15 | Release resistor NTC overtemperature |

**Mode Feedback (`mode_feedback`):**

| Value | Description |
|-------|-------------|
| 0 | MOVE P |
| 1 | MOVE J |
| 2 | MOVE L |
| 3 | MOVE C |
| 4 | MOVE MIT |
| 5 | MOVE CPV |

**Teach Status (`teach_status`):**

| Value | Description |
|-------|-------------|
| 0 | Closed |
| 1 | Start teaching record (enter drag teaching) |
| 2 | End teaching record (exit drag teaching) |
| 3 | Execute teaching trajectory |
| 4 | Pause execution |
| 5 | Continue execution |
| 6 | Terminate execution |
| 7 | Move to trajectory start point |

#### Gripper Status Details (`/feedback/gripper_status`)

Message type: `agx_arm_msgs/GripperStatus`

**Message Field Description:**

| Field | Type | Description |
|-------|------|-------------|
| `header` | `std_msgs/Header` | Message header |
| `width` | `float64` | Current gripper opening width (unit: meters) |
| `force` | `float64` | Current gripping force (unit: Newtons) |
| `voltage_too_low` | `bool` | Voltage too low (true=abnormal, false=normal) |
| `motor_overheating` | `bool` | Motor overheating (true=abnormal, false=normal) |
| `driver_overcurrent` | `bool` | Driver overcurrent (true=abnormal, false=normal) |
| `driver_overheating` | `bool` | Driver overheating (true=abnormal, false=normal) |
| `sensor_status` | `bool` | Sensor status (true=abnormal, false=normal) |
| `driver_error_status` | `bool` | Driver error status (true=abnormal, false=normal) |
| `driver_enable_status` | `bool` | Driver enable status (true=enabled, false=disabled) |
| `homing_status` | `bool` | Homing status (true=completed, false=not completed) |

#### Hand Status Details (`/feedback/hand_status`)

Message type: `agx_arm_msgs/HandStatus`

**Message Field Description:**

| Field | Type | Description |
|-------|------|-------------|
| `header` | `std_msgs/Header` | Message header |
| `left_or_right` | `uint8` | Hand type identifier: 1=left hand, 2=right hand |

**Finger Position Fields (range: [0, 100], 0=fully open, 100=fully closed):**

| Field | Type | Description |
|-------|------|-------------|
| `thumb_tip_pos` | `uint8` | Thumb tip position |
| `thumb_base_pos` | `uint8` | Thumb base position |
| `index_finger_pos` | `uint8` | Index finger position |
| `middle_finger_pos` | `uint8` | Middle finger position |
| `ring_finger_pos` | `uint8` | Ring finger position |
| `pinky_finger_pos` | `uint8` | Pinky finger position |

**Finger Motor Status Fields (0=idle, 1=running, 2=stalled/jammed):**

| Field | Type | Description |
|-------|------|-------------|
| `thumb_tip_status` | `uint8` | Thumb tip motor status |
| `thumb_base_status` | `uint8` | Thumb base motor status |
| `index_finger_status` | `uint8` | Index finger motor status |
| `middle_finger_status` | `uint8` | Middle finger motor status |
| `ring_finger_status` | `uint8` | Ring finger motor status |
| `pinky_finger_status` | `uint8` | Pinky finger motor status |

### Control Topics

| Topic                           | Message Type                       | Description           | Condition          |
| ----------------------------- | ---------------------------------- | ------------ | ------------- |
| `/control/joint_states`       | `sensor_msgs/JointState`           | Joint control (with end-effector) | Always available          |
| `/control/move_j`             | `sensor_msgs/JointState`           | Joint control motion       | Always available          |
| `/control/move_p`             | `geometry_msgs/PoseStamped`        | Point-to-point motion        | Always available          |
| `/control/move_l`             | `geometry_msgs/PoseStamped`        | Linear motion         | Piper series      |
| `/control/move_c`             | `geometry_msgs/PoseArray`          | Circular motion         | Piper series      |
| `/control/move_js`            | `sensor_msgs/JointState`           | MIT mode joint motion   | Piper series      |
| `/control/move_mit`           | `agx_arm_msgs/MoveMITMsg`          | MIT torque control     | Piper series      |
| `/control/hand`               | `agx_arm_msgs/HandCmd`             | Dexterous hand control        | Revo2 configured      |
| `/control/hand_position_time` | `agx_arm_msgs/HandPositionTimeCmd` | Hand position-time control    | Revo2 configured      |

#### `/control/joint_states` Details

This topic uses the `sensor_msgs/JointState` message type and supports simultaneous control of arm joints and end-effector (gripper/dexterous hand). Only the joints to be controlled need to be sent; joints not included will not be affected.

**Message Field Description:**

| Field | Description |
|-------|-------------|
| `name` | Joint name list |
| `position` | Target position for corresponding joints |
| `velocity` | Not used (can be left empty) |
| `effort` | Used for gripper force control (only effective for `gripper` joint) |

**Gripper control via `/control/joint_states`** (requires `effector_type=agx_gripper`)

Include `gripper` in `name`, set target width via `position`, and set gripping force via `effort`.

| Joint Name | position (width) | effort (force) |
|------------|-----------------|----------------|
| `gripper` | Target width (m), range: [0.0, 0.1] | Target force (N), range: [0.5, 3.0], default: 1.0 |

> **Note:** When `effort` is 0 or not specified, the default force of 1.0N is used.

Example: Control gripper width to 0.05m with force 1.5N
```bash
ros2 topic pub /control/joint_states sensor_msgs/msg/JointState \
  "{name: [gripper], position: [0.05], velocity: [], effort: [1.5]}" -1
```

**Dexterous hand control via `/control/joint_states`** (requires `effector_type=revo2`)

Include dexterous hand joint names in `name`, set target position via `position` (position mode, range [0, 100]). Only the joints to be controlled need to be sent; joints not included will maintain their current position.

Example: Control only the left index finger to position 80
```bash
ros2 topic pub /control/joint_states sensor_msgs/msg/JointState \
  "{name: [l_f_joint2], position: [80], velocity: [], effort: []}" -1
```

| Joint Name | Description | Position Range |
|------------|-------------|---------------|
| `l_f_joint1_1` / `r_f_joint1_1` | Thumb base | [0, 100] |
| `l_f_joint1_2` / `r_f_joint1_2` | Thumb tip | [0, 100] |
| `l_f_joint2` / `r_f_joint2` | Index finger | [0, 100] |
| `l_f_joint3` / `r_f_joint3` | Middle finger | [0, 100] |
| `l_f_joint4` / `r_f_joint4` | Ring finger | [0, 100] |
| `l_f_joint5` / `r_f_joint5` | Pinky finger | [0, 100] |

#### `/control/move_mit` Details

Message type: `agx_arm_msgs/MoveMITMsg`

**Message Field Description:**

| Field | Type | Description |
|-------|------|-------------|
| `joint_index` | `int32[]` | Array of joint indices to control |
| `p_des` | `float64[]` | Desired joint position array (unit: radians) |
| `v_des` | `float64[]` | Desired joint velocity array (unit: radians/second) |
| `kp` | `float64[]` | Position gain array |
| `kd` | `float64[]` | Velocity gain array |
| `torque` | `float64[]` | Desired joint torque array (unit: Newton-meters, N·m) |

> **Note:** All array fields must have the same length as `joint_index`. Supports simultaneous control of multiple joints.

#### `/control/hand` Details

Message type: `agx_arm_msgs/HandCmd`

**Message Field Description:**

| Field | Type | Description |
|-------|------|-------------|
| `mode` | `string` | Control mode: `position` (position) / `speed` (speed) / `current` (current) |

**Finger Target Value Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `thumb_tip` | `int8` | Thumb tip target value |
| `thumb_base` | `int8` | Thumb base target value |
| `index_finger` | `int8` | Index finger target value |
| `middle_finger` | `int8` | Middle finger target value |
| `ring_finger` | `int8` | Ring finger target value |
| `pinky_finger` | `int8` | Pinky finger target value |

**Value Ranges for Different Modes:**

| Mode | Value Range | Description |
|------|-------------|-------------|
| `position` | [0, 100] | 0=fully open, 100=fully closed |
| `speed` | [-100, 100] | Negative=open direction, positive=close direction |
| `current` | [-100, 100] | Negative=open direction, positive=close direction |

#### `/control/hand_position_time` Details

Message type: `agx_arm_msgs/HandPositionTimeCmd`

**Message Field Description:**

**Finger Target Position Fields (range: [0, 100], 0=fully open, 100=fully closed):**

| Field | Type | Description |
|-------|------|-------------|
| `thumb_tip_pos` | `int8` | Thumb tip position |
| `thumb_base_pos` | `int8` | Thumb base position |
| `index_finger_pos` | `int8` | Index finger position |
| `middle_finger_pos` | `int8` | Middle finger position |
| `ring_finger_pos` | `int8` | Ring finger position |
| `pinky_finger_pos` | `int8` | Pinky finger position |

**Finger Arrival Time Fields (unit: 10ms, range: [0, 255], e.g.: 200 = 2 seconds):**

| Field | Type | Description |
|-------|------|-------------|
| `thumb_tip_time` | `uint8` | Thumb tip arrival time |
| `thumb_base_time` | `uint8` | Thumb base arrival time |
| `index_finger_time` | `uint8` | Index finger arrival time |
| `middle_finger_time` | `uint8` | Middle finger arrival time |
| `ring_finger_time` | `uint8` | Ring finger arrival time |
| `pinky_finger_time` | `uint8` | Pinky finger arrival time |

### Services

| Service | Type | Description | Condition |
|---------|------|-------------|-----------|
| `/enable_agx_arm` | `std_srvs/SetBool` | Enable/disable arm | Always available |
| `/move_home` | `std_srvs/Empty` | Move to home position | Always available |
| `/exit_teach_mode` | `std_srvs/Empty` | Exit teach mode | Piper series |

---

## Parameter Limits

### Gripper

| Parameter | Range | Default | Description |
|-----------|-------|---------|-------------|
| width | [0.0, 0.1] m | - | Target opening width |
| force | [0.5, 3.0] N | 1.0 | Gripping force |

> ⚠️ Values out of range will be rejected (not executed), and the node will output a warning log. For example: when sending force=5.0, the command will not be executed, and a warning `force must be in range [0.5, 3.0], current value: 5.0` will be output.

### Dexterous Hand (Revo2)

| Parameter | Range | Description |
|-----------|-------|-------------|
| position | [0, 100] | Finger target position, 0 = fully open, 100 = fully closed |
| speed | [-100, 100] | Finger motion speed |
| current | [-100, 100] | Finger drive current |
| time | [0, 255] | Time to reach target position (unit: 10ms, e.g. 100 = 1 second) |

> ⚠️ Values out of range will be rejected (not executed), and the node will output a warning log. For example: when sending position=120, the command will not be executed, and a warning `position must be in range [0, 100], current value: 120` will be output.

---

## Important Notes

### CAN Communication

- CAN module **must be activated** before use
- Baud rate: **1000000 bps**
- If `SendCanMessage failed` error occurs, check CAN connection

### ⚠️ Safety Warnings

- **Maintain safe distance**: Do not enter the arm's workspace during motion to avoid injury
- **Singularity risk**: Joints may move suddenly and significantly near kinematic singularities
- **MIT mode is dangerous**: High-speed response MIT mode is extremely hazardous, use with caution
